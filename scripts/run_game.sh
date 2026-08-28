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

# --- help (T37) ------------------------------------------------------------
# Prints this script's own header block. Added after `route.py --help` was
# silently ignored and fell through to a state-mutating default.
case "${1:-}" in
    -h|--help)
        sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'
        exit 0 ;;
esac

SECS="${1:-20}"
OUT="${2:-/tmp/game_run.log}"
shift 2 2>/dev/null || true

cd "$(dirname "$0")/.." || exit 1
BIN=./build/SinPunishmentRecompiled

# --- The output path must be plausible (A312) ------------------------------
# On 2026-08-22 this script was invoked with TWO EXTRA LEADING TOKENS ahead of
# the intended command. Nothing noticed: SECS took the first, and **$2 -- the
# run log -- silently became a path ending in `run_game.sh`.** The launch
# redirect is `> "$OUT"`, so a shifted argument list points the game's entire
# stdout at whatever happens to land in $2. Here the redirect merely failed
# (rc=1, one second, no log), but the same slip with a WRITABLE path would have
# TRUNCATED THE FILE IT NAMED -- and the file it named was a script in this
# repo.
#
# Two cheap refusals, and both must fail LOUDLY rather than default:
#   * the parent directory must already exist -- a typo'd or shifted path
#     otherwise dies deep inside the launch with a bare rc=1;
#   * the log must not be an existing SCRIPT. A run log is never a .sh or .py,
#     so this cannot refuse a legitimate call, and it is the exact shape of the
#     accident that happened.
OUTDIR="$(dirname "$OUT")"
if [[ ! -d "$OUTDIR" ]]; then
    echo "[run_game] REFUSING: the log's directory does not exist: $OUTDIR" >&2
    echo "[run_game]   log path was: $OUT" >&2
    echo "[run_game]   Check the argument order: <seconds> <logfile> [ENV=v...]" >&2
    exit 2
fi
case "$OUT" in
    *.sh|*.py)
        echo "[run_game] REFUSING: the log path looks like a SCRIPT, not a log: $OUT" >&2
        echo "[run_game]   The launch redirects the game's stdout over this path" >&2
        echo "[run_game]   and would truncate it. This is what a shifted argument" >&2
        echo "[run_game]   list looks like (A312). Check: <seconds> <logfile> [ENV=v...]" >&2
        exit 2 ;;
esac

# --- Source/binary drift ---------------------------------------------------
# Twice now a source change has been made and the binary left stale, so the run
# measured the OLD code: I10 (a toml stripped after the build) and 2026-08-19 (a
# submodule patch reverted for a repro, restored in source, never rebuilt --
# leaving a crashing binary behind a fixed tree). Both times the disagreement
# was invisible at run time. Cheap to detect: if any tracked source is newer
# than the binary, say so.
if [[ -x "$BIN" ]]; then
    NEWER=$(find sinpunishment.toml symbols lib/N64ModernRuntime/ultramodern/src \
                 lib/N64ModernRuntime/librecomp/src -newer "$BIN" -type f 2>/dev/null | head -3)
    if [[ -n "$NEWER" ]]; then
        echo "[run_game] WARNING: source is NEWER than the binary -- this run may measure stale code:" >&2
        echo "$NEWER" | sed 's/^/[run_game]   /' >&2
        echo "[run_game]   Rebuild with scripts/build.sh, or the result is about the old build." >&2
    fi
fi

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
#
# Isolation itself lives in scripts/display_isolate.sh -- ONE copy, because
# three divergent copies is what let the gdb wrappers run unisolated (T59).
# SNP_VISIBLE arrives as an ARGUMENT (an env assignment forwarded to `env`),
# not in this script's own environment -- so "${SNP_VISIBLE:-}" never saw it,
# and a run the user had been asked to WATCH silently went to the nested server
# instead. Check both places.
WANT_VISIBLE="${SNP_VISIBLE:-}"
for a in "$@"; do
    case "$a" in SNP_VISIBLE=*) WANT_VISIBLE="${a#SNP_VISIBLE=}" ;; esac
done
# SNP_ISO GETS THE SAME TREATMENT, 2026-08-22 (A312) -- and it did not have it.
# This script scanned the argument list for SNP_VISIBLE and NOT for SNP_ISO, so
# `run_game.sh N log SNP_ISO=xephyr` forwarded the assignment to the GAME's
# environment via `env` and left display_isolate.sh -- which runs in THIS
# shell -- reading an unset SNP_ISO. The run silently chose a different display
# mode from the one written on the command line. That is the SAME failure the
# comment above describes for SNP_VISIBLE, on the neighbouring variable, and it
# put a documented command in the run sheet that could not do what it said.
WANT_ISO="${SNP_ISO:-}"
for a in "$@"; do
    case "$a" in SNP_ISO=*) WANT_ISO="${a#SNP_ISO=}" ;; esac
done
[[ -n "$WANT_ISO" ]] && export SNP_ISO="$WANT_ISO"
# THE WHOLE CLASS, KILLED, 2026-08-27 — THIRD INSTANCE FORCED IT. SNP_VISIBLE
# (above), then SNP_ISO (A312), and now SNP_REC: the overnight ablation screen
# passed SNP_REC=0 on all 621 runs and STILL RECORDED EVERY ONE (~2.7 GB of
# mp4s, A503), because the assignment reached only the game's env via `env`
# while display_isolate — sourced into THIS shell — read an unset SNP_REC and
# defaulted to recording. Two special cases did not stop the third; a special
# case per variable never will. So: every SNP_* assignment in the argument
# list is exported into this shell too. SNP_* is the wrapper's own namespace —
# non-SNP assignments (SP_AUTOSTART etc.) stay game-only, unchanged.
for a in "$@"; do
    case "$a" in SNP_*=*) export "${a%%=*}=${a#*=}" ;; esac
done
# SNP_VISIBLE arrives as an ARGUMENT (an env assignment forwarded to `env`),
# not in this script's own environment, so it is re-exported here before the
# shared helper reads it.
export SNP_VISIBLE="${WANT_VISIBLE:-0}"
# shellcheck source=scripts/display_isolate.sh
. "$(dirname "$0")/display_isolate.sh"
# T125: say so if this binary is older than the sources it was built from.
# scripts/build.sh --no-recomp builds the RELEASE tree only, so the debug
# binary these debuggers default to can silently be last week's code.
. "$(dirname "$0")/build_staleness.sh"
snp_warn_if_stale "$BIN"
snp_isolate_display run_game
trap snp_display_cleanup EXIT INT TERM

# SNP_HEARTBEAT DEFAULTS ON (T111). It is the liveness signal the validity
# verdict is computed from, and without it a run is recorded UNKNOWN and cannot
# be judged valid (T22). **10 of 93 logged runs were UNKNOWN purely because
# nobody passed it** -- a wasted verdict on a run already paid for in
# wall-clock. It is opt-OUT, not opt-in: an explicit SNP_HEARTBEAT in "$@"
# still wins, because `env` takes the LAST assignment of a name.
# AUDIO (A265) -- BEFORE the launch, because the game must inherit PULSE_SINK
# and open ON the capture sink rather than be chased afterwards. The first
# wiring used `attach`, which hunts for a live sink-input and gave up after 20s
# ("Failure: No such entity", empty file) because our game had not opened one
# by then. Headless runs were discarding their sound on ~20 runs a day, and a
# per-run amplitude reading is a standing regression test on the sound.
# ITS POLARITY WAS BACKWARDS UNTIL 2026-08-28 (A637): written when the game was
# silent, it treated -91 dB as normal. A447 fixed the silence, A499 confirmed
# the music by ear and A97 closed at A509 -- so an audible capture (~-15 dB) is
# the healthy state and FLAT -91 dB is the regression. Opt out with SNP_AUDIO=0.
# Never fatal.
snp_start_audio run_game

# `stdbuf -oL`: LINE-BUFFER STDOUT SO IT SURVIVES THE KILL (2026-08-21).
#
# Both streams have always been merged into $OUT, so RT64's startup lines --
# "Device Name", "Device Vendor", "Driver Version", printed to STDOUT in
# rt64_application.cpp -- should have been in every log. They were in **2 of
# 34**. stderr is unbuffered; stdout redirected to a FILE is block-buffered, and
# this script ends every run with `kill -9`, which discards a partial buffer. So
# the GPU identity was being written and then thrown away.
#
# WHY IT MATTERS RATHER THAN BEING TIDINESS: the user reports geometry warping
# on the real display that does NOT appear in our recordings (A287, unresolved).
# If any visual fault is driver- or shader-path dependent, the renderer identity
# is the axis that separates two runs -- and we were not recording it. Also the
# reason `MM_RT64_UBERSHADERS_ONLY` exists in another project is NVIDIA-specific
# rendering issues, and this machine is an RTX 3080 (T143).
#
# Line buffering, not full flushing: the game writes little to stdout after
# startup, so the cost is a flush per line on a cold path. The probes all use
# stderr and are unaffected.
# RECORD THE GRAPHICS CONFIG THE RUN ACTUALLY USED (A404, 2026-08-25). The
# config lives in ~/.config/sinpunishment/graphics.json and NOTHING in the run
# log named it, so a run at native resolution and a run at Auto were
# indistinguishable after the fact. A404 changed four settings, measured a
# render difference, and then could not say WHICH setting caused it -- the
# entry had to be written with the axis unisolated. Same shape as the GPU
# identity above: state that decides how a frame looks, written and thrown
# away. Copied in BEFORE launch so it describes the run that is starting, not
# whatever the file says whenever someone reads it later.
# TRUNCATE EXPLICITLY. The game's redirect below is now `>>` so the config
# block survives it, which means NOTHING truncates $OUT any more -- re-using a
# log path would silently append this run onto the last one's output. That is
# the "two runs in one file" trap, and every verdict below greps $OUT.
: > "$OUT"

GFX_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/sinpunishment/graphics.json"
if [[ -r "$GFX_CFG" ]]; then
    { echo "[cfg] graphics.json at launch:"
      sed 's/^/[cfg]   /' "$GFX_CFG"; } >> "$OUT"
else
    echo "[cfg] graphics.json NOT READABLE at $GFX_CFG -- render settings unknown" >> "$OUT"
fi

env SP_AUTOSTART=1 SNP_HEARTBEAT=1 "$@" stdbuf -oL "$BIN" >> "$OUT" 2>&1 &
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

# The isolated server is torn down by snp_display_cleanup on the EXIT trap.
# Deliberately NOT also killed here: two cleanup paths for one resource is
# how the copies drifted apart in the first place.

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

# STALLED IS NOT DEGRADED (A220). The rule above reads only the LAST heartbeat,
# so a run that played the whole tutorial and then stopped scored identically to
# one that never rendered a frame -- and got told "not evidence about the
# build". It mislabelled three runs, including the one the user watched reach a
# section this project had never rendered.
#
# The fix needs no new threshold: reuse the same 25/s bar and ask whether the
# run spent MORE of its life healthy than stalled. A run that worked for 200
# seconds and stopped for 40 is not the same object as one that never started,
# and only the first is evidence about what the build can do.
# `grep -c` PRINTS 0 AND EXITS 1 when there are no matches, so `|| echo 0`
# appends a SECOND zero and the arithmetic below dies on "0\n0". Caught by
# re-grading real logs rather than by reading this back.
HEALTHY_SECS=$(grep -c 'gfx_tasks=[0-9]* *+\(2[5-9]\|[3-9][0-9]\)' "$OUT" 2>/dev/null || true)
STALLED_SECS=$(grep -c 'NO GFX TASKS' "$OUT" 2>/dev/null || true)
HEALTHY_SECS=${HEALTHY_SECS:-0}
STALLED_SECS=${STALLED_SECS:-0}

VERDICT="CLEAN"
if   [[ "$INPUT" -gt 0 ]];                     then VERDICT="CONTAMINATED"
elif [[ -n "$EARLY" ]];                        then VERDICT="CRASHED"
elif [[ -z "$GFX_LINE" ]];                     then VERDICT="UNKNOWN(no SNP_HEARTBEAT)"
elif [[ "${GFX_RATE:-0}" -lt 25 ]]; then
    if [[ "$HEALTHY_SECS" -gt "$STALLED_SECS" ]]; then VERDICT="STALLED"
    else                                             VERDICT="DEGRADED"; fi
fi

printf '[run_game] ran %ss  pid=%s  log=%s (%s lines)  leftover=%s  input_events=%s  VERDICT=%s\n' \
    "$SECS" "$PID" "$OUT" "$(wc -l < "$OUT" 2>/dev/null || echo 0)" "$LEFT" "$INPUT" "$VERDICT"

case "$VERDICT" in
  DEGRADED)
    echo "[run_game] NOT COMPARABLE: gfx ended at +${GFX_RATE:-?}/s and was never sustained (${HEALTHY_SECS}s healthy vs ${STALLED_SECS}s stalled). This run is not evidence about the build (T22)." >&2 ;;
  STALLED)
    echo "[run_game] IT RAN, THEN STOPPED: ${HEALTHY_SECS}s at a healthy rate, then ${STALLED_SECS}s with no graphics." >&2
    echo "[run_game] This IS evidence -- it is not rate-comparable to a CLEAN run, but the part before the stall is real (A220)." >&2 ;;
  "UNKNOWN(no SNP_HEARTBEAT)")
    echo "[run_game] No liveness signal, and SNP_HEARTBEAT defaults ON (T111) — so this is a\n[run_game] REAL anomaly, not a forgotten flag: the build may lack the hook, or the run\n[run_game] may have died before emitting one. Do not judge this run valid (T22)." >&2 ;;
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
# RECORD THE MODE ACTUALLY USED, NOT MERELY THE ARGUMENTS (2026-08-22, A310).
# This column was `"${*:-none}"` -- the extra env assignments passed as ARGS.
# But SNP_VISIBLE is accepted TWO ways (see the block near line 105): as an
# argument, and from this script's own environment. A caller using the shell
# prefix form -- `SNP_VISIBLE=1 scripts/run_game.sh ...`, which is exactly what
# docs/inspector-sitting-checklist.md said -- ran REAL and logged `none`.
#
# That is not a cosmetic gap. check_ledger.py's changed-signature trigger reads
# this column to tell a headless crash (a regression worth waking someone for)
# from a visible one (a user at the keyboard). The 2026-08-22 08:29 row logged
# `none` for a real-display run the USER crashed on purpose, and the alarm duly
# reported "a HEADLESS SIGSEGV ... a regression". A row that misstates the mode
# is worse than a missing row, because everything downstream believes it.
ENVCOL="${*:-}"
if [[ "${SNP_VISIBLE:-0}" == "1" && "$ENVCOL" != *SNP_VISIBLE=* ]]; then
    ENVCOL="${ENVCOL:+$ENVCOL }SNP_VISIBLE=1"
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -Iseconds)" "$SECS" "${EARLY:-$SECS}" "${RC:-0}" "$INPUT" "$LEFT" \
    "${GFX_TOTAL:-NA}" "${GFX_RATE:-NA}" "$VERDICT" "$(basename "$OUT")" "${ENVCOL:-none}" >> "$RUNLOG"

exit 0
