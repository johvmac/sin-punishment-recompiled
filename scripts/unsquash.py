#!/usr/bin/env python3
"""Fix squashed field captures for viewing: vertical pixel-double + integer upscale.

WHY (user request, 2026-08-26): reference frames captured as one interlaced
field come out 640x240 and read as "smooshed" when viewed. The fix the user
specified, implemented literally: double the pixels VERTICALLY (640x240 ->
640x480, restoring aspect), then integer-scale the whole thing with NEAREST
NEIGHBOUR (default x2 -> 1280x960). No resampling at any step — every output
pixel is an exact copy of a source pixel, so nothing blurs and nothing is
invented.

    scripts/unsquash.py <in.png> [out.png] [--scale N] [--dry-run]

Skips (with a message, not an error) inputs that are not squashed (height*2 >
width * 1.2 heuristic) unless --force. --self-check runs the controls.
"""
import argparse, sys
from pathlib import Path
from PIL import Image


def unsquash(im: Image.Image, scale: int) -> Image.Image:
    w, h = im.size
    out = im.resize((w, h * 2), Image.NEAREST)          # vertical double
    return out.resize((w * scale, h * 2 * scale), Image.NEAREST)  # integer up


def self_check() -> int:
    ok = 0
    checks = []
    # a 4x2 image with 5 distinct colours
    src = Image.new('RGB', (4, 2))
    px = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (9, 9, 9),
          (1, 2, 3), (4, 5, 6), (7, 8, 9), (255, 255, 255)]
    src.putdata(px)
    out = unsquash(src, 3)
    checks.append(("dims are (w*s, h*2*s)", out.size == (12, 12)))
    # nearest introduces NO new colours — a resampling bug would (the control
    # that can fail: swap NEAREST for BILINEAR and this fails immediately)
    checks.append(("colour set preserved exactly",
                   set(out.getdata()) == set(px)))
    # each source pixel becomes an exact s x 2s block
    blk = [out.getpixel((0 + dx, 0 + dy)) for dx in range(3) for dy in range(6)]
    checks.append(("top-left block is uniform", set(blk) == {px[0]}))
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok += passed
    print(f"self-check {ok}/{len(checks)}")
    return 0 if ok == len(checks) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", type=Path)
    ap.add_argument("output", nargs="?", type=Path)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        sys.exit(self_check())
    if not a.input:
        ap.error("input required")
    im = Image.open(a.input)
    w, h = im.size
    if h * 2 > w * 1.2 and not a.force:
        print(f"SKIP: {a.input} is {w}x{h} — not squashed (h*2 > w*1.2); --force to override")
        return
    out_path = a.output or a.input.with_name(a.input.stem + "-unsquashed.png")
    if a.dry_run:
        print(f"DRY-RUN: {a.input} {w}x{h} -> {out_path} {w*a.scale}x{h*2*a.scale} (NEAREST only)")
        return
    unsquash(im, a.scale).save(out_path)
    print(f"wrote {out_path} ({w*a.scale}x{h*2*a.scale})")


if __name__ == "__main__":
    main()
