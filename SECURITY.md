# Security and privacy

iTerm Tab Shader is intentionally local-only. Do not add patches that access
browser state, credentials, cookies, keychains, private APIs, remote services,
or terminal transcript content.

The optional Codex watcher reads only its local model and reasoning-effort
diagnostic fields. It uses a read-only SQLite connection, scopes the lookup to
the Codex process attached to the active terminal, and makes no connection.
The feature can be disabled with `ITERM_TAB_SHADER_CODEX_LIVE=0`.

The attention monitor must never send terminal input. Do not add AppleScript
`write text`, direct PTY writes, `async_send_text`, `async_inject`, or any
equivalent mechanism. Those paths can corrupt an interactive agent session.
Use iTerm's session-local profile API for visual changes.

Please report a security concern through GitHub's private security-advisory
interface rather than a public issue.
