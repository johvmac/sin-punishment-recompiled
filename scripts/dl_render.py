#!/usr/bin/env python3
"""Draw a frame from the game's own display list, with no game and no renderer.

THE USER'S QUESTION (2026-08-25): "if we have the draw calls, how much of a
frame would it be possible for us to construct external to the game itself --
I imagine we couldn't pull in the textures, but could we still get shapes?"

Yes. This replays the ORDERED trace `SNP_DL_GEOM` emits -- matrix loads, matrix
pops, vertex loads and triangles, in list order -- maintains the matrix stack
and the 32-entry vertex cache exactly as the RSP would, transforms, projects,
and writes a PNG.

NO TEXTURES, DELIBERATELY. Triangles are coloured BY SUB-LIST, which answers a
better question than real colours would: A422 measured 739 depth-writing
triangles in a tutorial frame with no sub-list larger than 36. Is that a
character and three enemies, or ninety fragments of something else? Texture
would hide exactly that. Colour-by-child shows it.

WHY IT IS WORTH HAVING AT ALL
-----------------------------
Every geometry claim on this project has come through RT64 or through counts.
This is an independent path from the game's own list to a picture. A421 got
that kind of corroboration by accident (the depth buffer agreed with the census
from the opposite side of the renderer) and it was the most valuable thing that
day.

THE CONTROL, AND IT DECIDES THE WHOLE DESIGN
--------------------------------------------
Reconstruct an ATTRACT frame FIRST -- a scene that demonstrably renders -- and
compare it against the recording of the same run. If the pipeline reproduces a
working scene it can be trusted on a broken one. Pointing it at the tutorial
first would mean believing whatever came out, and matrix-stack emulation is
exactly the kind of thing that fails silently and plausibly.

    scripts/dl_render.py <log> --task 2400 -o attract.png
    scripts/dl_render.py <log> --task 5400 -o tutorial.png --stats
    scripts/dl_render.py --self-check

SCOPE: this shows what was SUBMITTED. It cannot show what the RDP then did with
it -- no clipping, no z-buffering, no combiner. For "is the geometry there at
all", which is A422's live question, that is the right instrument. For "why
does this pixel look wrong", it is not.
"""
import argparse
import re
import struct
import sys
import zlib

# F3DEX2 matrix parameter bits. The PUSH bit is INVERTED by the microcode
# (gsSPMatrix XORs with G_MTX_PUSH), so the raw byte's bit 0 means NOPUSH.
G_MTX_PROJECTION = 0x04
G_MTX_LOAD = 0x02
G_MTX_PUSH_INVERTED = 0x01

VTX_CACHE = 32


def mat_from_words(words):
    """N64 Mtx -> 4x4 floats.

    The fixed-point layout is the trap: the 16 INTEGER halves come first, in
    32 bytes, and the 16 FRACTIONAL halves follow in the next 32 -- they are
    NOT interleaved per element. Reading it as s16.16 pairs in order produces a
    matrix that is plausible, wrong, and wrong in a way that still renders.
    """
    b = b"".join(struct.pack(">I", w) for w in words)
    m = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            off = i * 8 + j * 2
            ip = struct.unpack_from(">h", b, off)[0]
            fp = struct.unpack_from(">H", b, 32 + off)[0]
            m[i][j] = ip + fp / 65536.0
    return m


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)]


def mat_id():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def xform(m, v):
    x, y, z = v
    return [x * m[0][j] + y * m[1][j] + z * m[2][j] + m[3][j] for j in range(4)]


class Replay:
    """The RSP's state machine, as much of it as geometry needs."""

    def __init__(self):
        self.proj = mat_id()
        self.mv = mat_id()
        self.stack = []
        self.cache = [None] * VTX_CACHE
        self.tris = []          # (p0, p1, p2, child) in clip space
        self.child = 0
        self.unresolved_mtx = 0
        self.unresolved_vtx = 0
        self.dropped_tris = 0
        self.rects = []         # (kind, ulx, uly, lrx, lry, sub-list)

    def mtx(self, param, words):
        m = mat_from_words(words)
        if param & G_MTX_PROJECTION:
            self.proj = m if (param & G_MTX_LOAD) else mat_mul(m, self.proj)
        else:
            if not (param & G_MTX_PUSH_INVERTED):     # inverted: 0 means PUSH
                self.stack.append([r[:] for r in self.mv])
            self.mv = m if (param & G_MTX_LOAD) else mat_mul(m, self.mv)

    def pop(self, n):
        for _ in range(n):
            if self.stack:
                self.mv = self.stack.pop()

    def vtx(self, slot, x, y, z):
        if 0 <= slot < VTX_CACHE:
            self.cache[slot] = (x, y, z)

    def tri(self, a, b, c, zupd=1):
        vs = [self.cache[i] if 0 <= i < VTX_CACHE else None for i in (a, b, c)]
        if any(v is None for v in vs):
            # A triangle referencing a slot never loaded is DROPPED and
            # COUNTED, never filled with a zero vertex -- an invented vertex at
            # the origin draws a spike through the middle of the frame and
            # looks like geometry.
            self.dropped_tris += 1
            return
        mvp = mat_mul(self.mv, self.proj)
        # (p0, p1, p2, sub-list, depth-writing?). The last field is A422's
        # Z_UPD and it separates the 3D scene from the 2D overlay.
        self.tris.append(tuple(xform(mvp, v) for v in vs) + (self.child, zupd))


def parse(lines, replay):
    for ln in lines:
        f = ln.split()
        if len(f) < 2:
            continue
        k = f[1]
        if k == "m":
            if "UNRESOLVED" in ln:
                replay.unresolved_mtx += 1
                continue
            replay.mtx(int(f[2], 16), [int(w, 16) for w in f[3:19]])
            replay.child += 1
        elif k == "p":
            replay.pop(int(f[2]))
        elif k == "v":
            if "UNRESOLVED" in ln:
                replay.unresolved_vtx += 1
                continue
            replay.vtx(int(f[2]), int(f[3]), int(f[4]), int(f[5]))
        elif k == "r":
            # rect kind, ulx, uly, lrx, lry -- already in screen pixels.
            replay.rects.append((f[2], int(f[3]), int(f[4]), int(f[5]),
                                 int(f[6]), replay.child))
        elif k == "t":
            # The 4th field is Z_UPD. Traces from before 2026-08-25 lack it and
            # default to 1 -- reproducing the old behaviour rather than
            # silently reclassifying every triangle as overlay.
            replay.tri(int(f[2]), int(f[3]), int(f[4]),
                       int(f[5]) if len(f) > 5 else 1)
    return replay


WMIN = 1e-3
# A vertex still projecting beyond this many frame-widths after clipping is
# degenerate. Counted and dropped, never drawn -- see the guard in project().
GUARD = 8.0
# Above this NDC depth, non-depth-writing geometry is SCENERY rather than
# screen-pinned overlay.
#
# 0.0, NOT 0.5, AND THE DIFFERENCE WAS MEASURED (A430). A428 set it to 0.5 from
# ONE frame, reasoning that nothing sat between 0.442 and 0.918. That read the
# lowest member of the UPPER cluster as if it were the top of the lower one.
# Across all four tutorial frames the real gap is between -0.504 and 0.388 --
# wide, empty, and consistent -- while 0.5 cuts through a populated band: at
# task 5400 the same 138 shadow triangles fall the other side of it and the
# split swings from 144 screen-pinned to 6.
#
# Still a heuristic. But now it sits in the gap the data actually has, checked
# on four frames rather than one.
SCENE_Z = 0.0


def _clip_plane(poly, dist):
    """Sutherland-Hodgman against one plane, `dist(v) >= 0` meaning inside."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        da, db = dist(a), dist(b)
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            t = da / (da - db)
            out.append([a[k] + t * (b[k] - a[k]) for k in range(4)])
    return out


def clip_near(v0, v1, v2):
    """Clip a clip-space triangle, returning 0..n triangles.

    WITHOUT THIS, A TRIANGLE CROSSING THE EYE PLANE EXPLODES. Measured on real
    data: task 600 draw 61 projected to 6,928% of the screen and task 2400
    reached 53,889%, which is what made the environment paint over the
    characters in the viewer. Dropping the whole triangle would instead delete
    geometry that is partly visible, so it is clipped and re-triangulated.

    TWO PLANES, AND THE SECOND IS THE ONE THAT MATTERS. `w >= WMIN` alone does
    NOT bound anything -- coordinates still divide by a near-zero w, which the
    self-check caught. The real near plane is `z + w >= 0`; there w equals the
    near distance rather than zero, so the divide stays finite. Both are
    applied: the standard plane for correctness, the numerical one for safety.
    """
    poly = _clip_plane([list(v0), list(v1), list(v2)], lambda v: v[3] - WMIN)
    if len(poly) < 3:
        return []
    poly = _clip_plane(poly, lambda v: v[2] + v[3])
    if len(poly) < 3:
        return []
    return [(poly[0], poly[i], poly[i + 1]) for i in range(1, len(poly) - 1)]


def project(tris, w, h):
    """Clip-space -> screen, WITH near-plane clipping and NDC depth.

    Returns (screen_tris, dropped). Each screen triangle carries a per-vertex
    depth `z/w`, which is LINEAR IN SCREEN SPACE and so can be interpolated
    barycentrically by a depth test -- that is what makes a real z-buffer
    possible downstream. Painter's order alone is wrong for this data: the game
    draws characters first and environment after, and on hardware the depth
    test rejects the later surface. Without depth the environment paints over
    the characters and they vanish (the user, reading task 600, 2026-08-25).
    """
    out, dropped = [], 0
    for t in tris:
        pieces = clip_near(t[0], t[1], t[2])
        if not pieces:
            dropped += 1
            continue
        for piece in pieces:
            pts = []
            for p in piece:
                pts.append(((p[0] / p[3] * 0.5 + 0.5) * w,
                            (1.0 - (p[1] / p[3] * 0.5 + 0.5)) * h,
                            p[2] / p[3]))
            # GUARD: anything still off in the distance after two clip planes
            # is degenerate. Counted and dropped rather than drawn -- a single
            # such triangle covers the frame and reads as a solid surface.
            if any(abs(p[0]) > GUARD * w or abs(p[1]) > GUARD * h for p in pts):
                dropped += 1
                continue
            out.append((pts, t[3], t[4] if len(t) > 4 else 1))
    return out, dropped


def raster(tris, w, h, fill):
    buf = bytearray(w * h * 3)
    for pts, child, _zu in tris:
        r = (child * 97) % 200 + 55
        g = (child * 57) % 200 + 55
        b = (child * 151) % 200 + 55
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if fill:
            x0, x1 = max(0, int(min(xs))), min(w - 1, int(max(xs)))
            y0, y1 = max(0, int(min(ys))), min(h - 1, int(max(ys)))
            if (x1 - x0) * (y1 - y0) > w * h // 2:
                continue                      # degenerate/huge, skip
            (ax, ay), (bx, by), (cx, cy) = pts
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-9:
                continue
            for py in range(y0, y1 + 1):
                for px in range(x0, x1 + 1):
                    l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
                    l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
                    if l1 >= 0 and l2 >= 0 and l1 + l2 <= 1:
                        o = (py * w + px) * 3
                        buf[o] = r; buf[o + 1] = g; buf[o + 2] = b
        else:
            for i in range(3):
                _line(buf, w, h, pts[i], pts[(i + 1) % 3], r, g, b)
    return buf


def _line(buf, w, h, p, q, r, g, b):
    x0, y0, x1, y1 = int(p[0]), int(p[1]), int(q[0]), int(q[1])
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    if dx > 4000 or dy > 4000:
        return
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        if 0 <= x0 < w and 0 <= y0 < h:
            o = (y0 * w + x0) * 3
            buf[o] = r; buf[o + 1] = g; buf[o + 2] = b
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy; x0 += sx
        if e2 < dx:
            err += dx; y0 += sy


def write_png(path, buf, w, h):
    raw = b"".join(b"\x00" + bytes(buf[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    open(path, "wb").write(png)


def tasks_in(logpath):
    return [int(t) for t in re.findall(r"\[dlgeom\] task=(\d+) BEGIN",
                                       open(logpath, errors="replace").read())]


def frame_json(logpath, task, w, h):
    """One frame as plain data, IN LIST ORDER, for the step-through viewer.

    Order is the whole value here: the viewer reveals triangles one draw at a
    time, which is what RT64's own 'View Draw Call' was supposed to do and
    could not (A316/A332 — every setting produced no visible change, because
    the colour buffer is never cleared in the tutorial so the old picture just
    stayed). Offline we control the rasteriser, so an incremental draw is
    actually incremental.
    """
    r = parse(extract(logpath, task), Replay())
    scr, behind = project(r.tris, w, h)
    tris = []
    for pts, c, zu in scr:
        # Integer screen pixels; depth kept to 4 decimals, which is ample for a
        # depth TEST and keeps the embedded payload down.
        # THREE-WAY, and the threshold lives HERE rather than in the page.
        # A428: the non-depth-writing triangles are two populations, not one --
        # scenery at scene depth (the pylons) and screen-pinned overlay (the
        # controller). Calling both "2D overlay" was wrong and hid the pylons.
        #   d = depth-writing        s = scene depth, no depth-write
        #   o = screen-pinned overlay
        # SCENE_Z is a HEURISTIC on a bimodal distribution (nothing between
        # 0.44 and 0.92 in the frames measured), not a principled boundary.
        if zu:
            kind = "d"
        else:
            kind = "s" if min(p[2] for p in pts) > SCENE_Z else "o"
        tris.append({"p": [[int(p[0]), int(p[1]), round(p[2], 4)] for p in pts],
                     "c": c, "z": zu, "k": kind})
    return {"task": task, "w": w, "h": h, "tris": tris,
            "rects": [{"kind": k, "x0": a, "y0": b, "x1": c2, "y1": d2, "c": ch}
                      for k, a, b, c2, d2, ch in r.rects],
            "behind": behind, "dropped": r.dropped_tris,
            "matrices": r.child, "built": len(r.tris)}


def extract(logpath, task):
    want, out = f"task={task} BEGIN", []
    on = False
    for ln in open(logpath, errors="replace"):
        if "[dlgeom]" not in ln:
            continue
        if want in ln:
            on = True
            continue
        if on and f"task={task} END" in ln:
            break
        if on:
            out.append(ln.strip())
    return out


def self_check():
    """Controls on the parts that fail SILENTLY. Each must be able to fail."""
    ok = fail = 0

    def chk(label, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    # 1. The fixed-point layout: integer halves first, THEN fractions.
    #    Element [0][0] = 2.5 -> integer 2 at offset 0, fraction 0x8000 at 32.
    words = [0] * 16
    words[0] = 0x00020000            # int part of m[0][0] = 2
    words[8] = 0x80000000            # frac part of m[0][0] = 0x8000
    m = mat_from_words(words)
    chk("s15.16 halves are split 32/32, not interleaved", abs(m[0][0] - 2.5) < 1e-6)

    # 2. A vertex through an identity MVP lands where it started.
    r = Replay()
    idw = [0] * 16
    for i in range(4):
        off = i * 8 + i * 2
        idw[off // 4] |= 1 << (16 if off % 4 == 0 else 0)
    r.proj = mat_id(); r.mv = mat_id()
    r.vtx(0, 10, 20, 30); r.vtx(1, 40, 50, 60); r.vtx(2, 70, 80, 90)
    r.tri(0, 1, 2)
    chk("identity transform preserves a vertex", r.tris and
        abs(r.tris[0][0][0] - 10) < 1e-6 and abs(r.tris[0][0][1] - 20) < 1e-6)

    # 3. DISCRIMINATING: a triangle citing an unloaded slot must be DROPPED,
    #    not filled with a zero vertex. A zero vertex draws a spike to the
    #    origin that reads as real geometry -- the same class as the census
    #    refusing an unset segment instead of defaulting it to 0.
    r2 = Replay()
    r2.vtx(0, 1, 1, 1)
    r2.tri(0, 5, 9)
    chk("a triangle citing an unloaded slot is dropped and counted",
        len(r2.tris) == 0 and r2.dropped_tris == 1)

    # 4. DISCRIMINATING: the PUSH bit is INVERTED in F3DEX2. A raw param of 0
    #    means PUSH; if we read it the gbi.h way the stack never grows and
    #    every child inherits its sibling's transform.
    r3 = Replay()
    r3.mtx(0x00, [0] * 16)          # modelview, mul, raw 0 == PUSH
    chk("raw param 0 PUSHES the modelview stack (inverted bit)", len(r3.stack) == 1)
    r4 = Replay()
    r4.mtx(0x01, [0] * 16)          # raw 1 == NOPUSH
    chk("raw param 1 does NOT push", len(r4.stack) == 0)

    # 5. DISCRIMINATING: geometry behind the eye must be dropped, not divided
    #    by a negative w -- that mirrors it into frame as plausible shapes.
    front = [((0, 0, 0, 1), (1, 0, 0, 1), (0, 1, 0, 1), 0)]
    back = [((0, 0, 0, -1), (1, 0, 0, -1), (0, 1, 0, -1), 0)]
    _, nb_f = project(front, 320, 240)
    _, nb_b = project(back, 320, 240)
    chk("geometry behind the eye is dropped, in front is kept",
        nb_f == 0 and nb_b == 1)

    # 6. DISCRIMINATING: a triangle STRADDLING the eye plane must be CLIPPED,
    #    not dropped and not projected whole. Dropping deletes geometry that is
    #    partly visible; projecting it whole is what produced a triangle
    #    covering 53,889% of the screen on real data.
    # Clip-space values as a real perspective matrix produces them: w is the
    # view depth, z runs to -w at the near plane. One vertex is well inside
    # the frustum, one is beyond the near plane.
    strad = [((0.0, 0.0, -1.0, 2.0), (1.0, 0.0, -1.0, 2.0),
              (0.0, 1.0, -5.0, 1.0), 0)]
    got, dropped = project(strad, 320, 240)
    inside = all(abs(p[0]) <= GUARD * 320 and abs(p[1]) <= GUARD * 240
                 for t in got for p in t[0])
    chk("a triangle crossing the near plane is CLIPPED, not exploded",
        len(got) >= 1 and inside)

    # 7. Depth survives projection and is finite -- the z-buffer needs it.
    chk("each projected vertex carries a finite NDC depth",
        all(isinstance(p[2], float) and p[2] == p[2] for t in got for p in t[0]))

    print(f"\n[dlrender] self-check {ok}/{ok + fail}")
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("log", nargs="?")
    ap.add_argument("--task", type=int)
    ap.add_argument("-o", "--out", default="frame.png")
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--fill", action="store_true", help="filled tris, not wireframe")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--json-all", metavar="OUT",
                    help="every dumped frame in the log as JSON, in list order")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__)
        return 0
    if a.self_check:
        return self_check()
    if a.json_all:
        if not a.log:
            print("need <log>", file=sys.stderr)
            return 2
        found = tasks_in(a.log)
        if not found:
            print(f"[dlrender] no [dlgeom] traces in {a.log}", file=sys.stderr)
            return 1
        frames = [frame_json(a.log, t, a.width, a.height) for t in found]
        import json
        open(a.json_all, "w").write(json.dumps({"frames": frames}))
        for f in frames:
            print(f"[dlrender] task={f['task']:<6} tris={len(f['tris']):<6} "
                  f"sublists={len({t['c'] for t in f['tris']}):<4} "
                  f"clipped/dropped={f['behind']}")
        print(f"[dlrender] wrote {a.json_all} ({len(frames)} frame(s))")
        return 0
    if not a.log or a.task is None:
        print("need <log> and --task (or --self-check)", file=sys.stderr)
        return 2

    lines = extract(a.log, a.task)
    if not lines:
        print(f"[dlrender] no [dlgeom] trace for task={a.task} in {a.log}",
              file=sys.stderr)
        return 1
    r = parse(lines, Replay())
    tris, behind = project(r.tris, a.width, a.height)
    buf = raster(tris, a.width, a.height, a.fill)
    write_png(a.out, buf, a.width, a.height)

    print(f"[dlrender] task={a.task}  trace lines={len(lines)}")
    print(f"[dlrender] matrices={r.child}  cached-vtx-loads ok  "
          f"triangles built={len(r.tris)}  drawn={len(tris)}")
    print(f"[dlrender] DROPPED: behind-eye={behind}  unloaded-slot={r.dropped_tris}  "
          f"unresolved mtx={r.unresolved_mtx} vtx={r.unresolved_vtx}")
    print(f"[dlrender] wrote {a.out}  ({a.width}x{a.height}, "
          f"{'filled' if a.fill else 'wireframe'}, coloured by sub-list)")
    if a.stats:
        per = {}
        for _, c, _z in tris:
            per[c] = per.get(c, 0) + 1
        top = sorted(per.items(), key=lambda kv: -kv[1])[:10]
        print(f"[dlrender] {len(per)} sub-lists drew; largest: " +
              ", ".join(f"#{c}={n}" for c, n in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
