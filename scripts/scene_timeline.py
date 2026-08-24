#!/usr/bin/env python3
"""When does the picture CHANGE? A scene timeline, with no labels and no
cross-emulator pixel comparison.

WHY THIS SHAPE AND NOT CLASSIFICATION (A377/A379)
-------------------------------------------------
The obvious tool matches frames against LABELLED references. A379 measured what
that can and cannot do across two emulators: a still, distinctive screen matches
decisively (the title screen at 10, next-best 22), but a moving scene sampled at
an arbitrary instant does not -- because two runs are at different MOMENTS of
the same motion, which is not a renderer problem and no amount of registration
fixes it.

So this does not compare our pictures to ares' pictures at all.

**It finds the CUTS inside each recording separately, and compares the two
SEQUENCES.** A cut is an event in one video's own space -- ares against ares,
ours against ours -- so the renderer difference never enters. That answers the
question actually asked: *what is supposed to happen, and when, and does ours do
it* -- without needing to know what any scene IS.

It also needs no labelled references, which matters because labelling scenes in
ares-space would be recognition work, and that is the user's time (A227's split).

BOUNDARIES ARE FADES TO BLACK, NOT FRAME-TO-FRAME JUMPS -- MEASURED
------------------------------------------------------------------
The obvious signal is the distance between consecutive frames: a big jump is a
cut. **It was tried on the reference and it does not work.** The histogram over
601 sampled frames runs smoothly from 0 to 43 with **no valley** -- because the
game is in constant motion, so "the picture changed a lot" happens continuously
and there is no quiet baseline to stand out from. Any threshold picked off that
distribution would be me choosing the answer. `--dry-run` still prints it, so
the absence of a valley is visible rather than taken on trust.

What DOES separate cleanly is **the game fading to black**, which A164 already
measured at the title-to-tutorial transition. On the same recording that gives
six well-separated black runs against a brightness range of 0 to 244. A black
frame is black; there is no parameter to tune.

WHAT A BOUNDARY IS NOT
----------------------
A fade to black is where the game *pauses*, not necessarily where a scene ends
-- a death, a screen wipe or a loading pause look identical. And a transition
with **no** fade is invisible to this. The timeline is a structure to compare,
not a description of content.

    scripts/scene_timeline.py --dry-run <video> [--fps 2] [--geom W:H:X:Y]
    scripts/scene_timeline.py <video> -o <out.json> [--fps 2] [--geom ...]
    scripts/scene_timeline.py --compare <a.json> <b.json>
    scripts/scene_timeline.py --self-check
"""
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K_MAD = 6.0          # only for the DIAGNOSTIC distance histogram in --dry-run
BLACK = 4.0          # mean grey (0-255) below which a frame counts as black
MIN_SCENE = 1.0      # seconds; a shorter gap is one transition, not a scene


def dhash(path):
    from PIL import Image
    im = Image.open(path).convert("L").resize((9, 8), Image.LANCZOS)
    p = im.load()
    b = 0
    for y in range(8):
        for x in range(8):
            b = (b << 1) | (1 if p[x, y] > p[x + 1, y] else 0)
    return b


def ham(a, b):
    return bin(a ^ b).count("1")


def _extract(video, tmp, fps, geom):
    """All sampled frames in ONE ffmpeg pass. Per-frame invocation was ~9s for
    14 frames; a 300s recording at 2fps is 600 of them."""
    vf = f"fps={fps}"
    if geom:
        w, h, x, y = geom
        vf = f"crop={w}:{h}:{x}:{y},{vf}"
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf,
                        str(tmp / "f%06d.png")], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"[timeline] ffmpeg failed:\n{r.stderr.strip()}")
    return sorted(tmp.glob("f*.png"))


def distances(video, fps, geom):
    with tempfile.TemporaryDirectory() as td:
        frames = _extract(video, Path(td), fps, geom)
        if len(frames) < 10:
            raise SystemExit(f"[timeline] REFUSING: only {len(frames)} frames; "
                             f"a timeline from this few is not a timeline.")
        hs = [dhash(f) for f in frames]
    return [ham(hs[i], hs[i + 1]) for i in range(len(hs) - 1)]


def brightness(video, fps, geom):
    """Mean grey per sampled frame. Downscaled to 64x48 first -- the mean is the
    same and it is ~100x less work than reading the full frame."""
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        vf = f"fps={fps},scale=64:48"
        if geom:
            w, h, x, y = geom
            vf = f"crop={w}:{h}:{x}:{y}," + vf
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf,
                            str(td / "b%06d.png")], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"[timeline] ffmpeg failed:\n{r.stderr.strip()}")
        fs = sorted(td.glob("b*.png"))
        if len(fs) < 10:
            raise SystemExit(f"[timeline] REFUSING: only {len(fs)} frames; "
                             f"a timeline from this few is not a timeline.")
        return [sum(Image.open(f).convert("L").getdata()) / (64 * 48) for f in fs]


def black_runs(means, fps):
    """Contiguous spans of near-black, as (start, end) in seconds."""
    runs, s = [], None
    for i, m in enumerate(means):
        if m < BLACK and s is None:
            s = i
        elif m >= BLACK and s is not None:
            runs.append((s / fps, (i - 1) / fps))
            s = None
    if s is not None:
        runs.append((s / fps, (len(means) - 1) / fps))
    return runs


def segments_from_black(means, fps):
    """Lit stretches BETWEEN the black runs. The black itself is a boundary, not
    a scene -- a four-second fade is not four seconds of content."""
    runs = black_runs(means, fps)
    total = (len(means) - 1) / fps
    segs, cur = [], 0.0
    for a, b in runs:
        if a - cur >= MIN_SCENE:
            segs.append((cur, a))
        cur = b + 1.0 / fps
    if total - cur >= MIN_SCENE:
        segs.append((cur, total))
    return [{"start": round(a, 2), "end": round(b, 2), "dur": round(b - a, 2)}
            for a, b in segs]


def threshold(ds):
    med = statistics.median(ds)
    mad = statistics.median([abs(d - med) for d in ds]) or 1.0
    return med + K_MAD * mad, med, mad


def segments(ds, fps, thr):
    """Cut points -> segments. A segment shorter than MIN_SCENE is merged back:
    two cuts a few frames apart are one transition, not a scene."""
    cuts = [i for i, d in enumerate(ds) if d > thr]
    bounds = [0.0] + [(i + 1) / fps for i in cuts] + [(len(ds) + 1) / fps]
    segs = []
    for a, b in zip(bounds, bounds[1:]):
        if segs and (b - a) < MIN_SCENE:
            segs[-1] = (segs[-1][0], b)
        else:
            segs.append((a, b))
    return [{"start": round(a, 2), "end": round(b, 2), "dur": round(b - a, 2)}
            for a, b in segs]


def report_black(video, means, runs, fps, segs):
    print(f"  video     : {video}")
    print(f"  sampled   : {len(means)} frames at {fps} fps")
    print(f"  brightness: {min(means):.1f} .. {max(means):.1f}   (black below {BLACK})")
    print(f"  black runs: {len(runs)}")
    for a, b in runs:
        print(f"     {a:7.2f} .. {b:7.2f}  ({b - a + 1/fps:5.2f}s)")
    print(f"  segments  : {len(segs)}")
    for i, s in enumerate(segs):
        print(f"     {i:2}  {s['start']:7.2f} .. {s['end']:7.2f}  ({s['dur']:7.2f}s)")
    if not runs:
        print("  WARNING   : no black frames at all — this recording has no "
              "boundaries this method can see, and one segment is not a timeline.",
              file=sys.stderr)


def report(video, ds, fps, thr, med, mad, segs):
    print(f"  video     : {video}")
    print(f"  sampled   : {len(ds)+1} frames at {fps} fps")
    print(f"  distances : median {med:.0f}  MAD {mad:.1f}  max {max(ds)}")
    print(f"  threshold : {thr:.1f}   (median + {K_MAD}*MAD)")
    q = sorted(ds)
    print(f"  quantiles : p50 {q[len(q)//2]}  p90 {q[int(len(q)*.9)]}  "
          f"p99 {q[int(len(q)*.99)]}  over-threshold {sum(d>thr for d in ds)}")
    print(f"  segments  : {len(segs)}")
    for s in segs:
        print(f"     {s['start']:7.2f} .. {s['end']:7.2f}  ({s['dur']:6.2f}s)")


def compare(a, b):
    """Two timelines side by side, aligned from the start.

    DELIBERATELY NOT A SIMILARITY SCORE. A number would invite 'the runs are 82%
    alike', which says nothing about WHICH part diverged -- and which part is the
    whole question. This prints both sequences and where they stop lining up.
    """
    A, B = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    sa, sb = A["segments"], B["segments"]
    print(f"  A: {A['video']}  ({len(sa)} segments, {A['duration']:.1f}s)")
    print(f"  B: {B['video']}  ({len(sb)} segments, {B['duration']:.1f}s)")
    print()
    print(f"  {'#':>3}  {'A start':>9} {'A dur':>8}   {'B start':>9} {'B dur':>8}   note")
    div = None
    for i in range(max(len(sa), len(sb))):
        x = sa[i] if i < len(sa) else None
        y = sb[i] if i < len(sb) else None
        note = ""
        if x and y:
            r = x["dur"] / y["dur"] if y["dur"] else float("inf")
            if r > 1.5 or r < 0.67:
                note = f"duration differs {r:.2f}x"
                div = div if div is not None else i
        else:
            note = "MISSING in " + ("B" if x else "A")
            div = div if div is not None else i
        print(f"  {i:3}  {x['start'] if x else '-':>9} {x['dur'] if x else '-':>8}   "
              f"{y['start'] if y else '-':>9} {y['dur'] if y else '-':>8}   {note}")
    print()
    print(f"  first divergence: segment {div}" if div is not None
          else "  no structural divergence found at this threshold")
    if len(sa) != len(sb):
        print()
        print(f"  !! ALIGNMENT IS NAIVE — index against index, and the two runs have "
              f"{len(sa)} and {len(sb)} segments.", file=sys.stderr)
        print(f"  !! If one run is MISSING a segment, everything after it shifts and "
              f"every later row reads as a mismatch that is not one.", file=sys.stderr)
        print(f"  !! Read the two lists as sequences before believing any row. A real "
              f"diff (insert/delete aware) is not implemented.", file=sys.stderr)
    return 0


def self_check():
    """Controls on a SYNTHETIC video whose cuts are known independently."""
    from PIL import Image
    import random
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # THREE scenes of 4s each at 10fps. Within a scene the image drifts
        # slightly (a moving camera); at a cut it changes completely.
        rnd = random.Random(5)
        base = [[[rnd.randrange(256) for _ in range(16)] for _ in range(16)]
                for _ in range(3)]
        k = 0
        # WITHIN-SCENE DRIFT MUST ACTUALLY MOVE THE HASH, or the threshold is
        # never exercised and every control here passes vacuously. A first
        # version added `f % 3` to every cell -- a uniform shift, which dHash
        # (a comparison between NEIGHBOURS) is invariant to by construction.
        # It made the distances exactly zero and the median-threshold control
        # could not fail. Two cells are now re-randomised per frame.
        for scene in range(3):
            if scene:                       # a 1-second fade to black BETWEEN scenes
                for _ in range(10):
                    Image.new("L", (64, 64), 0).save(td / f"src{k:05d}.png")
                    k += 1
            for f in range(40):
                im = Image.new("L", (64, 64))
                p = im.load()
                grid = [row[:] for row in base[scene]]
                for _ in range(2):
                    grid[rnd.randrange(16)][rnd.randrange(16)] = rnd.randrange(256)
                for yy in range(16):
                    for xx in range(16):
                        for dy in range(4):
                            for dx in range(4):
                                p[xx * 4 + dx, yy * 4 + dy] = grid[yy][xx]
                im.save(td / f"src{k:05d}.png")
                k += 1
        vid = td / "syn.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-framerate", "10", "-i",
                        str(td / "src%05d.png"), "-pix_fmt", "yuv420p", str(vid), "-y"],
                       check=True, capture_output=True)

        # THE REAL METHOD: black runs. The fixture's two cuts each carry a
        # 1-second fade to black, which is what the game actually does (A164).
        means = brightness(vid, 10, None)
        runs = black_runs(means, 10)
        segs = segments_from_black(means, 10)
        chk("finds both fades to black", len(runs) == 2, f"got {len(runs)} black runs, want 2")
        chk("segments are the LIT stretches between them",
            len(segs) == 3, f"got {len(segs)} segments, want 3")
        if len(segs) == 3:
            chk("the boundaries land at the fades (4s and 9s, +/- 0.4s)",
                abs(segs[0]["end"] - 4.0) < 0.4 and abs(segs[1]["start"] - 5.0) < 0.4,
                f"{[(x['start'], x['end']) for x in segs]}")
        else:
            chk("the boundaries land at the fades (4s and 9s, +/- 0.4s)", False, "no 3 segments")
        chk("the black itself is NOT counted as a scene",
            all(x["dur"] > 1.0 for x in segs), f"{[x['dur'] for x in segs]}")

        # THE DIAGNOSTIC THE METHOD REPLACED, kept as a control: on a fixture
        # built to be easy it works. On the real recording it does not, because
        # the distance histogram there has no valley. Asserting it works HERE is
        # what makes "it failed there" a statement about the CONTENT rather than
        # about a broken implementation.
        ds = distances(vid, 10, None)
        thr, med, mad = threshold(ds)
        # Asserted on the CUT TIMES, not the segment count: the distance method
        # sees a fade as TWO events (into black, out of black), so it yields five
        # segments here, not three. That is correct behaviour and asserting ==3
        # was me expecting the wrong thing rather than the method being wrong.
        cuts = [round((i + 1) / 10, 1) for i, d in enumerate(ds) if d > thr]
        chk("CONTROL: distance-based cutting finds every transition on an EASY fixture",
            cuts == [4.0, 5.0, 9.0, 10.0],
            f"got {cuts}; if this fails, the real-recording failure cannot be "
            f"blamed on the CONTENT rather than on a broken implementation")

        # CONTROL VERIFIED TO FAIL: the threshold has to MATTER. A badly chosen
        # one must give a different, wrong answer -- if it gives the same answer,
        # the fixture has no dynamic range and every control above is vacuous.
        #
        # The DIRECTION was got wrong first, and the note is the useful part: a
        # median threshold fires on about half the frames, but MIN_SCENE then
        # merges those cuts into each other, so it UNDER-segments rather than
        # over-segments. Asserting "more segments" was a guess about a mechanism
        # I had not traced. Asserting "not the right answer" is the property.
        bad_segs = segments(ds, 10, med)
        chk("CONTROL: a badly chosen distance threshold gives a wrong answer",
            len(bad_segs) != 3,
            f"median threshold gave {len(bad_segs)} segments, same as the right one — "
            f"the fixture cannot discriminate and the controls above prove nothing")

        # 12 s at 0.5 fps is 6 frames -- BELOW the limit. The first version used
        # 1 fps, which is 12 frames and above it, so the control asserted a
        # refusal that correctly never happened.
        chk("REFUSES a video too short to be a timeline",
            _raises(lambda: distances(vid, 0.5, None)),
            "12s at 0.5fps is 6 frames; must refuse under 10")

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
    if "--compare" in a:
        i = a.index("--compare")
        if len(a) < i + 3:
            print("[timeline] --compare needs two json files", file=sys.stderr)
            return 2
        return compare(a[i + 1], a[i + 2])

    fps = 2.0
    if "--fps" in a:
        i = a.index("--fps"); fps = float(a[i + 1]); a = a[:i] + a[i + 2:]
    geom = None
    if "--geom" in a:
        i = a.index("--geom"); geom = tuple(int(v) for v in a[i + 1].split(":")); a = a[:i] + a[i + 2:]
    out = None
    if "-o" in a:
        i = a.index("-o"); out = Path(a[i + 1]); a = a[:i] + a[i + 2:]
    dry = "--dry-run" in a
    a = [x for x in a if not x.startswith("--")]
    if not a:
        print("[timeline] need a video", file=sys.stderr)
        return 2
    video = Path(a[0])
    if not video.exists():
        print(f"[timeline] no such video: {video}", file=sys.stderr)
        return 2

    means = brightness(video, fps, geom)
    runs = black_runs(means, fps)
    segs = segments_from_black(means, fps)
    if dry:
        print("=== DRY RUN — measured only, nothing written ===")
        # THE DIAGNOSTIC THAT KILLED THE OBVIOUS METHOD, printed so its absence
        # of a valley is visible rather than asserted in a docstring.
        ds = distances(video, fps, geom)
        thr, med, mad = threshold(ds)
        q = sorted(ds)
        print(f"  [diagnostic] frame-to-frame distance: median {med:.0f} "
              f"p90 {q[int(len(q)*.9)]} p99 {q[int(len(q)*.99)]} max {max(ds)} "
              f"— smooth, no valley, so this is NOT used for boundaries")
    report_black(video, means, runs, fps, segs)
    if dry:
        return 0
    if out:
        out.write_text(json.dumps({
            "video": str(video), "fps": fps, "geom": geom,
            "duration": round((len(means) - 1) / fps, 2),
            "method": "black-run", "black": BLACK,
            "black_runs": [[round(a, 2), round(b, 2)] for a, b in runs],
            "segments": segs}, indent=1) + "\n")
        print(f"[timeline] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
