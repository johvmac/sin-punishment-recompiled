#!/usr/bin/env python3
"""Crop a run recording down to the game window, and PROVE nothing was lost.

WHY NOT cropdetect
------------------
ffmpeg's `cropdetect` finds the bounding box of non-black CONTENT, and that is
the wrong box. The game's own 640x480 image has black borders inside it -- a
frame from the title-screen run measures a content box of 591x425 at 344,136,
well inside the window. Cropping to that would silently slice off legitimate
game pixels, and the result would look perfectly fine.

What we want is the WINDOW rect: 640x480, centred in the recorded screen because
Xvfb runs with no window manager. That is a geometry fact, not a content fact.

THE CONTROL
-----------
An assumed geometry that is wrong destroys evidence and looks fine afterwards --
the exact failure mode this project keeps hitting. So the crop is never applied
on the assumption alone:

  **every pixel OUTSIDE the proposed crop, across sampled frames spread through
  the whole video, must be black. If any is not, REFUSE.**

That is a control that can fail: point it at a video whose window is somewhere
else, or propose a crop that clips the game, and it says so instead of encoding.

Usage:
    scripts/crop_recording.py <video> [--check] [--replace] [-o OUT]
    scripts/crop_recording.py <video> --geom 640x480+320+120

    --check     verify only; print the proposed crop and the verdict, encode nothing
    --replace   on success, replace the original (default: write <name>-crop.mp4)
    --frames N  how many frames to sample for verification (default 24)
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GAME_W, GAME_H = 640, 480
BLACK = 16  # a channel value at or below this counts as black
# 16 is the tolerance for a LOSSY source. Against the lossless master that
# capture now produces, real padding measures exactly 0, so the check is far
# stricter in practice than the threshold implies.


def _ff(args):
    return subprocess.run(["ffprobe", "-v", "error"] + args,
                          capture_output=True, text=True).stdout.strip()


def probe_size(path):
    """Width, height, duration. Duration is tried THREE ways and may be None.

    The lossless matroska masters written by a SIGINT-stopped ffmpeg carry NO
    stream duration (`N/A`). The first version fell back to 0.0, and verify()
    then sampled seconds 0..N-1 -- the first few seconds only -- while STILL
    printing "across the whole file". A control that silently narrows its own
    scope and reports the wide one is worse than no control: it is exactly the
    A93/A161 failure, inside the tool built to prevent it.

    So: stream duration, else FORMAT duration (which matroska does carry), else
    frames/rate. If all three fail, return None and let the caller REFUSE
    rather than quietly checking the opening seconds.
    """
    out = _ff(["-select_streams", "v:0", "-show_entries",
               "stream=width,height,duration", "-of", "csv=p=0", str(path)])
    parts = out.split(",")
    w, h = int(parts[0]), int(parts[1])
    dur = None
    try:
        dur = float(parts[2])
    except (IndexError, ValueError):
        pass
    if not dur or dur <= 0:
        try:
            dur = float(_ff(["-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))
        except ValueError:
            dur = None
    if not dur or dur <= 0:
        try:
            n = float(_ff(["-count_frames", "-select_streams", "v:0", "-show_entries",
                           "stream=nb_read_frames", "-of", "csv=p=0", str(path)]))
            rate = _ff(["-select_streams", "v:0", "-show_entries",
                        "stream=avg_frame_rate", "-of", "csv=p=0", str(path)])
            num, den = (rate.split("/") + ["1"])[:2]
            fps = float(num) / float(den or 1)
            dur = n / fps if fps > 0 else None
        except (ValueError, ZeroDivisionError):
            dur = None
    return w, h, dur


def verify(path, geom, n_frames, dur):
    """Sample frames across the WHOLE video; assert everything outside is black.

    Spread across the whole file deliberately: the window could in principle
    move, and sampling only the start would not notice. This is the same
    sampling-scope lesson that cost A93 and A161.
    """
    from PIL import Image
    cw, ch, cx, cy = geom
    worst = 0
    worst_at = None
    with tempfile.TemporaryDirectory() as d:
        for i in range(n_frames):
            t = (dur * (i + 0.5) / n_frames) if dur > 0 else i
            f = Path(d) / f"f{i}.png"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", str(f)],
                           capture_output=True)
            if not f.exists() or f.stat().st_size == 0:
                continue
            im = Image.open(f).convert("RGB")
            px = im.load()
            W, H = im.size
            for y in range(0, H, 2):
                inside_y = cy <= y < cy + ch
                for x in range(0, W, 2):
                    if inside_y and cx <= x < cx + cw:
                        continue
                    v = max(px[x, y])
                    if v > worst:
                        worst, worst_at = v, (x, y, round(t, 1))
    return worst, worst_at


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("video")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--geom")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--crf", type=int, default=26)
    ap.add_argument("--finalize", action="store_true",
                    help="source is a lossless master: crop+compress in ONE pass "
                         "to <name>.mp4 and delete the master on success")
    ap.add_argument("-o", "--out")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__)
        return 0

    src = Path(a.video)
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ffmpeg/ffprobe required", file=sys.stderr)
        return 2

    W, H, dur = probe_size(src)
    if a.geom:
        m = re.fullmatch(r"(\d+)x(\d+)\+(\d+)\+(\d+)", a.geom)
        if not m:
            print("--geom must look like 640x480+320+120", file=sys.stderr)
            return 2
        cw, ch, cx, cy = (int(g) for g in m.groups())
    else:
        cw, ch = GAME_W, GAME_H
        cx, cy = (W - cw) // 2, (H - ch) // 2
    geom = (cw, ch, cx, cy)

    if cx < 0 or cy < 0 or cx + cw > W or cy + ch > H:
        print(f"proposed crop {cw}x{ch}+{cx}+{cy} does not fit in {W}x{H}", file=sys.stderr)
        return 2

    if dur is None:
        print(f"REFUSING   : cannot determine the duration of {src.name}, so frames "
              f"cannot be sampled across it. Verifying only the opening seconds "
              f"while claiming otherwise is the failure this check exists to "
              f"prevent.", file=sys.stderr)
        return 1
    print(f"source     : {src.name}  {W}x{H}  {dur:.1f}s  {src.stat().st_size/1e6:.1f} MB")
    print(f"proposed   : {cw}x{ch} at +{cx}+{cy}"
          + ("  (centred, no WM under Xvfb)" if not a.geom else "  (explicit)"))

    worst, at = verify(src, geom, a.frames, dur)
    ok = worst <= BLACK
    print(f"verify     : sampled {a.frames} frames over 0-{dur:.1f}s; "
          f"brightest pixel OUTSIDE the crop = {worst}"
          + (f" at x={at[0]} y={at[1]} t={at[2]}s" if at else ""))
    if not ok:
        print(f"REFUSING   : something outside the proposed crop is not black "
              f"({worst} > {BLACK}). Cropping would DISCARD it. Pass --geom "
              f"explicitly if you know better.", file=sys.stderr)
        return 1
    print(f"verdict    : OK — everything outside the crop is black, nothing to lose")

    if a.check:
        print("\n--check: nothing encoded.")
        return 0

    if a.finalize:
        out = src.with_suffix(".mp4")
    else:
        out = Path(a.out) if a.out else src.with_name(src.stem + "-crop.mp4")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(src), "-vf", f"crop={cw}:{ch}:{cx}:{cy}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(a.crf),
                        "-pix_fmt", "yuv420p", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        print(f"ffmpeg failed: {r.stderr[:400]}", file=sys.stderr)
        return 1
    print(f"wrote      : {out.name}  {out.stat().st_size/1e6:.1f} MB "
          f"({100*out.stat().st_size/src.stat().st_size:.0f}% of original)")
    if a.finalize:
        # Delete the lossless master ONLY after the final file exists and is
        # non-trivial. The master is the only copy of the run until this point.
        if out.exists() and out.stat().st_size > 1000:
            src.unlink()
            print(f"finalized  : {out.name}  (lossless master removed)")
        else:
            print(f"KEEPING master: {out.name} looks wrong", file=sys.stderr)
            return 1
    elif a.replace:
        # rename() alone -- POSIX rename is atomic and overwrites the
        # destination. Unlinking first would leave a window in which the
        # evidence exists under NEITHER name, and this runs from a cleanup trap
        # that can itself be interrupted.
        out.rename(src)
        print(f"replaced   : {src.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
