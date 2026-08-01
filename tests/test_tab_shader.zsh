#!/bin/zsh
set -eu

TERM_PROGRAM=iTerm.app
source "${0:A:h:h}/iterm-tab-shader.zsh"

assert_equal() {
    if [[ "$1" != "$2" ]]; then
        print -u2 "expected '$1', got '$2'"
        exit 1
    fi
}

assert_equal 08111c "$(_its_codex_bg gpt-5.6-luna minimal)"
assert_equal 102945 "$(_its_codex_bg gpt-5.6-luna medium)"
assert_equal 194667 "$(_its_codex_bg gpt-5.6-luna xhigh)"
assert_equal 07150c "$(_its_codex_bg gpt-5.6-terra minimal)"
assert_equal 0e301c "$(_its_codex_bg gpt-5.6-terra medium)"
assert_equal 17502f "$(_its_codex_bg gpt-5.6-terra xhigh)"
assert_equal 1b1706 "$(_its_codex_bg gpt-5.6-sol minimal)"
assert_equal 382e08 "$(_its_codex_bg gpt-5.6-sol medium)"
assert_equal 5a490b "$(_its_codex_bg gpt-5.6-sol max)"
assert_equal 23232a "$(_its_codex_bg gpt-5.5-other medium)"
assert_equal 3b121c "$(_its_claude_bg Opus)"
assert_equal 23232a "$(_its_claude_bg unknown)"

print 'tab shader palette tests passed'
