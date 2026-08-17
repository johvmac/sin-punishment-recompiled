#!/usr/bin/env bash
# Run the game for N seconds, capture its output, and GUARANTEE it dies.
#
# Usage: scripts/run_game.sh [seconds] [logfile] [extra env assignments...]
#   scripts/run_game.sh 20 /tmp/run.log
#   scripts/run_game.sh 20 /tmp/run.log SNP_TRACE=1
#
# Why this script exists (two real bugs, both cost hours -- see the playbook):
#
# 1. NEVER `pkill -f <binary>`. `pkill -f` matches full command lines,
#    including the command line of the shell running the pkill. Any command
#    that both mentions the binary path and pkills by name kills its own
#    shell. It fails silently and misleadingly: no output at all, and a
#    nonzero exit that looks like the *game* failed. The `[R]` bracket trick
#    is NOT sufficient -- it only stops the pattern matching itself, not the
#    binary path appearing elsewhere on the same line.
#    => This script kills by PID only.
#
# 2. NEVER rely on SIGTERM (plain `timeout N`). SDL2 installs its own
#    SIGTERM handler by default (SDL_HINT_NO_SIGNAL_HANDLERS is not set) and
#    converts it into an SDL_QUIT *event*. A blocked game thread -- the
#    normal case while debugging -- never processes that event, so the
#    process survives, the window lingers, and the WM eventually pops a
#    "not responding / force quit" dialog at the user.
#    => This script uses SIGKILL, which cannot be caught.
set -uo pipefail

SECS="${1:-20}"
OUT="${2:-/tmp/game_run.log}"
shift 2 2>/dev/null || true

cd "$(dirname "$0")/.." || exit 1
BIN=./build/SinPunishmentRecompiled

if [[ ! -x "$BIN" ]]; then
    echo "[run_game] ERROR: $BIN not found or not executable" >&2
    exit 1
fi

env SP_AUTOSTART=1 "$@" "$BIN" > "$OUT" 2>&1 &
PID=$!

sleep "$SECS"

# Kill the process group (game + any children), by PID. SIGKILL only.
kill -9 -- "-$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
sleep 1

# Read-only verification. pgrep never kills, so matching our own argv here is
# harmless -- subtract this script's own shell from the count.
LEFT=$(pgrep -f 'SinPunishmentRecompiled' 2>/dev/null | grep -v "^$$\$" | wc -l)

printf '[run_game] ran %ss  pid=%s  log=%s (%s lines)  leftover=%s\n' \
    "$SECS" "$PID" "$OUT" "$(wc -l < "$OUT" 2>/dev/null || echo 0)" "$LEFT"

if [[ "$LEFT" -gt 0 ]]; then
    echo "[run_game] WARNING: $LEFT process(es) survived SIGKILL -- investigate" >&2
fi
exit 0
