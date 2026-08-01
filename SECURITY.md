# Security and privacy

iTerm Tab Shader is intentionally local-only. Do not add patches that access
browser state, credentials, cookies, keychains, private APIs, remote services,
or terminal transcript content.

The optional Codex watcher extracts only its local model and reasoning-effort
diagnostic fields. One broker holds a read-only SQLite connection and scopes
each update to the Codex process attached to its terminal. Per-tab registration
and state files contain only a process ID, model slug, and effort name. They are
stored in a mode-700 runtime directory and removed when the process exits. The
broker makes no network connection. The feature can be disabled with
`ITERM_TAB_SHADER_CODEX_LIVE=0`.

The attention monitor must never send terminal input. Do not add AppleScript
`write text`, direct PTY writes, `async_send_text`, `async_inject`, or any
equivalent mechanism. Those paths can corrupt an interactive agent session.
Use iTerm's session-local profile API for visual changes.

Please report a security concern through GitHub's private security-advisory
interface rather than a public issue.
