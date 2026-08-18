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

# --- Display isolation (default ON) ----------------------------------------
# The session is Wayland + GNOME Shell, so the game runs under XWayland, and
# mutter THROTTLES FRAME CALLBACKS for an unfocused or occluded window. That
# produces the exact signature that wasted a large part of 2026-08-18: gfx_tasks
# collapse to +1..3/s while `other` holds a perfect +30/s, because the game's
# own threads are fine and only PRESENTATION is being starved. Measured, with
# the user deliberately unfocusing the window to confirm it.
#
# Effect on measurement (3 runs per arm):
#   real display, unfocused : 770 / 1734 / 307 gfx  -- all DEGRADED
#   nested Xephyr           : 1302 / 1301 / 1301    -- all CLEAN
# A spread of 1 versus a spread of 1427. Every build-to-build comparison made
# on the real display is suspect for this reason.
#
# So isolation is the default: a measurement run must not depend on where the
# user's mouse is. Pass SNP_VISIBLE=1 when the run is meant to be WATCHED --
# milestone confirmation has to happen on the real display.
XEPHYR_PID=""
if [[ -z "${SNP_VISIBLE:-}" ]] && command -v Xephyr >/dev/null 2>&1; then
    ISO_DISPLAY=":${SNP_ISO_DISPLAY:-7}"
    Xephyr "$ISO_DISPLAY" -screen 1280x720 -nolisten tcp > /dev/null 2>&1 &
    XEPHYR_PID=$!
    sleep 2
    if kill -0 "$XEPHYR_PID" 2>/dev/null; then
        export DISPLAY="$ISO_DISPLAY"
        echo "[run_game] isolated on $ISO_DISPLAY (Xephyr pid $XEPHYR_PID) -- pass SNP_VISIBLE=1 to watch it instead" >&2
    else
        XEPHYR_PID=""
        echo "[run_game] WARNING: Xephyr failed to start; running on the real display, which is throttled when unfocused" >&2
    fi
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

# Wait up to SECS, but NOTICE if the game exits on its own. The old version
# slept unconditionally and then reported "ran ${SECS}s" either way -- so a
# crash at frame 18 of a 300s run looked exactly like a healthy full-length
# run, and the probe log just looked mysteriously short. An early exit is a
# RESULT; report it, with the exit code, and say how far it got.
EARLY=""
RC=""
for (( i = 0; i < SECS; i++ )); do
    if ! kill -0 "$PID" 2>/dev/null; then
        wait "$PID" 2>/dev/null
        RC=$?
        EARLY=$i
        break
    fi
    sleep 1
done

if [[ -n "$EARLY" ]]; then
    printf '[run_game] GAME EXITED ON ITS OWN after %ss of %ss (exit code %s) -- the run did NOT reach its deadline\n' \
        "$EARLY" "$SECS" "$RC" >&2
    case "$RC" in
        139) echo "[run_game]   rc=139 is SIGSEGV" >&2 ;;
        134) echo "[run_game]   rc=134 is SIGABRT" >&2 ;;
        136) echo "[run_game]   rc=136 is SIGFPE"  >&2 ;;
    esac
fi

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

# Kill the nested server by PID, same discipline as the game itself.
if [[ -n "$XEPHYR_PID" ]]; then
    kill -9 "$XEPHYR_PID" 2>/dev/null || true
    wait "$XEPHYR_PID" 2>/dev/null
fi

# Controller input CONTAMINATES a run: the window takes focus when it appears,
# and the frontend binds ordinary letters (A/S/D/W/E/I/J/K/L/Q/R/SPACE/RETURN),
# so typing anywhere while a run is up can press N64 buttons. Verified 2026-08-18:
# injected input made a run SIGSEGV. A run with input in it is not comparable to
# one without, so say so loudly rather than leaving it to be noticed.
INPUT=$(grep -c '^\[input\] runtime' "$OUT" 2>/dev/null || true)
INPUT=${INPUT:-0}

# --- Validity verdict ------------------------------------------------------
# T22: run-to-run variance dominates, and three separate mechanisms were blamed
# for it before that was recognised. The one reliable per-run filter is the gfx
# rate -- a healthy attract run holds +30/s, and every anomalous run so far has
# shown it collapsed. Deciding this by eye, run by run, is exactly the kind of
# judgement that gets skipped when in a hurry, so the script decides it.
#
# A DEGRADED run is not evidence about a build. It is not comparable to a CLEAN
# one and must not be cited as though it were.
GFX_LINE=$(grep '^\[heartbeat\]' "$OUT" 2>/dev/null | tail -1)
GFX_TOTAL=$(sed -nE 's/.*gfx_tasks=([0-9]+).*/\1/p' <<< "$GFX_LINE")
GFX_RATE=$(sed -nE 's/.*gfx_tasks=[0-9]+ +\+([0-9]+).*/\1/p' <<< "$GFX_LINE")

VERDICT="CLEAN"
if   [[ "$INPUT" -gt 0 ]];                     then VERDICT="CONTAMINATED"
elif [[ -n "$EARLY" ]];                        then VERDICT="CRASHED"
elif [[ -z "$GFX_LINE" ]];                     then VERDICT="UNKNOWN(no SNP_HEARTBEAT)"
elif [[ "${GFX_RATE:-0}" -lt 25 ]];            then VERDICT="DEGRADED"
fi

printf '[run_game] ran %ss  pid=%s  log=%s (%s lines)  leftover=%s  input_events=%s  VERDICT=%s\n' \
    "$SECS" "$PID" "$OUT" "$(wc -l < "$OUT" 2>/dev/null || echo 0)" "$LEFT" "$INPUT" "$VERDICT"

case "$VERDICT" in
  DEGRADED)
    echo "[run_game] NOT COMPARABLE: gfx ended at +${GFX_RATE:-?}/s (healthy holds +30). This run is not evidence about the build (T22)." >&2 ;;
  "UNKNOWN(no SNP_HEARTBEAT)")
    echo "[run_game] No liveness signal — pass SNP_HEARTBEAT=1 or the run cannot be judged valid (T22)." >&2 ;;
esac

if [[ "$INPUT" -gt 0 ]]; then
    echo "[run_game] WARNING: $INPUT controller-input event(s) during this run -- it was NOT clean." >&2
    grep -m3 '^\[input\] runtime' "$OUT" | sed 's/^/[run_game]   /' >&2
    echo "[run_game]   Treat this run as contaminated and repeat it." >&2
fi

if [[ "$LEFT" -gt 0 ]]; then
    echo "[run_game] WARNING: $LEFT process(es) survived SIGKILL -- investigate" >&2
fi

# --- Append one line per run to docs/run-log.tsv ---------------------------
# Every field below was already computed and then thrown away, which is exactly
# why "how many runs support this claim?" was unanswerable all through
# 2026-08-18 (T22: run-to-run variance misattributed three times, to run length,
# probe cost, and an env var that was a no-op). With this, that question is a
# grep. gfx rate is the per-run validity filter: a healthy attract run holds
# +30/s, and a run that does not is not comparable to one that does.
RUNLOG="$(dirname "$0")/../docs/run-log.tsv"
if [[ ! -f "$RUNLOG" ]]; then
    printf 'ts\tsecs_req\tsecs_actual\trc\tinput\tleftover\tgfx_total\tgfx_rate\tverdict\tlog\tenv\n' > "$RUNLOG"
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "$SECS" "${EARLY:-$SECS}" "${RC:-0}" "$INPUT" "$LEFT" \
    "${GFX_TOTAL:-NA}" "${GFX_RATE:-NA}" "$VERDICT" "$(basename "$OUT")" "${*:-none}" >> "$RUNLOG"

exit 0
