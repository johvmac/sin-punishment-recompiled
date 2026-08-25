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

    def tri(self, a, b, c):
        vs = [self.cache[i] if 0 <= i < VTX_CACHE else None for i in (a, b, c)]
        if any(v is None for v in vs):
            # A triangle referencing a slot never loaded is DROPPED and
            # COUNTED, never filled with a zero vertex -- an invented vertex at
            # the origin draws a spike through the middle of the frame and
            # looks like geometry.
            self.dropped_tris += 1
            return
        mvp = mat_mul(self.mv, self.proj)
        self.tris.append(tuple(xform(mvp, v) for v in vs) + (self.child,))


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
        elif k == "t":
            replay.tri(int(f[2]), int(f[3]), int(f[4]))
    return replay


def project(tris, w, h):
    """Clip-space -> screen. Drops anything behind the eye rather than
    dividing by a negative w, which mirrors geometry into the frame."""
    out, behind = [], 0
    for t in tris:
        pts, ok = [], True
        for p in t[:3]:
            if p[3] <= 1e-6:
                ok = False
                break
            pts.append(((p[0] / p[3] * 0.5 + 0.5) * w,
                        (1.0 - (p[1] / p[3] * 0.5 + 0.5)) * h))
        if ok:
            out.append((pts, t[3]))
        else:
            behind += 1
    return out, behind


def raster(tris, w, h, fill):
    buf = bytearray(w * h * 3)
    for pts, child in tris:
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
    tris, behind = [], 0
    for t in r.tris:
        pts = []
        for p in t[:3]:
            if p[3] <= 1e-6:
                pts = None
                break
            # Integer screen pixels: sub-pixel precision buys nothing for a
            # step-through viewer and roughly halves the embedded payload.
            pts.append([int((p[0] / p[3] * 0.5 + 0.5) * w),
                        int((1.0 - (p[1] / p[3] * 0.5 + 0.5)) * h)])
        if pts is None:
            behind += 1
            continue                     # dropped, and counted -- never mirrored in
        tris.append({"p": pts, "c": t[3]})
    return {"task": task, "w": w, "h": h, "tris": tris,
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
                  f"behind-eye-dropped={f['behind']}")
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
        for _, c in tris:
            per[c] = per.get(c, 0) + 1
        top = sorted(per.items(), key=lambda kv: -kv[1])[:10]
        print(f"[dlrender] {len(per)} sub-lists drew; largest: " +
              ", ".join(f"#{c}={n}" for c, n in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
