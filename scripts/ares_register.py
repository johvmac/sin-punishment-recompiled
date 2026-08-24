#!/usr/bin/env python3
"""Find the GAME VIEWPORT inside an ares capture, and register it to our geometry.

WHY THIS EXISTS (A377/A378)
---------------------------
The capture wrapper records the whole isolated display, so an ares recording
contains the emulator's **menu bar, viewport and status bar**. Measuring the
"content area" of such a frame gives the WINDOW, not the game -- which is how
A376 ended up reporting an aspect of 1.2347 and calling it unexplained. The
viewport is 4:3; the window is not.

WHY THE GEOMETRY IS MEASURED AND NEVER HARD-CODED
-------------------------------------------------
A377 derived `crop=711:535:264:76` for one recording. **That number is not
portable.** It depends on ares' output mode, its window size, and whether
Overscan is on -- all of which the user can and does change, and two of which
changed the same day. A tool carrying a magic crop would keep working and
silently register the wrong region.

THE METHOD, AND WHY IT NEEDS NO ASSUMPTIONS
-------------------------------------------
**The viewport is what MOVES.** Chrome is static between frames; the game is
not. Take the largest CONTIGUOUS band of inter-frame motion, and the menu bar
and status bar fall out on their own -- including the status bar's live VPS
counter, which does move and which defeated a naive "any motion" version.

WHAT THIS CANNOT DO
-------------------
Registration makes the two images the same SHAPE. It does not make them the
same PICTURE: RT64 and ares are different renderers. A378 names four ares
settings that add deliberate differences (interframe blending, colour
emulation, VI filtering, overscan) and they can be turned off -- but the
incidental differences remain, and A377's control floor stands: two genuinely
different scenes from our own build sit 14 bits apart, so any cross-emulator
distance at or above that is noise.

    scripts/ares_register.py --dry-run <video>     # measure, print, touch nothing
    scripts/ares_register.py <video> <outdir> [-t 200 240 ...]
    scripts/ares_register.py --self-check
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_TIMES = [40, 80, 120, 160, 200, 240, 280, 320, 360]
MOTION = 40          # per-pixel grey delta that counts as "this moved"


def _frame(video, t, out):
    # stderr is CAPTURED, not discarded -- the caller decides. A missing input
    # is an expected outcome here (the refusal control exercises it), and letting
    # ffmpeg shout nine times about a file we know is absent buries the real
    # output of the self-check.
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video),
                    "-frames:v", "1", str(out), "-y"],
                   check=True, capture_output=True, text=True)


def _runs(flags):
    """Contiguous True spans as (start, end) inclusive."""
    out, s = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and s is None:
            s = i
        elif not f and s is not None:
            out.append((s, i - 1))
            s = None
    return out


def viewport(images):
    """(x0, y0, w, h) of the game area, from inter-frame motion alone."""
    from PIL import Image
    px = [Image.open(f).convert("L").load() for f in images]
    w, h = Image.open(images[0]).size

    def moved(x, y):
        v = [p[x, y] for p in px]
        return max(v) - min(v) > MOTION

    rows = [any(moved(x, y) for x in range(0, w, 4)) for y in range(h)]
    rr = _runs(rows)
    if not rr:
        raise SystemExit("[areg] REFUSING: nothing moves in these frames at all.")
    # LARGEST CONTIGUOUS BAND, not "any row that moved" -- the status bar's VPS
    # counter moves too, and taking the outer bounds swallows it.
    r = max(rr, key=lambda t: t[1] - t[0])
    inner = range(r[0] + 10, r[1] - 10, 4) if r[1] - r[0] > 30 else range(r[0], r[1] + 1)
    cols = [any(moved(x, y) for y in inner) for x in range(w)]
    cr = _runs(cols)
    c = max(cr, key=lambda t: t[1] - t[0])
    return c[0], r[0], c[1] - c[0] + 1, r[1] - r[0] + 1


def measure(video, tmp):
    imgs = []
    for t in SAMPLE_TIMES:
        p = tmp / f"s{t}.png"
        try:
            _frame(video, t, p)
        except subprocess.CalledProcessError:
            continue
        if p.exists():
            imgs.append(p)
    if len(imgs) < 3:
        raise SystemExit(f"[areg] REFUSING: only {len(imgs)} frames extracted; "
                         f"the geometry would rest on too few samples.")
    x, y, w, h = viewport(imgs)
    return (x, y, w, h), len(imgs)


def report(video, box, n):
    x, y, w, h = box
    ar = w / h
    print(f"  video     : {video}")
    print(f"  frames    : {n} sampled")
    print(f"  viewport  : x {x} y {y}  {w}x{h}")
    print(f"  aspect    : {ar:.4f}   (4:3 = {4/3:.4f}, off by {abs(ar-4/3)/(4/3)*100:.1f}%)")
    print(f"  scale     : {w/320:.3f}x horizontal, {h/240:.3f}x vertical")
    print(f"  ffmpeg    : crop={w}:{h}:{x}:{y},scale=640:480")
    # A viewport that is not ~4:3 means the band found is not the game. Say so
    # rather than emitting a crop that will be trusted.
    if abs(ar - 4 / 3) / (4 / 3) > 0.05:
        print("  WARNING   : that is NOT 4:3. The band found is probably not the "
              "game area — do not register against it without looking at a frame.",
              file=sys.stderr)


def self_check():
    """Controls verified to FAIL, on synthetic frames with a KNOWN answer.

    Synthetic rather than a real capture: the correct viewport has to be known
    independently, or the control is just the code agreeing with itself.
    """
    from PIL import Image
    import random
    import tempfile
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # A 400x300 canvas: static menu bar, a MOVING 160x120 viewport at
        # (100, 40), a static status bar with one small moving counter.
        rnd = random.Random(11)
        imgs = []
        for k in range(5):
            im = Image.new("L", (400, 300), 0)
            p = im.load()
            for x in range(80, 320):
                for y in range(10, 30):
                    p[x, y] = 200                      # menu bar, static
            for x in range(100, 260):
                for y in range(40, 160):
                    p[x, y] = rnd.randrange(256)       # viewport, moves
            for x in range(80, 320):
                for y in range(180, 200):
                    p[x, y] = 60                       # status bar, static
            for x in range(300, 316):
                for y in range(185, 195):
                    p[x, y] = 20 + k * 50              # VPS counter, moves
            f = td / f"f{k}.png"
            im.save(f)
            imgs.append(f)

        box = viewport(imgs)
        chk("finds the viewport, not the whole window",
            box == (100, 40, 160, 120), f"got {box}, want (100, 40, 160, 120)")
        chk("the moving status-bar counter does not extend the viewport",
            box[1] + box[3] <= 180, f"bottom edge {box[1]+box[3]} reaches the status bar")

        # THE BREAK: with the largest-contiguous-band rule removed, the counter's
        # band merges into the answer. Verified here rather than asserted.
        def naive(images):
            from PIL import Image as I
            px = [I.open(f).convert("L").load() for f in images]
            w, h = I.open(images[0]).size
            ys = [y for y in range(h)
                  if any(max(p[x, y] for p in px) - min(p[x, y] for p in px) > MOTION
                         for x in range(0, w, 4))]
            return min(ys), max(ys)
        ny = naive(imgs)
        chk("CONTROL: the naive 'any row that moved' rule really does fail here",
            ny[1] > 180, f"naive gave {ny}; if it passes, this fixture proves nothing")

        chk("REFUSES when too few frames survive extraction",
            _raises(lambda: measure(td / "nope.mp4", td)),
            "a geometry from one or two frames must not be emitted")

    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


def _raises(fn):
    try:
        fn()
    except SystemExit:
        return True
    except Exception:
        return True
    return False


def main():
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    dry = "--dry-run" in a
    a = [x for x in a if x != "--dry-run"]
    times = SAMPLE_TIMES
    if "-t" in a:
        i = a.index("-t")
        times = [int(x) for x in a[i + 1:]]
        a = a[:i]
    video = Path(a[0])
    if not video.exists():
        print(f"[areg] no such video: {video}", file=sys.stderr)
        return 2

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        box, n = measure(video, Path(td))
    if dry:
        print("=== DRY RUN — measured only, nothing written ===")
        report(video, box, n)
        return 0
    if len(a) < 2:
        print("[areg] need an output directory (or use --dry-run)", file=sys.stderr)
        return 2
    out = Path(a[1])
    out.mkdir(parents=True, exist_ok=True)
    report(video, box, n)
    x, y, w, h = box
    for t in times:
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video),
                        "-frames:v", "1", "-vf",
                        f"crop={w}:{h}:{x}:{y},scale=640:480",
                        str(out / f"reg-t{t}.png"), "-y"], check=False)
    print(f"[areg] wrote {len(list(out.glob('reg-t*.png')))} registered frames to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
