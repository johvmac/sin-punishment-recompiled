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

# --- Reap strays before starting -------------------------------------------
# A previous run whose PARENT was killed (session ended, credits ran out, Ctrl-C)
# leaves the game running forever, because the deadline used to live only in
# this script's `sleep`. On 2026-08-18 that orphaned a process for 2h36m and
# nothing reported it. `comm` is truncated to 15 chars by the kernel, so match
# "SinPunishmentRe" -- and note this can never match our own shell, unlike
# `pkill -f`, which kills the very command line running it.
STALE=$(ps -eo pid,comm --no-headers | awk '$2=="SinPunishmentRe"{print $1}')
if [[ -n "$STALE" ]]; then
    echo "[run_game] reaping stale game process(es): $STALE" >&2
    # shellcheck disable=SC2086
    kill -9 $STALE 2>/dev/null || true
    sleep 1
fi

env SP_AUTOSTART=1 "$@" "$BIN" > "$OUT" 2>&1 &
PID=$!

# --- Detached hard-deadline watchdog ---------------------------------------
# `setsid` puts this in its OWN session, so killing this script -- or the whole
# terminal, or the agent session -- does not take it with us. It is the only
# guarantee that survives the parent dying, which is the failure mode that
# actually happened. It re-checks `comm` before firing so a recycled PID is
# never killed by mistake.
HARD=$(( SECS + 15 ))
setsid bash -c "
    sleep $HARD
    if [ \"\$(ps -o comm= -p $PID 2>/dev/null)\" = 'SinPunishmentRe' ]; then
        kill -9 -- -$PID 2>/dev/null || kill -9 $PID 2>/dev/null
    fi
" < /dev/null > /dev/null 2>&1 &
WATCHDOG=$!

sleep "$SECS"

# Kill the process group (game + any children), by PID. SIGKILL only.
kill -9 -- "-$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
sleep 1

# Read-only verification. pgrep never kills, so matching our own argv here is
# harmless -- subtract this script's own shell from the count.
kill "$WATCHDOG" 2>/dev/null || true   # normal path won; retire the watchdog

# Count by `comm`, not `pgrep -f`: the latter also matches this script's own
# command line, which is how a "leftover" can be reported that does not exist.
LEFT=$(ps -eo comm --no-headers | grep -c '^SinPunishmentRe$' || true)

printf '[run_game] ran %ss  pid=%s  log=%s (%s lines)  leftover=%s\n' \
    "$SECS" "$PID" "$OUT" "$(wc -l < "$OUT" 2>/dev/null || echo 0)" "$LEFT"

if [[ "$LEFT" -gt 0 ]]; then
    echo "[run_game] WARNING: $LEFT process(es) survived SIGKILL -- investigate" >&2
fi
exit 0
