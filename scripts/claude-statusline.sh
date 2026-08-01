#!/bin/sh
# Optional Claude Code statusline companion for iTerm Tab Shader.
# It reports a display model to the shell-side watcher; it never emits OSC.

input=$(cat)
model=$(printf '%s' "$input" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, OSError):
    payload = {}

model = (payload.get("model") or {}).get("display_name") or ""
context = payload.get("context_window") or {}
used = context.get("used_percentage")
workspace = (payload.get("workspace") or {}).get("current_dir") or ""
name = workspace.rstrip("/").rsplit("/", 1)[-1] if workspace else "-"
print("\x1f".join((model, "" if used is None else str(used), name)))
' 2>/dev/null)

IFS="$(printf '\037')" read -r model percentage directory <<EOF
$model
EOF

state_dir="${ITERM_TAB_SHADER_CLAUDE_STATE_DIR:-${TMPDIR:-/tmp}/iterm-tab-shader-claude}"
if [ -n "${ITERM_SESSION_ID:-}" ] && [ -n "$model" ]; then
    mkdir -p "$state_dir"
    session_key=$(printf '%s' "$ITERM_SESSION_ID" | tr -c 'A-Za-z0-9._-' '_')
    printf '%s' "$model" > "$state_dir/$session_key"
fi

case "$model" in
    Fable*) icon='◆' ;;
    Opus*) icon='●' ;;
    Sonnet*) icon='▲' ;;
    Haiku*) icon='■' ;;
    *) icon='○' ;;
esac

output="$icon ${model:--}  ${directory:--}"
if [ -n "$percentage" ]; then
    output="$output  ${percentage}%"
fi
printf '%s' "$output"
