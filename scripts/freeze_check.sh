#!/usr/bin/env bash
# Does the game FREEZE, and if so when? Captures the SAME running instance at
# several timestamps and reports whether the frame actually changes.
#
# Usage: scripts/freeze_check.sh "10 15 25 35 50 70" [binary] [outdir]
#
# WHY THIS EXISTS (methodology bug, 2026-08-15):
# `boot_screen_check.sh N` launches a FRESH process and screenshots once at N
# seconds. Running it at 50s, 70s and 100s therefore produces three INDEPENDENT
# runs -- comparing those readings measures run-to-run variation, NOT whether a
# single run is still animating. That mistake produced a confident and wrong
# claim that a build was "still animating at 100s". Frames must be compared
# WITHIN one process to say anything about freezing.
#
# A frame is identified by an md5 of the decoded PNG: identical hash on two
# different timestamps == the exact same frame == frozen (a live attract loop
# never reproduces a frame bit-for-bit).
set -uo pipefail

# --- help (T37) ------------------------------------------------------------
# Prints this script's own header block. Added after `route.py --help` was
# silently ignored and fell through to a state-mutating default.
case "${1:-}" in
    -h|--help)
        sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'
        exit 0 ;;
esac
cd "$(dirname "$0")/.." || exit 1

TIMES="${1:-10 15 25 35 50 70}"
BIN="${2:-./build/SinPunishmentRecompiled}"
OUTDIR="${3:-/tmp/freeze_check}"
mkdir -p "$OUTDIR"

_self_exe="$(readlink -f "$BIN" 2>/dev/null)"
for _pid in $(pgrep -f SinPunishmentRecompiled 2>/dev/null); do
    [[ "$_pid" == "$$" ]] && continue
    [[ "$(readlink -f "/proc/$_pid/exe" 2>/dev/null)" == "$_self_exe" ]] && kill -9 "$_pid" 2>/dev/null
done
sleep 1

# SDL_VIDEODRIVER=x11: same reason as boot_screen_check.sh -- xwd silently
# reads a stale backing store for Wayland-backed windows.
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 "$BIN" > "$OUTDIR/run.log" 2>&1 &
GAME_PID=$!
echo "launched pid $GAME_PID  ($BIN)"

WIN_ID=""
for _ in $(seq 1 30); do
    WIN_ID=$(xwininfo -root -tree 2>/dev/null | grep -i "SinPunishmentRecompiled" | grep -v -i "mutter" | grep -oE '0x[0-9a-fA-F]+' | head -1)
    [ -n "$WIN_ID" ] && break
    sleep 0.5
done
if [ -z "$WIN_ID" ]; then
    echo "ERROR: never found the game window"; kill -9 "$GAME_PID" 2>/dev/null; exit 1
fi
echo "window $WIN_ID"

# Wait for the first genuinely-rendered frame BEFORE minimizing. Minimizing at
# window-creation time -- before Vulkan's swapchain has completed its first
# present -- leaves the window stuck never rendering at all (documented in
# boot_screen_check.sh, confirmed reproducible 2026-08-14). Getting this wrong
# here produced a full run of solid-black "frozen" frames that were an artifact
# of this script, not the build.
# Interpreter that can import python-xlib, for minimize_window.py. Probed, not
# hardcoded: SNP_PYXLIB wins if set, then the system python3, then any venv
# listed below. Kept as a search rather than one absolute path so the repo
# carries no machine-specific path, and as a search rather than a single
# fallback because on at least one dev machine python-xlib exists ONLY inside a
# venv -- assuming the system python3 has it silently disabled minimizing.
# If none work PYXLIB stays empty and the minimize step is skipped: the run is
# unaffected, the window just stays on screen.
PYXLIB="${SNP_PYXLIB:-}"
if [ -z "$PYXLIB" ]; then
    for _cand in "$(command -v python3)" \
                 "$HOME/Documents/reference-recomps/decomp-venv/bin/python3"; do
        if [ -x "$_cand" ] && "$_cand" -c "import Xlib" >/dev/null 2>&1; then
            PYXLIB="$_cand"
            break
        fi
    done
fi
if [ -n "$PYXLIB" ] && [ -x "$PYXLIB" ] && [ "${KEEP_VISIBLE:-0}" != "1" ]; then
    for _ in $(seq 1 80); do
        xwd -id "$WIN_ID" -silent -out "$OUTDIR/poll.xwd" 2>/dev/null
        if [ -s "$OUTDIR/poll.xwd" ]; then
            ffmpeg -y -loglevel error -i "$OUTDIR/poll.xwd" "$OUTDIR/poll.png" 2>/dev/null
            IS_DARK=$(python3 -c "
from PIL import Image
img = Image.open('$OUTDIR/poll.png').convert('RGB')
px = list(img.getdata())
dark = sum(1 for r,g,b in px if r<12 and g<12 and b<12)
print('dark' if dark/len(px) > 0.995 else 'notdark')
" 2>/dev/null)
            [ "$IS_DARK" = "notdark" ] && break
        fi
        sleep 0.25
    done
    rm -f "$OUTDIR/poll.xwd" "$OUTDIR/poll.png"
    "$PYXLIB" "$(dirname "$0")/minimize_window.py" "$WIN_ID" >/dev/null 2>&1
fi

PREV_HASH=""
ELAPSED=0
for T in $TIMES; do
    SLEEP=$(( T - ELAPSED ))
    [ "$SLEEP" -gt 0 ] && sleep "$SLEEP"
    ELAPSED=$T

    if ! kill -0 "$GAME_PID" 2>/dev/null; then
        echo "t=${T}s  PROCESS EXITED (see $OUTDIR/run.log)"
        break
    fi

    PNG="$OUTDIR/t${T}.png"
    xwd -id "$WIN_ID" -silent -out "$OUTDIR/t.xwd" 2>/dev/null
    ffmpeg -y -loglevel error -i "$OUTDIR/t.xwd" "$PNG" 2>/dev/null

    read -r SIZE FRAC HASH <<<"$(python3 -c "
import hashlib,sys
from PIL import Image
img = Image.open('$PNG').convert('RGB')
px = list(img.getdata())
dark = sum(1 for r,g,b in px if r<12 and g<12 and b<12)
print(f'{img.size[0]}x{img.size[1]}', round(dark/len(px),4),
      hashlib.md5(img.tobytes()).hexdigest()[:12])
" 2>/dev/null)"

    SAME=""
    [ -n "$PREV_HASH" ] && [ "$HASH" = "$PREV_HASH" ] && SAME="  <<< IDENTICAL TO PREVIOUS -- FROZEN"
    printf 't=%-4ss size=%-9s dark=%-7s frame=%s%s\n' "$T" "$SIZE" "$FRAC" "$HASH" "$SAME"
    PREV_HASH="$HASH"
done

kill -9 "$GAME_PID" 2>/dev/null
rm -f "$OUTDIR/t.xwd"
echo "images in $OUTDIR"
exit 0
