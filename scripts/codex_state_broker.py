#!/usr/bin/env python3
"""Share one read-only Codex settings feed across iTerm tab watchers."""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import signal
import sqlite3
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TARGET = "codex_core::session::handlers"
THREAD_SETTINGS = "op: ThreadSettings { thread_settings: ThreadSettingsOverrides"
SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")
PID_FROM_UUID = re.compile(r"^pid:(\d+):")
MODEL = re.compile(r'model: Some\("([^"\r\n]+)"\)')
EFFORT = re.compile(r"effort: Some\(Some\(([A-Za-z]+)\)\)")
SEED_LOOKBACK_ROWS = 100_000


@dataclass(frozen=True)
class Settings:
    model: str = ""
    effort: str = ""

    def merged(self, other: "Settings") -> "Settings":
        return Settings(other.model or self.model, other.effort or self.effort)

    @property
    def empty(self) -> bool:
        return not self.model and not self.effort

    def serialize(self) -> str:
        return f"{self.model}|{self.effort}\n"


def parse_pid(process_uuid: str | None) -> int | None:
    match = PID_FROM_UUID.match(process_uuid or "")
    return int(match.group(1)) if match else None


def parse_settings(fragment: str | None) -> Settings:
    text = fragment or ""
    model_match = MODEL.search(text)
    effort_match = EFFORT.search(text)
    return Settings(
        model_match.group(1) if model_match else "",
        effort_match.group(1).lower() if effort_match else "",
    )


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
        timeout=0.25,
    )
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 250")
    return connection


def maximum_id(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT coalesce(max(id), 0) FROM logs").fetchone()
    return int(row[0])


def settings_fragment_sql() -> str:
    return """
        CASE
            WHEN instr(feedback_log_body, ', model: ') > 0
            THEN substr(
                feedback_log_body,
                instr(feedback_log_body, ', model: ') + 2,
                192
            )
            ELSE ''
        END
    """


def thread_settings_predicate_sql() -> str:
    return """
        instr(feedback_log_body, ?) = instr(feedback_log_body, 'op: ')
        AND instr(feedback_log_body, ?) BETWEEN 1 AND 256
    """


def latest_settings(connection: sqlite3.Connection, pid: int) -> Settings:
    newest_id = maximum_id(connection)
    rows = connection.execute(
        f"""
        SELECT {settings_fragment_sql()}
        FROM logs
        WHERE id > ?
          AND process_uuid LIKE ?
          AND target = ?
          AND {thread_settings_predicate_sql()}
        ORDER BY id DESC
        LIMIT 128
        """,
        (
            max(0, newest_id - SEED_LOOKBACK_ROWS),
            f"pid:{pid}:%",
            TARGET,
            THREAD_SETTINGS,
            THREAD_SETTINGS,
        ),
    )
    found = Settings()
    for (fragment,) in reversed(rows.fetchall()):
        found = found.merged(parse_settings(fragment))
    return found


def events_after(
    connection: sqlite3.Connection, last_id: int
) -> tuple[int, list[tuple[int, int, Settings]]]:
    newest_id = maximum_id(connection)
    rows = connection.execute(
        f"""
        SELECT id, process_uuid, {settings_fragment_sql()}
        FROM logs
        WHERE id > ?
          AND id <= ?
          AND target = ?
          AND {thread_settings_predicate_sql()}
        ORDER BY id
        """,
        (last_id, newest_id, TARGET, THREAD_SETTINGS, THREAD_SETTINGS),
    )
    events: list[tuple[int, int, Settings]] = []
    for row_id, process_uuid, fragment in rows:
        pid = parse_pid(process_uuid)
        settings = parse_settings(fragment)
        if pid is not None and not settings.empty:
            events.append((int(row_id), pid, settings))
    return newest_id, events


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_registration(path: Path) -> int | None:
    if path.is_symlink() or not SAFE_KEY.fullmatch(path.stem):
        return None
    try:
        raw = path.read_text(encoding="ascii")[:64].strip()
    except (OSError, UnicodeError):
        return None
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def unlink_if_registration_matches(path: Path, pid: int) -> None:
    if read_registration(path) != pid:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def registrations_in(directory: Path) -> dict[str, int]:
    active: dict[str, int] = {}
    try:
        paths: Iterable[Path] = directory.glob("*.pid")
        for path in paths:
            pid = read_registration(path)
            if pid is None:
                continue
            if pid_is_alive(pid):
                active[path.stem] = pid
            else:
                unlink_if_registration_matches(path, pid)
    except OSError:
        return active
    return active


def atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def remove_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def remove_unregistered_states(directory: Path, active_keys: set[str]) -> None:
    try:
        for path in directory.glob("*.state"):
            if SAFE_KEY.fullmatch(path.stem) and path.stem not in active_keys:
                remove_state(path)
    except OSError:
        pass


def remove_old_temporary_files(directory: Path, age_seconds: float = 60.0) -> None:
    cutoff = time.time() - age_seconds
    try:
        for path in directory.glob("*.tmp"):
            try:
                if path.lstat().st_mtime < cutoff:
                    path.unlink()
            except FileNotFoundError:
                pass
    except OSError:
        pass


def database_identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_dev, stat.st_ino


class Broker:
    def __init__(
        self,
        database: Path,
        runtime_directory: Path,
        poll_seconds: float,
        idle_seconds: float,
    ) -> None:
        self.database = database
        self.runtime_directory = runtime_directory
        self.registration_directory = runtime_directory / "registrations"
        self.state_directory = runtime_directory / "states"
        self.poll_seconds = max(0.1, poll_seconds)
        self.idle_seconds = max(1.0, idle_seconds)
        self.connection: sqlite3.Connection | None = None
        self.identity: tuple[int, int] | None = None
        self.last_id = 0
        self.registrations: dict[str, int] = {}
        self.settings: dict[str, Settings] = {}
        self.running = True

    def stop(self, _signum: int, _frame: object) -> None:
        self.running = False

    def connect(self) -> bool:
        identity = database_identity(self.database)
        if identity is None:
            return False
        if self.connection is not None and identity == self.identity:
            return True
        if self.connection is not None:
            self.connection.close()
        self.connection = connect_database(self.database)
        self.identity = identity
        self.last_id = maximum_id(self.connection)
        for key, pid in self.registrations.items():
            seeded = latest_settings(self.connection, pid)
            self.update_state(key, seeded)
        return True

    def update_state(self, key: str, incoming: Settings) -> None:
        current = self.settings.get(key, Settings())
        updated = current.merged(incoming)
        if updated == current or updated.empty:
            return
        self.settings[key] = updated
        atomic_write(self.state_directory / f"{key}.state", updated.serialize())

    def refresh_registrations(self) -> None:
        current = registrations_in(self.registration_directory)
        remove_unregistered_states(self.state_directory, set(current))
        remove_old_temporary_files(self.registration_directory)
        remove_old_temporary_files(self.state_directory)
        removed = self.registrations.keys() - current.keys()
        changed = {
            key
            for key, pid in current.items()
            if self.registrations.get(key) != pid
        }
        for key in removed | changed:
            self.settings.pop(key, None)
            remove_state(self.state_directory / f"{key}.state")
        self.registrations = current
        if self.connection is not None:
            for key in changed:
                self.update_state(key, latest_settings(self.connection, current[key]))

    def poll_events(self) -> None:
        if self.connection is None:
            return
        self.last_id, events = events_after(self.connection, self.last_id)
        keys_by_pid: dict[int, list[str]] = {}
        for key, pid in self.registrations.items():
            keys_by_pid.setdefault(pid, []).append(key)
        for _row_id, pid, settings in events:
            for key in keys_by_pid.get(pid, []):
                self.update_state(key, settings)

    def run(self) -> None:
        idle_since = time.monotonic()
        while self.running:
            try:
                self.refresh_registrations()
                if self.registrations:
                    idle_since = time.monotonic()
                elif time.monotonic() - idle_since >= self.idle_seconds:
                    break
                if self.connect():
                    self.poll_events()
            except (OSError, sqlite3.Error):
                if self.connection is not None:
                    self.connection.close()
                self.connection = None
                self.identity = None
            time.sleep(self.poll_seconds)
        if self.connection is not None:
            self.connection.close()


def ensure_private_directory(path: Path, *, parents: bool = False) -> None:
    path.mkdir(parents=parents, exist_ok=True, mode=0o700)
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise OSError(f"runtime path is not a directory: {path}")
    if details.st_uid != os.geteuid():
        raise PermissionError(f"runtime directory is not owned by this user: {path}")
    os.chmod(path, 0o700)


def prepare_runtime(path: Path) -> tuple[Path, Path, Path]:
    ensure_private_directory(path, parents=True)
    registration_directory = path / "registrations"
    state_directory = path / "states"
    ensure_private_directory(registration_directory)
    ensure_private_directory(state_directory)
    return path / "broker.lock", path / "broker.pid", state_directory


def remove_own_pid_file(path: Path, pid: int) -> None:
    try:
        if path.read_text(encoding="ascii").strip() == str(pid):
            path.unlink()
    except (FileNotFoundError, OSError, UnicodeError):
        pass


def run_broker(args: argparse.Namespace) -> int:
    os.umask(0o077)
    runtime_directory = Path(os.path.abspath(args.runtime_dir.expanduser()))
    lock_path, pid_path, _state_directory = prepare_runtime(runtime_directory)
    lock_descriptor = os.open(
        lock_path,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.fchmod(lock_descriptor, 0o600)
    lock = os.fdopen(lock_descriptor, "a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return 0

    pid = os.getpid()
    atomic_write(pid_path, f"{pid}\n")
    broker = Broker(
        args.database.expanduser().resolve(),
        runtime_directory,
        args.poll_seconds,
        args.idle_seconds,
    )
    signal.signal(signal.SIGTERM, broker.stop)
    signal.signal(signal.SIGINT, broker.stop)
    try:
        broker.run()
    finally:
        remove_own_pid_file(pid_path, pid)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--idle-seconds", type=float, default=60.0)
    return parser


def main() -> int:
    return run_broker(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
