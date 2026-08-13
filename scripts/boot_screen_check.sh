#!/usr/bin/env bash
# Boots the game headlessly-but-with-a-real-window, waits for it to settle,
# screenshots the actual game window (not the whole desktop), and reports
# whether the captured frame is (close to) solid black -- a quick, scriptable
# proxy for "did it actually reach the title screen" without needing a human
# to look at the screen.
set -u
cd "$(dirname "$0")/.."

WAIT_SECONDS="${1:-60}"
OUT_PNG="${2:-/tmp/boot_screen_check.png}"

pkill -9 -f "build/SinPunishmentRecompiled" >/dev/null 2>&1
sleep 1

SP_AUTOSTART=1 ./build/SinPunishmentRecompiled > /tmp/boot_screen_check_run.log 2>&1 &
GAME_PID=$!
echo "launched pid $GAME_PID, waiting ${WAIT_SECONDS}s..."
sleep "$WAIT_SECONDS"

if ! kill -0 "$GAME_PID" 2>/dev/null; then
    echo "RESULT: process exited/crashed before screenshot"
    tail -20 /tmp/boot_screen_check_run.log
    exit 2
fi

WIN_ID=$(xwininfo -root -tree 2>/dev/null | grep -i "sin.*punish\|SinPunishmentRe" | grep -oE '0x[0-9a-fA-F]+' | head -1)

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
if frac_dark > 0.98:
    print("RESULT: BLACK (still stuck / not rendering)")
else:
    print("RESULT: NOT BLACK (something is rendering)")
PYEOF
