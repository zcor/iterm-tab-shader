#!/usr/bin/env python3
"""Mark iTerm panes that ask for attention without writing to their input."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Any

try:
    import iterm2
except ModuleNotFoundError:
    iterm2 = None


POLL_SECONDS = 0.5
ATTENTION_RGB = (255, 159, 10)
PITCH_FACTORS = (1.0, 1.125, 1.25, 1.333333, 1.5)
NOTE_NAMES = ("do", "re", "mi", "fa", "sol")
FUNK_SOURCE = Path("/System/Library/Sounds/Funk.aiff")
CACHE_DIR = Path(
    os.environ.get(
        "ITERM_TAB_SHADER_CACHE_DIR",
        str(Path.home() / "Library" / "Caches" / "iterm-tab-shader"),
    )
)
LOCK_PATH = Path(os.environ.get("ITERM_TAB_SHADER_LOCK_PATH", str(CACHE_DIR / "attention.lock")))


@dataclass
class TabColorState:
    session_id: str
    tab_color: Any
    use_tab_color: bool | None
    tab_color_light: Any
    use_tab_color_light: bool | None
    tab_color_dark: Any
    use_tab_color_dark: bool | None


@dataclass
class BadgeState:
    session_id: str
    badge_text: str | None
    badge_color: Any


@dataclass
class PendingAlert:
    tab_id: str
    badge: BadgeState


def needs_attention(title: str) -> bool:
    """Claude uses a leading star for an attention request."""
    return title.lstrip().startswith("✳")


def has_working_spinner(title: str) -> bool:
    """Codex uses an animated Braille character while a turn is running."""
    stripped = title.lstrip()
    return bool(stripped) and 0x2800 <= ord(stripped[0]) <= 0x28FF


def codex_just_finished(previous_title: str, current_title: str) -> bool:
    """Codex finishes when its spinner disappears from a Codex title."""
    return (
        "(codex" in current_title.lower()
        and has_working_spinner(previous_title)
        and not has_working_spinner(current_title)
    )


def note_for_position(position: int) -> tuple[str, float]:
    index = max(position, 1) - 1
    degree = index % len(PITCH_FACTORS)
    octave = index // len(PITCH_FACTORS)
    return f"{NOTE_NAMES[degree]}{4 + octave}", PITCH_FACTORS[degree] * (2**octave)


def alert_path(position: int) -> Path | None:
    """Build a local sound cache if the optional macOS tools are available."""
    name, pitch_factor = note_for_position(position)
    path = CACHE_DIR / f"funk-{name}.wav"
    if path.exists():
        return path

    ffmpeg = shutil.which("ffmpeg")
    if not FUNK_SOURCE.exists() or ffmpeg is None:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp.wav")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(FUNK_SOURCE),
                "-af",
                f"asetrate={44_100 * pitch_factor:.6f},aresample=44100,volume=14dB,alimiter=limit=0.98",
                str(temporary),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        temporary.replace(path)
        return path
    except (FileNotFoundError, subprocess.CalledProcessError):
        temporary.unlink(missing_ok=True)
        return None


def ring(position: int) -> None:
    """Play asynchronously. A missing sound tool never delays the monitor."""
    def play() -> None:
        path = alert_path(position)
        if path is None:
            return
        try:
            subprocess.Popen(
                ["/usr/bin/afplay", str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            return

    threading.Thread(target=play, name="iterm-tab-shader-cue", daemon=True).start()


def attention_color() -> Any:
    if iterm2 is None:
        raise RuntimeError("The iTerm2 Python API is not installed")
    return iterm2.Color(*ATTENTION_RGB)


async def set_attention_color(session: Any) -> TabColorState:
    profile = await session.async_get_profile()
    state = TabColorState(
        session_id=session.session_id,
        tab_color=profile.tab_color,
        use_tab_color=profile.use_tab_color,
        tab_color_light=profile.tab_color_light,
        use_tab_color_light=profile.use_tab_color_light,
        tab_color_dark=profile.tab_color_dark,
        use_tab_color_dark=profile.use_tab_color_dark,
    )
    color = attention_color()
    await profile.async_set_tab_color(color)
    await profile.async_set_use_tab_color(True)
    await profile.async_set_tab_color_light(color)
    await profile.async_set_use_tab_color_light(True)
    await profile.async_set_tab_color_dark(color)
    await profile.async_set_use_tab_color_dark(True)
    return state


async def restore_tab_color(app: Any, state: TabColorState) -> None:
    session = app.get_session_by_id(state.session_id)
    if session is None:
        return
    profile = await session.async_get_profile()
    await profile.async_set_tab_color(state.tab_color)
    await profile.async_set_use_tab_color(state.use_tab_color)
    await profile.async_set_tab_color_light(state.tab_color_light)
    await profile.async_set_use_tab_color_light(state.use_tab_color_light)
    await profile.async_set_tab_color_dark(state.tab_color_dark)
    await profile.async_set_use_tab_color_dark(state.use_tab_color_dark)


async def set_attention_badge(session: Any) -> BadgeState:
    profile = await session.async_get_profile()
    state = BadgeState(
        session_id=session.session_id,
        badge_text=profile.badge_text,
        badge_color=profile.badge_color,
    )
    await profile.async_set_badge_color(attention_color())
    await profile.async_set_badge_text("ATTENTION")
    return state


async def restore_badge(app: Any, state: BadgeState) -> None:
    session = app.get_session_by_id(state.session_id)
    if session is None:
        return
    profile = await session.async_get_profile()
    await profile.async_set_badge_text(state.badge_text)
    await profile.async_set_badge_color(state.badge_color)


async def watch(connection: Any, requested_window_id: str | None, sound: bool, poll_seconds: float) -> None:
    if iterm2 is None:
        raise RuntimeError("Install the iTerm2 Python API with: python3 -m pip install --user iterm2")

    app = await iterm2.async_get_app(connection)
    if app is None:
        return
    window_id = requested_window_id
    if window_id is None:
        current = app.current_terminal_window
        if current is None:
            return
        window_id = current.window_id

    previous_titles: dict[str, str] = {}
    pending: dict[str, PendingAlert] = {}
    tab_colors: dict[str, TabColorState] = {}
    try:
        while True:
            await app.async_refresh()
            window = app.get_window_by_id(window_id)
            if window is None:
                return

            focused_session_id = None
            if window.current_tab and window.current_tab.current_session:
                focused_session_id = window.current_tab.current_session.session_id

            if focused_session_id in pending:
                alert = pending.pop(focused_session_id)
                await restore_badge(app, alert.badge)

            seen_sessions: set[str] = set()
            for position, tab in enumerate(window.tabs, start=1):
                for session in tab.sessions:
                    session_id = session.session_id
                    seen_sessions.add(session_id)
                    title = session.name
                    previous_title = previous_titles.get(session_id)
                    first_observation = previous_title is None
                    new_claude_attention = (
                        not first_observation
                        and needs_attention(title)
                        and not needs_attention(previous_title)
                    )
                    new_codex_attention = (
                        not first_observation
                        and codex_just_finished(previous_title, title)
                    )
                    is_focused = session_id == focused_session_id

                    if needs_attention(title) and first_observation and not is_focused and session_id not in pending:
                        pending[session_id] = PendingAlert(tab.tab_id, await set_attention_badge(session))
                    elif (new_claude_attention or new_codex_attention) and not is_focused:
                        if session_id not in pending:
                            pending[session_id] = PendingAlert(tab.tab_id, await set_attention_badge(session))
                        if sound:
                            ring(position)

                    previous_titles[session_id] = title

            pending_tab_ids = {alert.tab_id for alert in pending.values()}
            for tab in window.tabs:
                state = tab_colors.get(tab.tab_id)
                color_session = tab.current_session
                if tab.tab_id in pending_tab_ids and color_session is not None:
                    if state and state.session_id != color_session.session_id:
                        await restore_tab_color(app, state)
                        state = None
                    if state is None:
                        tab_colors[tab.tab_id] = await set_attention_color(color_session)
                elif state is not None:
                    await restore_tab_color(app, state)
                    tab_colors.pop(tab.tab_id, None)

            for session_id in set(previous_titles) - seen_sessions:
                previous_titles.pop(session_id, None)
                pending.pop(session_id, None)
            await asyncio.sleep(poll_seconds)
    finally:
        for state in tab_colors.values():
            await restore_tab_color(app, state)
        for alert in pending.values():
            await restore_badge(app, alert.badge)


def acquire_lock() -> Any | None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    lock.write(str(os.getpid()))
    lock.flush()
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", help="iTerm Python API window ID; defaults to the frontmost window")
    parser.add_argument("--no-sound", action="store_true", help="show visual alerts without local audio")
    parser.add_argument("--poll-seconds", type=float, default=POLL_SECONDS, help="poll interval in seconds")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than zero")
    if iterm2 is None:
        parser.error("install the iTerm2 Python API with: python3 -m pip install --user iterm2")

    lock = acquire_lock()
    if lock is None:
        return 0
    try:
        iterm2.run_until_complete(
            lambda connection: watch(connection, args.window, not args.no_sound, args.poll_seconds)
        )
    except KeyboardInterrupt:
        return 0
    finally:
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
