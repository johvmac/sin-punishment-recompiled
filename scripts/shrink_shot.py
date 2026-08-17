#!/usr/bin/env python3
"""Downscale a game capture to the N64's own output resolution for viewing.

The window is 640x480 but the game renders at roughly 320x240, so halving it
discards upscaling, not detail -- and a quarter of the pixels is markedly
cheaper to read. Writes <name>.small.png next to the input unless told
otherwise, and leaves the original alone: freeze_check.sh's md5 frame-identity
check must keep hashing the full-resolution image, since downscaling could in
principle collapse two genuinely different frames onto the same hash.

Usage: shrink_shot.py <in.png> [out.png] [width]
"""
import sys
from pathlib import Path

from PIL import Image

src = Path(sys.argv[1])
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".small.png")
width = int(sys.argv[3]) if len(sys.argv) > 3 else 320

img = Image.open(src)
height = max(1, round(img.height * width / img.width))
# BOX averages the source pixels in each target cell. For an exact 2:1 integer
# ratio that is precisely "undo the upscale"; LANCZOS would ring on the hard
# edges of pixel art and dither patterns, which is most of what is on screen.
img.resize((width, height), Image.BOX).save(dst)
print(f"{src} {img.width}x{img.height} -> {dst} {width}x{height}")
