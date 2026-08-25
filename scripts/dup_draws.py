#!/usr/bin/env python3
"""Count DUPLICATE draws inside a single submitted frame, offline.

THE QUESTION IT ANSWERS IS U2's, and U2 has been SHELVED since 2026-08-22
because the live instrument it named is in doubt (A316: every slider setting
produced no visible change). U2 asked the user to truncate a tutorial frame
with RT64's `View Draw Call` and report whether the duplicate overlay copies
appear one-per-index, or whether the truncated frame is CLEAN of duplicates.

    A247 predicts CLEAN -- the residue lives in the framebuffer, which is
    never colour-cleared (A304), not in the list.
    The older A219 mechanism predicts copies accumulating index by index.

THE OFFLINE REPLAY IS A STRICTLY BETTER INSTRUMENT FOR THAT QUESTION, and the
reason is structural rather than a matter of convenience: `dl_render.py` draws
the submitted list into an EMPTY image. There is no framebuffer to carry
residue, so a duplicate seen here CANNOT be residue. The slider could never
offer that, because it truncates rendering into the game's own buffer.

WHAT COUNTS AS A DUPLICATE -- two definitions, deliberately, because they mean
different things:

  EXACT   two sub-lists whose projected triangles are identical to 0.01 px.
          Same shape in the same place: the list drawing something twice over
          itself.
  SHAPE   identical after subtracting each sub-list's own centroid. Same shape
          in a DIFFERENT place: the list drawing one element at N positions,
          which is what "multiplied overlay clutter" would look like.

SCOPE: this reads what was SUBMITTED (dl_render's scope, inherited whole). It
says nothing about what the RDP did with it, and a duplicate submitted and then
z-rejected would still be counted here.

    scripts/dup_draws.py frames.json
    scripts/dup_draws.py frames.json --task 5400 --verbose
    scripts/dup_draws.py --self-check
"""
import json
import sys
from collections import defaultdict

Q = 2          # decimal places for the exact signature
QC = 1         # decimal places after centroid removal (looser: float drift)


def sig_exact(tris):
    """Canonical signature of a sub-list: its triangles, order-independent."""
    out = []
    for t in tris:
        vs = sorted(tuple(round(c, Q) for c in v[:2]) for v in t)
        out.append(tuple(vs))
    return tuple(sorted(out))


def sig_shape(tris):
    """Same, with each sub-list translated to its own centroid."""
    pts = [v for t in tris for v in t]
    if not pts:
        return ()
    cx = sum(v[0] for v in pts) / len(pts)
    cy = sum(v[1] for v in pts) / len(pts)
    out = []
    for t in tris:
        vs = sorted((round(v[0] - cx, QC), round(v[1] - cy, QC)) for v in t)
        out.append(tuple(vs))
    return tuple(sorted(out))


def by_sublist(frame):
    """{sublist index: [triangle, ...]} from a dl_render frame record."""
    groups = defaultdict(list)
    for tri in frame.get("tris", []):
        groups[tri["c"]].append(tri["p"])
    return groups


def analyse_rects(frame):
    """Duplicate RECTANGLES -- and this half is not optional.

    The triangle half below would have MISSED the whole question if overlay
    elements are drawn as `G_TEXRECT`, which is how N64 games usually draw a
    HUD. A429 recorded rectangle coordinates for the first time and there are
    56-93 of them per tutorial frame, so ignoring them and calling the frame
    clean would have been a scoped negative dressed up as a general one.

    EXACT is the same rectangle at the same place; SIZE-only is the same
    width and height somewhere else, which is a sprite reused at N positions.
    """
    ex, sz = defaultdict(list), defaultdict(list)
    for i, r in enumerate(frame.get("rects", [])):
        ex[(r["kind"], r["x0"], r["y0"], r["x1"], r["y1"])].append(i)
        sz[(r["kind"], r["x1"] - r["x0"], r["y1"] - r["y0"])].append(i)
    exact = {k: v for k, v in ex.items() if len(v) > 1}
    exact_members = {tuple(sorted(v)) for v in exact.values()}
    size_only = {k: v for k, v in sz.items()
                 if len(v) > 1 and tuple(sorted(v)) not in exact_members}
    return exact, size_only


def analyse(frame):
    groups = by_sublist(frame)
    ex, sh = defaultdict(list), defaultdict(list)
    for idx, tris in groups.items():
        ex[sig_exact(tris)].append(idx)
        sh[sig_shape(tris)].append(idx)
    exact = {k: v for k, v in ex.items() if len(v) > 1}
    shape = {k: v for k, v in sh.items() if len(v) > 1}
    # A shape group that is ALSO an exact group is not separate news.
    exact_members = {tuple(sorted(v)) for v in exact.values()}
    shape_only = {k: v for k, v in shape.items()
                  if tuple(sorted(v)) not in exact_members}
    return groups, exact, shape_only


def report(path, want_task=None, verbose=False):
    frames = json.load(open(path))
    if isinstance(frames, dict):
        frames = frames.get("frames", frames)
    rows = frames if isinstance(frames, list) else list(frames.values())
    any_dup = False
    for fr in rows:
        task = fr.get("task")
        if want_task is not None and task != want_task:
            continue
        groups, exact, shape_only = analyse(fr)
        rex, rsz = analyse_rects(fr)
        ndup = sum(len(v) - 1 for v in exact.values())
        nsh = sum(len(v) - 1 for v in shape_only.values())
        nrex = sum(len(v) - 1 for v in rex.values())
        nrsz = sum(len(v) - 1 for v in rsz.values())
        any_dup = any_dup or ndup or nsh or nrex or nrsz
        print(f"[dup] task={task:<5} sublists={len(groups):<4} "
              f"exact-dup-groups={len(exact):<3} redundant={ndup:<3} "
              f"shape-only-groups={len(shape_only):<3} redundant={nsh}")
        print(f"[dup] task={task:<5} rects={len(fr.get('rects', [])):<6} "
              f"exact-dup-groups={len(rex):<3} redundant={nrex:<3} "
              f"size-only-groups={len(rsz):<3} redundant={nrsz}")
        if verbose:
            for k, v in sorted(rex.items(), key=lambda kv: -len(kv[1])):
                print(f"[dup]   RECT-EXACT x{len(v)} indexes {v} at {k}")
            for k, v in sorted(rsz.items(), key=lambda kv: -len(kv[1]))[:8]:
                print(f"[dup]   RECT-SIZE  x{len(v)} indexes {v[:8]} "
                      f"kind={k[0]} {k[1]}x{k[2]}")
            for k, v in sorted(exact.items(), key=lambda kv: -len(kv[1])):
                print(f"[dup]   EXACT  x{len(v)} sublists {v} "
                      f"({len(k)} tris each)")
            for k, v in sorted(shape_only.items(), key=lambda kv: -len(kv[1])):
                print(f"[dup]   SHAPE  x{len(v)} sublists {v} "
                      f"({len(k)} tris each)")
    if not any_dup:
        print("[dup] no duplicate draws of either kind in any frame reported")
    return 0


# --------------------------------------------------------------------------
# CONTROLS. Four, and they VARY THE FAILURE MODE rather than repeating one
# (A261: four controls that are all duplicate-flagged-or-not are ONE control).
# C1 fires on same-place, C2 must STAY SILENT, C3 must split the two kinds
# apart, C4 must stay silent on a shape that only LOOKS similar in the ways a
# lossy signature would confuse.
# --------------------------------------------------------------------------
def _tri(x, y, s=10.0):
    return [[x, y, 0.0], [x + s, y, 0.0], [x, y + s, 0.0]]


def _frame(tris):
    return {"task": 1, "tris": tris}


def self_check():
    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"[selfcheck] {'PASS' if cond else 'FAIL'} {name} {detail}")

    # C2 first: a frame with three genuinely different sub-lists.
    base = _frame([{"c": 0, "p": _tri(0, 0)},
                   {"c": 1, "p": _tri(50, 0, 20.0)},
                   {"c": 2, "p": _tri(100, 80, 7.5)}])
    _, ex, sh = analyse(base)
    chk("C2 clean frame reports nothing", not ex and not sh,
        f"exact={len(ex)} shape={len(sh)}")

    # C1: an EXACT copy of sub-list 0, same place.
    f1 = _frame(base["tris"] + [{"c": 3, "p": _tri(0, 0)}])
    _, ex, sh = analyse(f1)
    chk("C1 exact copy detected", len(ex) == 1 and sorted(ex.values())[0] == [0, 3],
        f"exact={list(ex.values())}")

    # C3: a TRANSLATED copy -- must be SHAPE, never EXACT. This is the one
    # that discriminates the two questions; a detector that only removes
    # centroids would fail C1's placement, and one that never does fails here.
    f2 = _frame(base["tris"] + [{"c": 3, "p": _tri(200, 150)}])
    _, ex, sh = analyse(f2)
    chk("C3 translated copy is SHAPE not EXACT",
        not ex and len(sh) == 1 and sorted(sh.values())[0] == [0, 3],
        f"exact={len(ex)} shape={list(sh.values())}")

    # C4: same triangle COUNT, different PROPORTIONS. A signature that folded
    # to a count, a bounding box or a centroid would call this a duplicate.
    # It is not one.
    #
    # THIS CONTROL CAUGHT MY OWN FIXTURE FIRST TIME. The injected sub-list was
    # `_tri(-5, -5, 20.0)` -- a same-size triangle at a different position,
    # which IS a shape duplicate of sub-list 1, so a correct detector rightly
    # flagged it and the control read as a failure of the detector. A control
    # is only a control if the fixture means what it claims: the shape here is
    # a SLIVER, which nothing in the frame duplicates at any position.
    f3 = _frame(base["tris"] + [{"c": 3, "p": [[-5.0, -5.0, 0.0],
                                               [25.0, -5.0, 0.0],
                                               [-5.0, -2.0, 0.0]]}])
    _, ex, sh = analyse(f3)
    chk("C4 same-count different-shape is NOT a duplicate", not ex and not sh,
        f"exact={len(ex)} shape={len(sh)}")

    # ---- the RECTANGLE half. Same three failure modes, on the other path.
    def _r(kind, x0, y0, x1, y1):
        return {"kind": kind, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "c": 0}

    rbase = {"task": 1, "rects": [_r("fill", 0, 0, 10, 10),
                                  _r("tex", 40, 40, 56, 56),
                                  _r("tex", 100, 20, 132, 24)]}
    rex, rsz = analyse_rects(rbase)
    chk("C5 clean rect frame reports nothing", not rex and not rsz,
        f"exact={len(rex)} size={len(rsz)}")

    r1 = {"task": 1, "rects": rbase["rects"] + [_r("tex", 40, 40, 56, 56)]}
    rex, rsz = analyse_rects(r1)
    chk("C6 same rect twice in the same place is EXACT",
        len(rex) == 1 and sorted(rex.values())[0] == [1, 3] and not rsz,
        f"exact={list(rex.values())} size={len(rsz)}")

    r2 = {"task": 1, "rects": rbase["rects"] + [_r("tex", 200, 90, 216, 106)]}
    rex, rsz = analyse_rects(r2)
    chk("C7 same-size rect elsewhere is SIZE not EXACT",
        not rex and len(rsz) == 1 and sorted(rsz.values())[0] == [1, 3],
        f"exact={len(rex)} size={list(rsz.values())}")

    # C8: the KIND must matter. A fill and a texrect of identical geometry are
    # different commands doing different things, and folding them together
    # would manufacture duplicates out of the letterbox borders.
    r3 = {"task": 1, "rects": rbase["rects"] + [_r("fill", 40, 40, 56, 56)]}
    rex, rsz = analyse_rects(r3)
    chk("C8 fill vs texrect of the same box is NOT a duplicate",
        not rex and not rsz, f"exact={len(rex)} size={len(rsz)}")

    print(f"[selfcheck] {'ALL PASS' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


def main(argv):
    if "--self-check" in argv:
        return self_check()
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    path = argv[0]
    task = None
    if "--task" in argv:
        task = int(argv[argv.index("--task") + 1])
    return report(path, task, "--verbose" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
