#!/usr/bin/env python3
"""Say which known scenes a run recording reached, and when.

WHY THIS EXISTS
---------------
Scene identity has been read off sampled stills by eye three times and been
wrong three times (A93, A161, and the inherited "title scene" label on A99).
T83 made every run a recording so the frames all exist; this turns the recording
into a machine-readable timeline so nobody has to squint at artwork again.

WHAT IT DOES
------------
Perceptual hash (dHash, 8x8 -> 64 bits) of each sampled frame, compared against
a directory of LABELLED reference frames. dHash compares relative brightness
between neighbouring pixels, so it survives h264 quantisation and small
brightness shifts while still separating genuinely different images.

References live in `<archive>/scene-refs/<label>.png` and come from OUR OWN
build at 640x480 -- not from the ares captures, which are screenshots of a
different emulator's window at a different size and would need registering
first.

WHAT IT CAN AND CANNOT SUPPORT
------------------------------
* PRESENCE: strong. "label X appears at t=..." is a direct match.
* ABSENCE: only as strong as the sampling and the threshold, and BOTH are
  reported for exactly that reason. With `--fps 0` every frame is examined, and
  then "X never appears" is a claim about every frame in the file rather than
  about the instants somebody happened to look at. That is the whole point of
  recording instead of sampling -- do not throw it away with a coarse --fps and
  then write "never".

The per-frame best distance is always reported, so a NEAR miss is visible
rather than swallowed by the threshold.

Usage:
    scripts/classify_recording.py <video> [--fps 2] [--threshold 12]
    scripts/classify_recording.py --self-check
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_REFS = Path("/media/joh/extra/sin-punishment-archive/scene-refs")


def dhash(img, size=8):
    """64-bit difference hash: compare each pixel with its right-hand neighbour."""
    im = img.convert("L").resize((size + 1, size))
    px = im.load()
    bits = 0
    for y in range(size):
        for x in range(size):
            bits = (bits << 1) | (1 if px[x, y] < px[x + 1, y] else 0)
    return bits


def ham(a, b):
    return bin(a ^ b).count("1")


def load_refs(d):
    from PIL import Image
    refs = {}
    for f in sorted(Path(d).glob("*.png")):
        refs[f.stem] = dhash(Image.open(f))
    return refs


def sample(video, fps, outdir):
    """Extract frames. fps=0 means EVERY frame."""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if fps and fps > 0:
        args += ["-vf", f"fps={fps}"]
    args += [str(Path(outdir) / "f%06d.png")]
    subprocess.run(args, capture_output=True)
    return sorted(Path(outdir).glob("*.png"))


def classify(video, refs, fps, threshold):
    from PIL import Image
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True).stdout.strip() or 0)
    rows = []
    with tempfile.TemporaryDirectory() as d:
        frames = sample(video, fps, d)
        n = len(frames)
        for i, f in enumerate(frames):
            h = dhash(Image.open(f))
            best, bestd = None, 65
            for name, rh in refs.items():
                dd = ham(h, rh)
                if dd < bestd:
                    best, bestd = name, dd
            t = (dur * i / n) if n and dur else i
            rows.append((t, best if bestd <= threshold else None, bestd))
    return rows, dur


def runs_of(rows):
    """Collapse consecutive same-label rows into ranges."""
    out = []
    for t, lab, d in rows:
        if out and out[-1][2] == lab:
            out[-1][1] = t
            out[-1][3] = min(out[-1][3], d)
        else:
            out.append([t, t, lab, d])
    return out


def self_check():
    """The control: references must match THEMSELVES and NOT each other."""
    from PIL import Image
    refs_dir = DEFAULT_REFS
    checks = []
    if not refs_dir.exists():
        print(f"FAIL  reference dir missing: {refs_dir}")
        return 1
    files = sorted(refs_dir.glob("*.png"))
    hashes = {f.stem: dhash(Image.open(f)) for f in files}
    checks.append((f"{len(files)} reference frame(s) load", len(files) >= 2,
                   ", ".join(hashes)))
    # Self-match is trivial (distance 0) and proves almost nothing on its own.
    # DISCRIMINATION is the real control: title must not look like attract.
    if "title-screen" in hashes:
        worst = None
        for name, h in hashes.items():
            if name == "title-screen" or name.startswith("title"):
                continue
            d = ham(hashes["title-screen"], h)
            if worst is None or d < worst[1]:
                worst = (name, d)
        checks.append(("title-screen is FAR from every attract reference",
                       worst is not None and worst[1] >= 20,
                       f"closest non-title is {worst[0]} at distance {worst[1]}"
                       if worst else "no non-title refs"))
    # Two attract frames are different moments of the same cinematic: they should
    # NOT be identical, or the hash is too coarse to locate anything.
    at = [n for n in hashes if n.startswith("attract")]
    if len(at) >= 2:
        d = ham(hashes[at[0]], hashes[at[1]])
        checks.append(("distinct attract moments are distinguishable (hash not degenerate)",
                       d > 0, f"distance {d} between {at[0]} and {at[1]}"))
    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:56} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--refs", default=str(DEFAULT_REFS))
    ap.add_argument("--fps", type=float, default=2.0,
                    help="frames per second to examine; 0 = EVERY frame")
    ap.add_argument("--threshold", type=int, default=12)
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__)
        return 0
    if a.self_check:
        return self_check()
    if not a.video:
        print(__doc__)
        return 2

    refs = load_refs(a.refs)
    if not refs:
        print(f"no reference frames in {a.refs}", file=sys.stderr)
        return 2
    rows, dur = classify(Path(a.video), refs, a.fps, a.threshold)
    print(f"{Path(a.video).name}: {dur:.1f}s, {len(rows)} frames examined "
          f"({'EVERY frame' if a.fps == 0 else f'{a.fps} fps'}), "
          f"threshold {a.threshold}, refs: {', '.join(sorted(refs))}")
    print()
    for start, end, lab, d in runs_of(rows):
        name = lab if lab else "(unmatched)"
        print(f"  {start:7.1f}s - {end:7.1f}s   {name:16} best distance {d}")
    print()
    seen = {lab for _s, _e, lab, _d in runs_of(rows) if lab}
    for name in sorted(refs):
        print(f"  {'REACHED    ' if name in seen else 'not matched'} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
