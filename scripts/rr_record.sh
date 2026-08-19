#!/usr/bin/env bash
# Record a run under `rr` so it can be replayed and stepped BACKWARDS.
#
# Usage: scripts/rr_record.sh [seconds] [trace_dir] [binary]
#   scripts/rr_record.sh 200
#   scripts/rr_record.sh 200 /media/joh/extra/sin-punishment-archive/rr/a99
#
# Then:
#   rr replay <trace_dir>
#     continue                              # run to the SIGSEGV
#     watch -l *(unsigned int*)<host_addr>
#     reverse-continue                       # lands on the write
#
# WHY A WRAPPER RATHER THAN A BARE `rr record`
# --------------------------------------------
# A bare `rr record` launches the binary with no deadline and no display
# isolation -- the two things `run_game.sh` exists to provide, and the guard
# refuses a raw launch line for exactly that reason. This carries both:
#
#  * the same `scripts/display_isolate.sh` used by run_game.sh, gdb_watch.sh and
#    gdb_fault.sh, so a recording is headless by default (T59/T60). ONE copy of
#    that logic on purpose: three divergent copies is what let the gdb wrappers
#    run unisolated in the first place;
#  * a hard deadline, because a recording of a hung game grows without bound.
#
# PRECONDITION, CHECKED RATHER THAN ASSUMED
# -----------------------------------------
# `rr` needs kernel.perf_event_paranoid <= 1. This machine ships at 4. If it is
# not set, this REFUSES with the fix rather than recording a trace that cannot
# be replayed -- a silent failure here costs a full run to discover.
#
# THE CAVEAT THAT MATTERS (do not skip)
# -------------------------------------
# `rr` serialises threads onto one core. The scene walk runs on thread 3 while
# thread 4 runs the attract scene, and every timing-anchored result here -- the
# 158s crash, the +30/s gfx validity filter (T22) -- depends on real
# concurrency. So this script PRINTS the gfx rate from the recorded run and
# tells you to compare it. If the repro does not survive recording, that is a
# finding about `rr`, not about the bug (T60's rule, applied).
set -uo pipefail

case "${1:-}" in --help|-h) sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac

SECONDS_TO_RUN="${1:-200}"
TRACE_DIR="${2:-/tmp/rr-snp}"
BIN="${3:-build/SinPunishmentRecompiled}"

[ -x "$BIN" ] || { echo "no binary at $BIN" >&2; exit 1; }
command -v rr >/dev/null 2>&1 || { echo "rr is not installed" >&2; exit 1; }

# MEASURED 2026-08-19 (T62): rr 5.7 CANNOT record this program. Two blockers,
# either fatal on its own:
#   * it aborts on unmodelled ioctls. SDL's HID probe was disableable
#     (SDL_JOYSTICK_HIDAPI=0, applied below); the next one is
#     DMA_BUF_IOCTL_EXPORT_SYNC_FILE from the Vulkan/RT64 path, which is not.
#   * even before aborting, the gfx rate collapsed to +0/+1 against a normal
#     +30 -- so the 158s repro could never be reached anyway.
# Each abort also raises an apport crash dialog on the user's desktop, so this
# does not re-run itself casually. SNP_RR_FORCE=1 to try again (e.g. after an rr
# upgrade); the failure is loud and the wrapper detects it.
if [ "${SNP_RR_FORCE:-0}" != "1" ]; then
    cat >&2 <<'MSG'
[rr_record] REFUSING: rr cannot record this target -- measured, not assumed (T62).
[rr_record]   1. rr 5.7 aborts on DMA_BUF_IOCTL_EXPORT_SYNC_FILE (Vulkan/RT64).
[rr_record]   2. gfx rate collapses to +0/+1 vs +30, so the 158s repro is out of reach.
[rr_record] Each attempt also pops an Ubuntu apport crash dialog.
[rr_record] Use scripts/gdb_watch.sh instead -- it caught A99's writer in one run.
[rr_record] SNP_RR_FORCE=1 to retry anyway (worth it after an rr upgrade).
MSG
    exit 2
fi

PARANOID="$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo 99)"
if [ "$PARANOID" -gt 1 ]; then
    cat >&2 <<MSG
[rr_record] REFUSING: kernel.perf_event_paranoid is $PARANOID, rr needs <= 1.
[rr_record] Recording now would produce a trace that cannot be replayed, and you
[rr_record] would not find out until after the run. Fix, then re-run:
[rr_record]     sudo sysctl -w kernel.perf_event_paranoid=1
[rr_record] Persist it:
[rr_record]     echo 'kernel.perf_event_paranoid = 1' | sudo tee /etc/sysctl.d/10-rr.conf
[rr_record] (Or use 'rr record -n', which needs no sysctl but is much slower.)
MSG
    exit 2
fi

# shellcheck source=scripts/display_isolate.sh
. "$(dirname "$0")/display_isolate.sh"
snp_isolate_display rr_record
trap snp_display_cleanup EXIT INT TERM

LOG="${TRACE_DIR%/}.log"
mkdir -p "$(dirname "$TRACE_DIR")"
rm -rf "$TRACE_DIR"

echo "[rr_record] recording up to ${SECONDS_TO_RUN}s into $TRACE_DIR" >&2

# Deadline by PID, never `pkill -f` (it matches this script's own command line)
# and never plain SIGTERM (SDL2 converts it into an SDL_QUIT event) -- both
# lessons are baked into run_game.sh and apply identically here.
# SDL's hidapi joystick backend issues HIDIOCGVERSION (ioctl type 'H', nr 1).
# rr 5.7 does not model that ioctl and ABORTS the recording on it -- which on
# Ubuntu also raises an apport crash dialog on the user's desktop. Disabling
# the HID backends costs nothing here: runs are autostarted and headless, with
# no controller attached, and run_game.sh already reports input_events=0.
SP_AUTOSTART=1 SNP_HEARTBEAT=1 \
    SDL_JOYSTICK_HIDAPI=0 SDL_JOYSTICK_DISABLE_UDEV=1 \
    rr record -o "$TRACE_DIR" "$BIN" > "$LOG" 2>&1 &
RRPID=$!
( sleep "$SECONDS_TO_RUN"; kill -9 "$RRPID" 2>/dev/null ) &
WATCHDOG=$!
wait "$RRPID" 2>/dev/null
RC=$?
kill "$WATCHDOG" 2>/dev/null

# The validity filter. A recording whose gfx rate collapsed is not a recording
# of the bug -- it is a recording of rr's scheduling (T22, T60).
RATE="$(grep -oE 'gfx_tasks=[0-9]+ +\+[0-9]+' "$LOG" 2>/dev/null | awk '{print $2}' \
        | sort | uniq -c | sort -rn | head -3 | tr '\n' ' ')"
if grep -qE "\[FATAL\]|Unknown ioctl|memfd open\(\) failed" "$LOG" 2>/dev/null; then
    echo "[rr_record] rr ABORTED -- it could not model a syscall this program makes:" >&2
    grep -m2 -E "\[FATAL\]|Unknown ioctl|memfd open\(\) failed" "$LOG" | sed "s/^/[rr_record]   /" >&2
    echo "[rr_record] This is an rr/target incompatibility, NOT a bug in the game and" >&2
    echo "[rr_record] NOT a sysctl problem. The trace is unusable; do not replay it." >&2
    echo "[rr_record] Record the incompatibility and fall back to scripts/gdb_watch.sh." >&2
fi
echo "[rr_record] rc=$RC  trace=$TRACE_DIR  log=$LOG" >&2
echo "[rr_record] gfx rate distribution: ${RATE:-<none captured>}" >&2
echo "[rr_record] COMPARE that against a normal run (57x +30 over 60s, T60)." >&2
echo "[rr_record] If it collapsed, rr changed the thing you are measuring -- record" >&2
echo "[rr_record] that as a finding about rr and go back to scripts/gdb_watch.sh." >&2
echo "[rr_record] Replay with:  rr replay $TRACE_DIR" >&2
