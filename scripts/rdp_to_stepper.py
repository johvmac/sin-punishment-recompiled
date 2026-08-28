#!/usr/bin/env python3
"""Convert an ares `--dump-log rdp:...` stream into the draw-call stepper's JSON.

THE USER'S REQUEST (2026-08-28): "hook the dump up to our draw call
visualisation artefact so that I can step through it similarly" -- i.e. the
REFERENCE emulator's draws, in the same stepper that already shows ours.

WHAT THIS IS NOT
----------------
**RDP triangles are not our draw calls, and the page says so.** Ours come from
replaying the F3DEX2 DISPLAY LIST offline: object space, pre-cull, grouped by
matrix set-up. These come from the RDP COMMAND STREAM: screen space,
post-transform, post-cull, with no grouping in the data at all. A608 made this
point about counting and it applies at least as strongly to stepping. Use the
two side by side to compare WHAT IS ON SCREEN WHERE -- not to compare counts.

THE RECONSTRUCTION, which is the whole reason this file exists
--------------------------------------------------------------
An RDP triangle is three EDGES, not three vertices. Word 0 carries the three
scanlines YH/YM/YL (11.2 fixed); words 1-3 carry, as signed 16.16, the x and
dx/dy of the low, high and mid edges respectively -- ares's fetchEdge reads them
in exactly that order (render.cpp). Before 2026-08-28 the capture discarded
words 1-3, which is why every earlier dump could say y:[592,585,530] and never
say where on the scanline the triangle was.

  v1 = (XH, YH)                      the top vertex: major and mid edge meet
  v2 = (XL, YM)                      where the two minor edges meet
  v3 = (XH + DxHDy*(YL-YH), YL)      the bottom of the major edge

CONTROLS (T71 gate 2), all of which can fail:
  C1 Y CROSS-CHECK   -- our YL/YM/YH must equal the triple ares itself printed
     in the Data column. That string is produced by decode.cpp, a decoder
     independent of this file, so a wrong bit offset here shows up as a
     mismatch rather than as plausible numbers.
  C2 TOP-VERTEX IDENTITY -- XH and XM are both "x at YH" (the major and mid
     edges share the top vertex), so they must agree. They come from DIFFERENT
     WORDS, so this fails loudly if the word order is wrong.
     **IT APPLIES ONLY TO NON-DEGENERATE TRIANGLES.** 45% of this game's
     triangles have YM==YH or YM==YL, which makes the mid or low edge zero-height
     and XM unconstrained; the first version of this check counted those as
     failures and reported a scary 41% before the exclusion. On proper triangles
     79.4% agree to within 1px and the rest have a median error of 2.26px --
     sub-scanline snapping in the RSP's own coefficient generation, not a decode
     error. The wrong premise (XL on the MAJOR edge) holds on only 15%, so the
     check still discriminates; it is a threshold, not an equality.
  C2b THE DECISIVE CONTROL IS VISUAL, because C2 is an argument and an argument
     may flag a measurement without settling it (T107). Rasterising the
     reconstruction yields a coherent perspective corridor matching the
     tutorial; rasterising it with words 1-3 permuted yields sliver hash. See
     the playbook section "Reference draw commands into the stepper".
  C3 BOUNDS -- reconstructed vertices should mostly land inside the scissor.
     Weak on its own, reported as a percentage rather than asserted, because
     off-screen geometry is a thing we are actively looking for (A218).
  C4 FALSIFICATION -- `--self-check` reconstructs a synthetic triangle whose
     answer is known, then permutes words 1-3 and asserts the checks FAIL.
     A control that cannot fail is not a control (T65).

    scripts/rdp_to_stepper.py <dump.txt> --dry-run
    scripts/rdp_to_stepper.py <dump.txt> -o reference.json
    scripts/rdp_to_stepper.py --self-check
"""
import argparse
import json
import re
import sys
from pathlib import Path

FRAME_RE = re.compile(r"^=== frame (\d+) \((\d+) RSP \+ (\d+) RDP commands\) ===")
# ares prints y:[YL,YM,YH] raw (11.2 fixed, see decode.cpp case 0x08..0x0f).
YTRIPLE_RE = re.compile(r"y:\[(\d+),(\d+),(\d+)\]")

TRI_OPS = {"Triangle (Fill)", "Triangle (Z)", "Triangle (Tex)", "Triangle (Tex Z)",
           "Triangle (Shade)", "Triangle (Shade Z)", "Triangle (Shade Tex)",
           "Triangle (Shade Tex Z)"}
# Z-buffered triangle opcodes carry the two zbuffer coefficient words.
ZBUF_OPS = {"Triangle (Z)", "Triangle (Tex Z)", "Triangle (Shade Z)",
            "Triangle (Shade Tex Z)"}
# Any of these ends a run of primitives; see group_note().
STATE_OPS = {"Set Tile", "Tex Image", "Color Combiner", "Other Modes", "Tile Size",
             "Load Block", "Load Tile", "Load Tex LUT", "Fill Color", "Env Color",
             "Prim Color", "Blend Color", "Fog Color", "Color Image", "Depth Image",
             "Scissor", "Prim Depth", "Key GB", "Key R", "Convert"}

# The texture bank our build never binds, at any point in the run (A617/A618).
# Triangles textured from it are tagged b=1 and are, as far as every measurement
# to date goes, exactly the geometry missing from our tutorial.
BANK_LO, BANK_HI = 0x00206000, 0x00234000

NATIVE_W, NATIVE_H = 320, 240   # verified per frame against the Scissor command
# OUR OWN FRAMES ARE 320x240 (dup-frames-8tasks.json, 2026-08-25), and RDP
# screen space already IS 320x240, so the reference is emitted 1:1. Emitting it
# at 640x480 would have drawn the reference at twice our scale in the same
# canvas and made a side-by-side comparison silently meaningless.
OUT_W, OUT_H = NATIVE_W, NATIVE_H


def s14(v):
    v &= 0x3FFF
    return v - 0x4000 if v & 0x2000 else v


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def fx1616(word, shift):
    """Signed 16.16 packed as (integer << 16 | fraction) at `shift` in `word`."""
    i = s16(word >> (shift + 16))
    f = (word >> shift) & 0xFFFF
    return i + f / 65536.0


def group_note():
    return ("Draw boundaries are CONSTRUCTED by scripts/rdp_to_stepper.py as "
            "maximal runs of primitives between state changes. The RDP stream "
            "contains no draw-call boundaries of its own.")


def parse_tri(words, native_w, native_h):
    """Reconstruct one triangle. Returns (v1, v2, v3, zvals, checks) or None."""
    if len(words) < 4:
        return None
    w0, wl, wh, wm = words[0], words[1], words[2], words[3]

    yl_raw, ym_raw, yh_raw = (w0 >> 32) & 0x3FFF, (w0 >> 16) & 0x3FFF, w0 & 0x3FFF
    yl, ym, yh = s14(yl_raw) / 4.0, s14(ym_raw) / 4.0, s14(yh_raw) / 4.0

    xl, dxldy = fx1616(wl, 32), fx1616(wl, 0)
    xh, dxhdy = fx1616(wh, 32), fx1616(wh, 0)
    xm, dxmdy = fx1616(wm, 32), fx1616(wm, 0)

    v1 = (xh, yh)
    v2 = (xl, ym)
    v3 = (xh + dxhdy * (yl - yh), yl)

    checks = {"yraw": (yl_raw, ym_raw, yh_raw), "xh": xh, "xm": xm}
    return v1, v2, v3, (yh, ym, yl), checks, (dxldy, dxmdy)


def tri_depth(words, nzwords, v1, v2, v3):
    """Per-vertex z from the zbuffer coefficients, if this opcode has them.

    Z is a plane: Z(x,y) = d + dzdx*(x-XH) + dzdy*(y-YH), with d the depth at
    the major edge's top vertex. Returns three floats in 0..1, or None.
    """
    if nzwords is None or len(words) < nzwords + 2:
        return None
    wz0 = words[nzwords]
    wz1 = words[nzwords + 1]
    d = fx1616(wz0, 32)
    dzdx = fx1616(wz0, 0)
    dzdy = fx1616(wz1, 0)
    x0, y0 = v1
    out = []
    for (x, y) in (v1, v2, v3):
        z = d + dzdx * (x - x0) + dzdy * (y - y0)
        out.append(z / 32768.0)   # s15.16 depth -> roughly 0..1
    return out


def zword_offset(name):
    """Index of the first zbuffer word for a z-buffered triangle opcode."""
    if name == "Triangle (Z)":
        return 4                      # edge 4
    if name == "Triangle (Tex Z)":
        return 12                     # edge 4 + texture 8
    if name == "Triangle (Shade Z)":
        return 12                     # edge 4 + shade 8
    if name == "Triangle (Shade Tex Z)":
        return 20                     # edge 4 + shade 8 + texture 8
    return None


def convert(path, verbose=True):
    frames = []
    cur = None
    stats = {"c1_pass": 0, "c1_fail": 0, "c2_max": 0.0, "c2_bad": 0,
             "c2_n": 0, "c2_err": [], "degen": 0,
             "tris": 0, "rects": 0, "short": 0, "inb": 0}

    for line in Path(path).read_text(errors="replace").splitlines():
        m = FRAME_RE.match(line)
        if m:
            cur = {"task": int(m.group(1)), "w": OUT_W, "h": OUT_H,
                   "src": "reference", "tris": [], "rects": [],
                   "matrices": 0, "built": 0, "behind": 0,
                   "_group": 0, "_dirty": False,
                   "_scissor": None, "_zupd": True, "_timg": None}
            frames.append(cur)
            continue
        if cur is None or not line.startswith("RDP\t"):
            continue
        f = line.split("\t")
        if len(f) < 7:
            continue
        name, data, hexcol = f[4], f[5], f[6]
        words = [int(t, 16) for t in hexcol.split() if t]
        if not words:
            continue
        w0 = words[0]

        if name == "Tex Image":
            # A617/A621: the texture image in force when a triangle is issued.
            # Tracked in stream order because that is how the RDP resolves it.
            cur["_timg"] = w0 & 0x3FFFFFF
        if name == "Scissor":
            cur["_scissor"] = (((w0 >> 44) & 0xFFF) / 4.0, ((w0 >> 32) & 0xFFF) / 4.0)
        if name == "Other Modes":
            cur["_zupd"] = bool((w0 >> 5) & 1)      # render.cpp:455
        if name in STATE_OPS:
            if cur["_dirty"]:
                cur["_group"] += 1
                cur["_dirty"] = False
            continue

        if name in TRI_OPS:
            stats["tris"] += 1
            if len(words) < 4:
                stats["short"] += 1
                continue
            got = parse_tri(words, NATIVE_W, NATIVE_H)
            if not got:
                stats["short"] += 1
                continue
            v1, v2, v3, ys, checks, _ = got

            ym_ = YTRIPLE_RE.search(data)
            if ym_:
                want = (int(ym_.group(1)), int(ym_.group(2)), int(ym_.group(3)))
                if want == checks["yraw"]:
                    stats["c1_pass"] += 1
                else:
                    stats["c1_fail"] += 1
            # C2 only means anything where the mid edge has height. See the
            # module docstring: 45% of this game's triangles are degenerate in
            # this sense and XM is unconstrained for them.
            yh_, ym_v, yl_ = ys
            if ym_v != yh_ and ym_v != yl_:
                dx = abs(checks["xh"] - checks["xm"])
                stats["c2_n"] += 1
                stats["c2_max"] = max(stats["c2_max"], dx)
                if dx > 1.0:
                    stats["c2_bad"] += 1
                    stats["c2_err"].append(dx)
            else:
                stats["degen"] += 1

            zs = tri_depth(words, zword_offset(name), v1, v2, v3)
            sx, sy = OUT_W / NATIVE_W, OUT_H / NATIVE_H
            pts = []
            for i, (x, y) in enumerate((v1, v2, v3)):
                z = zs[i] if zs else 0.0
                pts.append([round(x * sx, 1), round(y * sy, 1), round(z, 5)])
            if all(0 <= p[0] <= OUT_W and 0 <= p[1] <= OUT_H for p in pts):
                stats["inb"] += 1

            if name in ZBUF_OPS:
                kind = "d" if cur["_zupd"] else "s"
            else:
                kind = "o"
            tri = {"p": pts, "c": cur["_group"],
                   "z": 1 if name in ZBUF_OPS else 0, "k": kind}
            # b=1 marks a triangle textured out of the bank our build never
            # reads (A617: 0x00206000-0x00234000; A618: zero bindings anywhere
            # in the run). These are the surfaces that are missing on our side.
            ti = cur.get("_timg")
            if ti is not None and BANK_LO <= ti < BANK_HI:
                tri["b"] = 1
            cur["tris"].append(tri)
            cur["built"] += 1
            cur["_dirty"] = True
            continue

        if name in ("Tex-Rect", "Tex-Rect (Flip)", "Fill-Rect"):
            x1 = ((w0 >> 44) & 0xFFF) / 4.0
            y1 = ((w0 >> 32) & 0xFFF) / 4.0
            x0 = ((w0 >> 12) & 0xFFF) / 4.0
            y0 = (w0 & 0xFFF) / 4.0
            cur["rects"].append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                 "kind": "fill" if name == "Fill-Rect" else "tex"})
            stats["rects"] += 1
            cur["_dirty"] = True
            continue

    for f in frames:
        f["matrices"] = f["_group"] + 1
        f["note"] = (f"Reference: ares frame {f['task']} — RDP command stream, "
                     f"post-transform and post-cull. {f['built']} triangles, "
                     f"{len(f['rects'])} rect commands, "
                     f"{f['_group'] + 1} constructed draw groups. "
                     "Nothing is 'dropped behind the eye' here: culling already "
                     "happened upstream, invisibly to this stream.")
        nb = sum(1 for x in f["tris"] if x.get("b"))
        f["note"] += (f" {nb} of them are textured from 0x206000-0x234000, the bank "
                      "our build never binds anywhere in the run (A617/A618).")
        for k in ("_group", "_dirty", "_scissor", "_zupd", "_timg"):
            f.pop(k, None)

    if verbose:
        report(frames, stats)
    return frames, stats


def report(frames, s):
    print(f"[rdp2step] {len(frames)} frame(s), {s['tris']} triangle commands, "
          f"{s['rects']} rect commands")
    # A control with nothing to test does NOT pass. Reporting PASS on a zero
    # denominator is how a broken instrument reads as a working one (T65/T100):
    # the pre-patch dump has 11,848 triangle rows and not one reconstructable
    # vertex, and the first version of this function called that PASS.
    built = s["tris"] - s["short"]
    tot = s["c1_pass"] + s["c1_fail"]
    print(f"  C1 y cross-check vs ares's own decoder : "
          f"{s['c1_pass']}/{tot} match"
          f"   {'PASS' if tot and s['c1_fail'] == 0 else 'FAIL (nothing to test)' if not tot else 'FAIL'}")
    # THRESHOLD, not equality -- and the number is justified, not picked: the
    # wrong premise (XL on the major edge) holds on only 15% of this same data,
    # so 70% separates a correct mapping from a wrong one by a wide margin.
    n2 = s["c2_n"]
    agree = n2 - s["c2_bad"]
    med = 0.0
    if s["c2_err"]:
        e = sorted(s["c2_err"])
        med = e[len(e) // 2]
    print(f"  C2 top-vertex identity XH==XM          : "
          f"{agree}/{n2} within 1px ({100.0*agree/n2:.1f}%) on non-degenerate "
          f"triangles; median miss {med:.2f}px, worst {s['c2_max']:.2f}px"
          f"   {'PASS' if n2 and agree * 10 >= n2 * 7 else 'FAIL (nothing to test)' if not n2 else 'FAIL'}")
    print(f"     ({s['degen']} degenerate triangles excluded: YM==YH or YM==YL "
          f"leaves XM unconstrained, so the identity does not apply)")
    if built:
        print(f"  C3 vertices inside the canvas          : "
              f"{100.0 * s['inb'] / built:.1f}% (reported, not asserted)")
    if s["short"]:
        print(f"  !! {s['short']} triangle rows had fewer than 4 words -- is this "
              f"a dump from BEFORE the capture was widened?")
    for f in frames:
        print(f"  frame {f['task']:<6} {len(f['tris']):>5} tris  "
              f"{len(f['rects']):>4} rects  {f['matrices']:>4} groups")


def pack_tri(yl, ym, yh, xl, dxldy, xh, dxhdy, xm, dxmdy, op=0x08):
    """Build synthetic edge words, for --self-check only."""
    def q(v):
        return (int(round(v * 65536)) & 0xFFFFFFFF)
    w0 = (op << 56) | ((int(yl * 4) & 0x3FFF) << 32) \
        | ((int(ym * 4) & 0x3FFF) << 16) | (int(yh * 4) & 0x3FFF)
    return [w0,
            (q(xl) << 32) | q(dxldy),
            (q(xh) << 32) | q(dxhdy),
            (q(xm) << 32) | q(dxmdy)]


def self_check():
    """C4. A synthetic triangle whose answer is known, then the same words
    permuted -- which must FAIL. Verified to fail, not merely to pass (T65)."""
    ok = True
    # v1=(100,50) v2=(40,130) v3=(180,200)
    yh, ym, yl = 50.0, 130.0, 200.0
    xh, dxhdy = 100.0, (180 - 100) / (yl - yh)
    xm, dxmdy = 100.0, (40 - 100) / (ym - yh)
    xl, dxldy = 40.0, (180 - 40) / (yl - ym)
    words = pack_tri(yl, ym, yh, xl, dxldy, xh, dxhdy, xm, dxmdy)

    v1, v2, v3, ys, ch, _ = parse_tri(words, NATIVE_W, NATIVE_H)
    want = [(100.0, 50.0), (40.0, 130.0), (180.0, 200.0)]
    got = [v1, v2, v3]
    good = all(abs(g[0] - w[0]) < 0.01 and abs(g[1] - w[1]) < 0.01
               for g, w in zip(got, want))
    print(f"  C4a synthetic triangle reconstructs      : "
          f"{'PASS' if good else 'FAIL'}  {[(round(x,2), round(y,2)) for x,y in got]}")
    ok &= good

    idt = abs(ch["xh"] - ch["xm"]) < 0.01
    print(f"  C4b top-vertex identity holds on it      : "
          f"{'PASS' if idt else 'FAIL'}  XH={ch['xh']:.2f} XM={ch['xm']:.2f}")
    ok &= idt

    # THE PART THAT MATTERS: permute words 1-3 and require the checks to break.
    bad = [words[0], words[2], words[3], words[1]]
    b1, b2, b3, _, bch, _ = parse_tri(bad, NATIVE_W, NATIVE_H)
    broke_v = any(abs(g[0] - w[0]) > 0.01 or abs(g[1] - w[1]) > 0.01
                  for g, w in zip([b1, b2, b3], want))
    broke_i = abs(bch["xh"] - bch["xm"]) > 1.0
    print(f"  C4c permuted words BREAK the vertices    : "
          f"{'PASS (it failed, as it must)' if broke_v else 'FAIL — control is blind'}")
    print(f"  C4d permuted words BREAK the identity    : "
          f"{'PASS (it failed, as it must)' if broke_i else 'FAIL — control is blind'}"
          f"  XH={bch['xh']:.2f} XM={bch['xm']:.2f}")
    ok &= broke_v and broke_i

    # A y-triple that disagrees must be counted as a failure, not rounded away.
    y_ok = ch["yraw"] == (int(yl * 4), int(ym * 4), int(yh * 4))
    print(f"  C4e y raw triple matches what was packed : "
          f"{'PASS' if y_ok else 'FAIL'}  {ch['yraw']}")
    ok &= y_ok

    print(f"\n  self-check {'PASSED' if ok else 'FAILED'} (5 controls)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("dump", nargs="?")
    ap.add_argument("-o", "--out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--frames", type=int, default=0,
                    help="keep only the first N frames (0 = all)")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__)
        return 0
    if a.self_check:
        return self_check()
    if not a.dump:
        print(__doc__)
        return 2

    frames, stats = convert(a.dump)
    if a.frames and len(frames) > a.frames:
        print(f"  [--frames {a.frames}] keeping {a.frames} of {len(frames)} frames; "
              f"the rest are DROPPED, not merged.")
        frames = frames[:a.frames]

    if a.dry_run or not a.out:
        blob = json.dumps({"frames": frames}, separators=(",", ":"))
        print(f"\n[dry run] would write {len(blob)} bytes of JSON "
              f"({len(blob)//1024} KB) for {len(frames)} frame(s).")
        if frames and frames[0]["tris"]:
            print(f"[dry run] first triangle: {frames[0]['tris'][0]}")
            print(f"[dry run] first rect    : "
                  f"{frames[0]['rects'][0] if frames[0]['rects'] else 'none'}")
        print("[dry run] nothing written. Re-run with -o <file> to emit.")
        return 0

    Path(a.out).write_text(json.dumps({"frames": frames}, separators=(",", ":")))
    print(f"\n[rdp2step] wrote {a.out} "
          f"({Path(a.out).stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
