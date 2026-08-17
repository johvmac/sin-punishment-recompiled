#!/usr/bin/env bash
# Boots the game headlessly-but-with-a-real-window, waits for it to settle,
# screenshots the actual game window (not the whole desktop), and reports
# whether the captured frame is (close to) solid black -- a quick, scriptable
# proxy for "did it actually reach the title screen" without needing a human
# to look at the screen.
#
# By default the window is minimized right after launch so it stays out of
# the user's way -- set KEEP_VISIBLE=1 to skip that (e.g. when you want the
# user to look at the actual screen for a sanity check, not just the capture).
set -u
cd "$(dirname "$0")/.."

WAIT_SECONDS="${1:-60}"
OUT_PNG="${2:-/tmp/boot_screen_check.png}"
KEEP_VISIBLE="${KEEP_VISIBLE:-0}"

# Clear any stale game instances. Do NOT use `pkill -f build/SinPunishmentRecompiled`
# here: `pkill -f` matches full command lines, so it also kills the *calling*
# shell whenever that shell's own command line happens to mention the binary
# path (e.g. a `cp build/SinPunishmentRecompiled ...` earlier on the same
# line). That failure is silent -- the caller dies mid-script with no output --
# and it corrupted several A/B comparisons on 2026-08-15 before being found.
#
# Instead: resolve each candidate's /proc/<pid>/exe and kill only processes
# that are genuinely this executable. A shell can never match that test.
_self_exe="$(readlink -f ./build/SinPunishmentRecompiled 2>/dev/null)"
if [[ -n "$_self_exe" ]]; then
    for _pid in $(pgrep -f SinPunishmentRecompiled 2>/dev/null); do
        [[ "$_pid" == "$$" ]] && continue
        _target="$(readlink -f "/proc/$_pid/exe" 2>/dev/null)"
        if [[ "$_target" == "$_self_exe" ]]; then
            kill -9 "$_pid" 2>/dev/null
        fi
    done
fi
sleep 1

# SDL_VIDEODRIVER=x11 forces a native X11 window instead of a Wayland-backed
# one on this machine's Wayland session -- without it, xwd's capture is
# intermittently and silently wrong (reports solid black for a window that's
# genuinely rendering, since Vulkan swapchain presentation doesn't reliably
# update the legacy X11 backing store xwd reads under XWayland). Confirmed
# 2026-08-14: three consecutive captures under a forced-X11 window all came
# back correct; captures under the default Wayland-backed window did not.
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 ./build/SinPunishmentRecompiled > /tmp/boot_screen_check_run.log 2>&1 &
GAME_PID=$!
echo "launched pid $GAME_PID"

# Find the window, then minimize it -- but only once it's actually presented a
# real frame. Minimizing immediately at window creation (before Vulkan's
# swapchain has done its first successful present) leaves it stuck never
# rendering at all -- confirmed 2026-08-14, reproducible. Rather than a fixed
# guessed delay (imprecise, and either too conservative -- leaving the window
# visible longer than needed -- or too tight and flaky under system load),
# poll with quick throwaway captures until the first non-black frame shows up,
# then minimize right away. Self-calibrating, no magic number.
WIN_ID=""
for _ in $(seq 1 20); do
    WIN_ID=$(xwininfo -root -tree 2>/dev/null | grep -i "SinPunishmentRecompiled" | grep -v -i "mutter" | grep -oE '0x[0-9a-fA-F]+' | head -1)
    [ -n "$WIN_ID" ] && break
    sleep 0.5
done

# Interpreter that can import python-xlib, for minimize_window.py. Override with
# SNP_PYXLIB=/path/to/python3; otherwise the system python3 is used if it has
# Xlib. If neither works, PYXLIB stays empty and the minimize step below is
# skipped entirely -- the run still works, the window just stays on screen.
PYXLIB="${SNP_PYXLIB:-}"
if [ -z "$PYXLIB" ] && python3 -c "import Xlib" >/dev/null 2>&1; then
    PYXLIB=$(command -v python3)
fi
if [ -n "$WIN_ID" ] && [ -n "$PYXLIB" ] && [ -x "$PYXLIB" ] && [ "$KEEP_VISIBLE" != "1" ]; then
    for _ in $(seq 1 60); do
        xwd -id "$WIN_ID" -silent -out /tmp/boot_screen_check_poll.xwd 2>/dev/null
        if [ -s /tmp/boot_screen_check_poll.xwd ]; then
            ffmpeg -y -loglevel error -i /tmp/boot_screen_check_poll.xwd /tmp/boot_screen_check_poll.png 2>/dev/null
            IS_DARK=$(python3 -c "
from PIL import Image
img = Image.open('/tmp/boot_screen_check_poll.png').convert('RGB')
pixels = list(img.getdata())
dark = sum(1 for r,g,b in pixels if r < 12 and g < 12 and b < 12)
print('dark' if dark / len(pixels) > 0.995 else 'notdark')
" 2>/dev/null)
            [ "$IS_DARK" = "notdark" ] && break
        fi
        sleep 0.25
    done
    rm -f /tmp/boot_screen_check_poll.xwd /tmp/boot_screen_check_poll.png
    "$PYXLIB" "$(dirname "$0")/minimize_window.py" "$WIN_ID" >/dev/null 2>&1
fi

echo "waiting ${WAIT_SECONDS}s..."
sleep "$WAIT_SECONDS"

if ! kill -0 "$GAME_PID" 2>/dev/null; then
    echo "RESULT: process exited/crashed before screenshot"
    tail -20 /tmp/boot_screen_check_run.log
    exit 2
fi

if [ -z "$WIN_ID" ]; then
    echo "RESULT: could not find game window"
    kill -9 "$GAME_PID" 2>/dev/null
    exit 3
fi

xwd -id "$WIN_ID" -silent -out /tmp/boot_screen_check.xwd
ffmpeg -y -loglevel error -i /tmp/boot_screen_check.xwd "$OUT_PNG"

kill -9 "$GAME_PID" 2>/dev/null

python3 - "$OUT_PNG" << 'PYEOF'
import sys
from PIL import Image
path = sys.argv[1]
img = Image.open(path).convert("RGB")
pixels = list(img.getdata())
n = len(pixels)
dark = sum(1 for r,g,b in pixels if r < 12 and g < 12 and b < 12)
frac_dark = dark / n
avg = tuple(sum(c[i] for c in pixels)/n for i in range(3))
print(f"RESULT: image={path} size={img.size} dark_fraction={frac_dark:.3f} avg_rgb={avg}")
if frac_dark > 0.995:
    print("RESULT: BLACK (still stuck / not rendering)")
elif frac_dark > 0.85:
    print("RESULT: AMBIGUOUS -- dark_fraction is in the borderline band (0.85-0.995).")
    print("RESULT: This number alone is NOT sufficient evidence either way -- view the PNG directly before concluding anything.")
else:
    print("RESULT: NOT BLACK (something is rendering)")
PYEOF
