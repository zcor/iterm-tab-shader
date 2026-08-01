# iTerm Tab Shader

![Three Codex tier families from dark to bright, plus companion agent shades](docs/palette.svg)

iTerm Tab Shader gives long-running agent tabs a quiet, recognisable background
wash. Codex uses a tier-and-effort palette. Claude, Grok, Gemini, and Kimi get
their own companion shades. An optional iTerm2 monitor adds a native orange tab
highlight and `ATTENTION` badge when an agent finishes in another tab.

The project is for macOS, iTerm2, and interactive zsh. It is deliberately small:
a sourced zsh file, one optional Python monitor, no server, and no telemetry.

## The palette

Codex's tier names lend themselves to a useful visual mnemonic. Sol is solar
gold, Terra is forest green, and Luna is night-sky blue. Within a tier, a higher
reasoning effort uses a brighter shade. The shade communicates the selected
configuration, not a claim about model quality or cost.

| Codex tier | Minimal | Low | Medium | High | Xhigh or max |
| --- | --- | --- | --- | --- | --- |
| Luna | `#08111c` | `#0b1b2d` | `#102945` | `#143755` | `#194667` |
| Terra | `#07150c` | `#0a2113` | `#0e301c` | `#124025` | `#17502f` |
| Sol | `#1b1706` | `#292206` | `#382e08` | `#493b09` | `#5a490b` |

Grok defaults to deep cyan (`#082536`), Gemini to dark teal (`#0b2b2b`), and
Kimi to plum (`#291430`). Set `ITERM_TAB_SHADER_GROK_HEX`,
`ITERM_TAB_SHADER_GEMINI_HEX`, or `ITERM_TAB_SHADER_KIMI_HEX` to make a local
palette your own.

## Install

Clone the repository where the shell can find it, then source the zsh file from
`~/.zshrc`.

```zsh
git clone https://github.com/zcor/iterm-tab-shader.git ~/.config/iterm-tab-shader

# Add this line to ~/.zshrc
[[ -r "$HOME/.config/iterm-tab-shader/iterm-tab-shader.zsh" ]] && source "$HOME/.config/iterm-tab-shader/iterm-tab-shader.zsh"
```

Open a fresh iTerm tab or source the file. The `codex`, `claude`, `grok`,
`gemini`, and `kimi` commands are then wrapped only when they run inside iTerm2.
Outside iTerm2 they pass directly to the underlying command.

Run `iterm-tab-shader-demo` to walk through the fifteen Codex colours. Any key
moves to the next one and the last step restores iTerm's profile background.

### Live Codex model changes

The `codex` wrapper uses the launch arguments or `~/.codex/config.toml` for the
first shade. When available, it also reads only the model and effort fields from
the local Codex diagnostic SQLite database, scoped to the Codex process on the
current terminal. That lets a `/model` change update the tint without confusing
neighbouring tabs.

This is a local, read-only compatibility feature. It does not read prompts,
responses, credentials, or account data, and it makes no connection. The
database schema is not a public contract, so this extra tracking may need an
update after a Codex release. To keep the launch shade but disable tracking:

```zsh
export ITERM_TAB_SHADER_CODEX_LIVE=0
```

Unknown model names use neutral slate (`#23232a`).

### Claude statusline companion

Claude's statusline process cannot safely tint a terminal itself. The optional
companion reports only the displayed model name to a short-lived local file;
the shell wrapper owns the terminal escape sequence. Configure Claude Code's
statusline command to run:

```text
$HOME/.config/iterm-tab-shader/scripts/claude-statusline.sh
```

The script also prints a compact statusline. It receives Claude's normal
statusline JSON and writes no project path or prompt content to the tint file.

### Attention tabs

The attention monitor needs iTerm2's Python API in the Python interpreter that
will run it:

```zsh
python3 -m pip install --user iterm2
iterm-tab-shader-attention start
```

Start it from a shell in the iTerm window to watch. It polls that one window,
marks a Claude title that gains a leading `✳`, and notices a Codex tab whose
Braille work spinner disappears. A pending pane receives an `ATTENTION` badge
and its enclosing tab becomes orange. The tab returns to its prior colour only
after every pending pane in it has received focus.

The monitor never sends text, escape sequences, AppleScript input, or PTY bytes
to an agent terminal. It uses iTerm's session-local profile API for the tab and
badge. It can optionally make a local macOS `Funk` sound at a pitch based on the
displayed tab position. Use `iterm-tab-shader-attention start --no-sound` for a
silent monitor, or `stop` and `status` to manage it.

The title rules are observed behaviour, not a documented promise from either
agent. If a release changes them, inspect the iTerm titles before broadening the
detector.

## Safety and privacy

This repository contains no host rules, SSH wrappers, remote audio routes,
browser automation, credentials, cookies, tokens, personal paths, or captured
terminal output. Its runtime makes no network requests.

The monitor snapshots and restores only the iTerm profile settings that it
changes. It never changes the saved iTerm profile. Its cache contains generated
local sound files and a process lock. The Codex database read is optional and
read-only. See [SECURITY.md](SECURITY.md) before proposing integrations that
would widen those boundaries.

The original private terminal screenshot is intentionally not included. Even a
blurred capture can preserve project names, tab titles, and terminal details.
The palette image above is a deterministic SVG with no user data.

## Development

The runtime shell file has no package dependencies. The monitor requires Python
3.10 or newer and the optional `iterm2` package only when it is run inside
iTerm2.

```zsh
make check
```

`make check` runs the zsh palette checks, Python helper tests, compilation, and
a public-tree audit for secrets and accidental local paths.

Codex, Claude, Grok, Gemini, Kimi, and iTerm2 are trademarks of their respective
owners. This project is independent and is not affiliated with or endorsed by
any of them.

MIT licensed.
