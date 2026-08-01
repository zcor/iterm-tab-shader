# iTerm Tab Shader
#
# Source this file from an interactive zsh session running in iTerm2. It keeps
# a tab's background in a recognisable family of very dark colours while an
# agent CLI is active. It makes no network requests.

[[ "${TERM_PROGRAM:-}" == "iTerm.app" ]] || return 0

typeset -g ITERM_TAB_SHADER_HOME="${ITERM_TAB_SHADER_HOME:-${${(%):-%x}:A:h}}"
typeset -g ITERM_TAB_SHADER_CACHE_DIR="${ITERM_TAB_SHADER_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/Library/Caches}/iterm-tab-shader}"
typeset -g ITERM_TAB_SHADER_CLAUDE_STATE_DIR="${ITERM_TAB_SHADER_CLAUDE_STATE_DIR:-${TMPDIR:-/tmp}/iterm-tab-shader-claude}"

_its_bg_set() {
    printf '\033]11;#%s\a' "${1#\#}" > /dev/tty
}

_its_bg_reset() {
    printf '\033]111\a' > /dev/tty
}

_its_codex_bg() {
    local model="$1"
    local effort="${2:-medium}"

    case "$model" in
        *luna*)
            case "$effort" in
                minimal|none) print -r -- 08111c ;;
                low)          print -r -- 0b1b2d ;;
                medium)       print -r -- 102945 ;;
                high)         print -r -- 143755 ;;
                xhigh|max)    print -r -- 194667 ;;
                *)            print -r -- 102945 ;;
            esac ;;
        *terra*)
            case "$effort" in
                minimal|none) print -r -- 07150c ;;
                low)          print -r -- 0a2113 ;;
                medium)       print -r -- 0e301c ;;
                high)         print -r -- 124025 ;;
                xhigh|max)    print -r -- 17502f ;;
                *)            print -r -- 0e301c ;;
            esac ;;
        *sol*)
            case "$effort" in
                minimal|none) print -r -- 1b1706 ;;
                low)          print -r -- 292206 ;;
                medium)       print -r -- 382e08 ;;
                high)         print -r -- 493b09 ;;
                xhigh|max)    print -r -- 5a490b ;;
                *)            print -r -- 382e08 ;;
            esac ;;
        *) print -r -- 23232a ;;
    esac
}

_its_claude_bg() {
    case "$1" in
        Fable*)  print -r -- 301547 ;;
        Opus*)   print -r -- 3b121c ;;
        Sonnet*) print -r -- 3b1d0c ;;
        Haiku*)  print -r -- 242027 ;;
        *)       print -r -- 23232a ;;
    esac
}

_its_command_with_bg() {
    local colour="$1"
    shift
    _its_bg_set "$colour"
    command "$@"
    local status=$?
    _its_bg_reset
    return "$status"
}

_its_config_value() {
    local path="$1"
    local key="$2"
    [[ -r "$path" ]] || return 0
    sed -nE "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*\"([^\"]+)\".*/\1/p" "$path" | head -1
}

_its_read_codex_event() {
    local database="$1"
    local pid="$2"
    local kind="$3"
    local row=""
    local parsed=""

    [[ -r "$database" && "$pid" == <-> ]] || return 0
    case "$kind" in
        model)
            row="$(sqlite3 -readonly -noheader "$database" "select feedback_log_body from logs where process_uuid like 'pid:${pid}:%' and target = 'codex_core::session::handlers' and feedback_log_body like '%model: Some(\"%' order by id desc limit 1;" 2>/dev/null)"
            parsed="$(printf '%s\n' "$row" | sed -nE 's/.*model: Some\("([^\"]+)"\).*/\1/p')" ;;
        effort)
            row="$(sqlite3 -readonly -noheader "$database" "select feedback_log_body from logs where process_uuid like 'pid:${pid}:%' and target = 'codex_core::session::handlers' and feedback_log_body like '%effort: Some(Some(%' order by id desc limit 1;" 2>/dev/null)"
            parsed="$(printf '%s\n' "$row" | sed -nE 's/.*effort: Some\(Some\(([A-Za-z]+)\)\).*/\1/p')" ;;
    esac
    print -r -- "$parsed"
}

codex() {
    [[ -n "${ITERM_SESSION_ID:-}" ]] || { command codex "$@"; return $?; }

    local config_path="${ITERM_TAB_SHADER_CODEX_CONFIG:-$HOME/.codex/config.toml}"
    local database="${ITERM_TAB_SHADER_CODEX_LOG_DB:-$HOME/.codex/logs_2.sqlite}"
    local model=""
    local effort=""
    local colour=""
    local tty_path=""
    local watcher=""
    local index

    for (( index = 1; index <= $#; index++ )); do
        case "${argv[index]}" in
            -m|--model)
                (( index++ ))
                model="${argv[index]:-}" ;;
            --model=*) model="${argv[index]#--model=}" ;;
            -c|--config)
                (( index++ ))
                case "${argv[index]:-}" in
                    model_reasoning_effort=*) effort="${argv[index]#*=}" ;;
                esac ;;
            model_reasoning_effort=*) effort="${argv[index]#*=}" ;;
        esac
    done

    [[ -n "$model" ]] || model="$(_its_config_value "$config_path" model)"
    [[ -n "$effort" ]] || effort="$(_its_config_value "$config_path" model_reasoning_effort)"
    effort="${effort//\"/}"
    [[ -n "$effort" ]] || effort="medium"
    colour="$(_its_codex_bg "$model" "$effort")"
    _its_bg_set "$colour"

    if [[ "${ITERM_TAB_SHADER_CODEX_LIVE:-1}" != "0" && -r "$database" ]] && command -v lsof >/dev/null && command -v sqlite3 >/dev/null; then
        tty_path="$(tty)"
        (
            local live_model="$model"
            local live_effort="$effort"
            local seen="$model:$effort"
            local pid=""
            local next_model=""
            local next_effort=""
            while true; do
                [[ -n "$pid" ]] || pid="$(lsof -t -a -c codex "$tty_path" 2>/dev/null | head -1)"
                if [[ "$pid" == <-> ]]; then
                    next_model="$(_its_read_codex_event "$database" "$pid" model)"
                    next_effort="$(_its_read_codex_event "$database" "$pid" effort)"
                    [[ -n "$next_model" ]] && live_model="$next_model"
                    [[ -n "$next_effort" ]] && live_effort="${(L)next_effort}"
                fi
                if [[ "$live_model:$live_effort" != "$seen" ]]; then
                    seen="$live_model:$live_effort"
                    _its_bg_set "$(_its_codex_bg "$live_model" "$live_effort")"
                fi
                sleep 1
            done
        ) &!
        watcher=$!
    fi

    command codex "$@"
    local status=$?
    [[ -n "$watcher" ]] && kill "$watcher" 2>/dev/null
    _its_bg_reset
    return "$status"
}

claude() {
    [[ -n "${ITERM_SESSION_ID:-}" ]] || { command claude "$@"; return $?; }

    local session_key="${ITERM_SESSION_ID//[^A-Za-z0-9._-]/_}"
    local state_file="$ITERM_TAB_SHADER_CLAUDE_STATE_DIR/$session_key"
    local watcher=""
    mkdir -p "$ITERM_TAB_SHADER_CLAUDE_STATE_DIR"
    : > "$state_file"
    (
        local last=""
        local model=""
        while [[ -e "$state_file" ]]; do
            model="$(<"$state_file")"
            if [[ -n "$model" && "$model" != "$last" ]]; then
                last="$model"
                _its_bg_set "$(_its_claude_bg "$model")"
            fi
            sleep 1
        done
    ) &!
    watcher=$!

    command claude "$@"
    local status=$?
    kill "$watcher" 2>/dev/null
    rm -f "$state_file"
    _its_bg_reset
    return "$status"
}

gemini() { _its_command_with_bg "${ITERM_TAB_SHADER_GEMINI_HEX:-0b2b2b}" gemini "$@"; }
grok()   { _its_command_with_bg "${ITERM_TAB_SHADER_GROK_HEX:-082536}" grok "$@"; }
kimi()   { _its_command_with_bg "${ITERM_TAB_SHADER_KIMI_HEX:-291430}" kimi "$@"; }

iterm-tab-shader-attention() {
    local lock_path="$ITERM_TAB_SHADER_CACHE_DIR/attention.lock"
    local pid=""
    local wait_count=""
    case "${1:-start}" in
        start)
            shift
            command python3 "$ITERM_TAB_SHADER_HOME/scripts/iterm_attention.py" "$@" &! ;;
        stop)
            [[ -r "$lock_path" ]] && pid="$(<"$lock_path")"
            if [[ "$pid" == <-> ]] && kill -0 "$pid" 2>/dev/null; then
                kill -INT "$pid" 2>/dev/null
                for wait_count in {1..40}; do
                    kill -0 "$pid" 2>/dev/null || break
                    sleep 0.05
                done
            fi ;;
        status)
            [[ -r "$lock_path" ]] && pid="$(<"$lock_path")"
            if [[ "$pid" == <-> ]] && kill -0 "$pid" 2>/dev/null; then
                print "attention monitor running (pid $pid)"
            else
                print "attention monitor stopped"
            fi ;;
        *)
            print -u2 "usage: iterm-tab-shader-attention [start|stop|status]"
            return 2 ;;
    esac
}

iterm-tab-shader-demo() {
    local model effort colour
    for model in luna terra sol; do
        for effort in minimal low medium high xhigh; do
            colour="$(_its_codex_bg "gpt-5.6-$model" "$effort")"
            _its_bg_set "$colour"
            printf 'Codex %-5s %-7s #%s  (any key for next)\n' "$model" "$effort" "$colour"
            read -k1 -s
        done
    done
    _its_bg_reset
    print "reset to the iTerm profile default"
}
