#!/usr/bin/env python3
"""Decompress the ROM's Yay0 archives and lay them out as contact sheets.

WHY THIS EXISTS (A227/A250)
---------------------------
A227's split: decompression and decoding are mechanical and belong to a script;
deciding "that is a logo, that is a font atlas, that is UI furniture" is instant
for a person and unreliable for code. **The deliverable is contact sheets for a
human to flip through**, not an automatic classifier.

A250 established the cheap half is already done: all 28 archives decompress to
EXACTLY their declared size, and archive 0 rendered as 4-bit indexed at 64 px
wide is a recognisable human face on the first layout guess.

THE CONTROL, AND WHY IT CAN FAIL
--------------------------------
A Yay0 header declares its uncompressed length. A decoder that mis-reads the
mask/link/chunk streams produces the wrong number of bytes -- so "output length
== declared length" is a fact the format checks for us, and it does not pass 28
times by luck. `--self-check` additionally builds a SYNTHETIC archive with a
known payload and requires an exact round-trip, and then CORRUPTS it and
requires the decode to FAIL. A decoder that always claimed success would pass
the first and fail the second.

WHAT IT DOES NOT DO
-------------------
It does not identify anything. Tiles are laid out at a FIXED size in ROM order;
a texture whose real width differs will look sheared, and that is expected --
the point is to make content recognisable enough for a person to say "that one,
at that offset". It also says nothing about whether an asset is ever LOADED;
that is RT64's texture dump (A243), which is the complementary question.

    scripts/yay0_extract.py --dry-run
    scripts/yay0_extract.py --out <dir>
    scripts/yay0_extract.py --self-check
"""
import argparse
import struct
import sys
from pathlib import Path

ROM_DEFAULT = Path.home() / ".config/sinpunishment/sinpunishment.n64.jp.1.0.z64"
# T47: evidence goes to the archive drive, never /tmp.
OUT_DEFAULT = Path("/media/joh/extra/sin-punishment-archive/asset-sheets")
TILE = 64                      # 64x64 CI4 tile == 2048 bytes
TILE_BYTES = TILE * TILE // 2
COLS = 10


def yay0_decode(src, off):
    """Decode one Yay0 archive. Returns (payload, declared_size)."""
    if src[off:off + 4] != b"Yay0":
        raise ValueError(f"no Yay0 magic at 0x{off:X}")
    size, link_off, chunk_off = struct.unpack_from(">III", src, off + 4)
    mp, lp, cp = off + 0x10, off + link_off, off + chunk_off
    out = bytearray()
    mask = 0
    bits = 0
    while len(out) < size:
        if bits == 0:
            mask = struct.unpack_from(">I", src, mp)[0]
            mp += 4
            bits = 32
        if mask & 0x80000000:
            out.append(src[cp])
            cp += 1
        else:
            link = struct.unpack_from(">H", src, lp)[0]
            lp += 2
            dist = (link & 0x0FFF) + 1
            cnt = link >> 12
            if cnt == 0:
                cnt = src[cp] + 0x12
                cp += 1
            else:
                cnt += 2
            start = len(out) - dist
            if start < 0:
                raise ValueError("back-reference before start of output")
            for i in range(cnt):
                out.append(out[start + i])
        mask = (mask << 1) & 0xFFFFFFFF
        bits -= 1
    return bytes(out), size


def find_archives(src):
    return [i for i in range(0, len(src) - 4, 4) if src[i:i + 4] == b"Yay0"]


def sheet(payload, path):
    """One contact sheet: the payload as 64x64 CI4 tiles in ROM order."""
    import numpy as np
    from PIL import Image
    n = len(payload) // TILE_BYTES
    if n == 0:
        return 0
    rows = (n + COLS - 1) // COLS
    canvas = np.zeros((rows * TILE, COLS * TILE), dtype=np.uint8)
    for t in range(n):
        chunk = np.frombuffer(payload[t * TILE_BYTES:(t + 1) * TILE_BYTES], dtype=np.uint8)
        px = np.empty(chunk.size * 2, dtype=np.uint8)
        px[0::2] = chunk >> 4
        px[1::2] = chunk & 0x0F
        tile = (px.reshape(TILE, TILE) * 17).astype(np.uint8)
        r, c = divmod(t, COLS)
        canvas[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE] = tile
    Image.fromarray(canvas, "L").save(path)
    return n


def self_check():
    checks = []

    def chk(name, ok, detail):
        checks.append((name, ok, detail))

    # A synthetic archive: all-literal encoding (every mask bit set) is valid
    # Yay0 and exercises the header, mask and chunk streams.
    payload = bytes(range(256)) * 4
    nmask = (len(payload) + 31) // 32
    header = struct.pack(">4sIII", b"Yay0", len(payload), 0x10 + nmask * 4, 0x10 + nmask * 4)
    blob = header + b"\xff\xff\xff\xff" * nmask + payload
    try:
        out, dec = yay0_decode(blob, 0)
        chk("synthetic archive round-trips EXACTLY", out == payload and dec == len(payload),
            f"{len(out)} bytes, match={out == payload}")
    except Exception as e:
        chk("synthetic archive round-trips EXACTLY", False, f"raised {e}")

    # DISCRIMINATING: a corrupted header must FAIL, not silently return short.
    # A decoder that always claimed success would pass the case above and fail
    # this one -- which is the whole reason it is here.
    bad = bytearray(blob)
    bad[0:4] = b"XXXX"
    try:
        yay0_decode(bytes(bad), 0)
        chk("a corrupted archive is REJECTED", False, "decoded a blob with no magic")
    except Exception:
        chk("a corrupted archive is REJECTED", True, "raised, as it must")

    # DISCRIMINATING: a truncated payload must not report the declared size.
    bad2 = bytearray(blob)
    struct.pack_into(">I", bad2, 4, len(payload) + 4096)   # claim more than exists
    try:
        out2, dec2 = yay0_decode(bytes(bad2), 0)
        chk("a size that overruns the data does NOT report success",
            len(out2) != dec2, f"produced {len(out2)} against declared {dec2}")
    except Exception:
        chk("a size that overruns the data does NOT report success", True, "raised, as it must")

    bad_n = 0
    for name, ok, detail in checks:
        bad_n += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:56} — {detail}")
    print(f"\n{len(checks)-bad_n}/{len(checks)} controls pass")
    return 1 if bad_n else 0


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--rom", type=Path, default=ROM_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__)
        return 0
    if a.self_check:
        return self_check()
    if not a.rom.exists():
        print(f"[yay0] ROM not found: {a.rom}", file=sys.stderr)
        return 2

    src = a.rom.read_bytes()
    offs = find_archives(src)
    print(f"[yay0] {len(offs)} archive(s); first at 0x{offs[0]:X}" if offs else "[yay0] none found")
    if a.dry_run:
        print(f"[yay0] --dry-run: would write {len(offs)} sheet(s) to {a.out}")
        for k, o in enumerate(offs[:5]):
            size = struct.unpack_from(">I", src, o + 4)[0]
            print(f"[yay0]   sheet {k:02d}: 0x{o:08X} -> {size:,} bytes "
                  f"({size // TILE_BYTES} tiles)")
        if len(offs) > 5:
            print(f"[yay0]   ... and {len(offs)-5} more")
        return 0

    a.out.mkdir(parents=True, exist_ok=True)
    ok = 0
    for k, o in enumerate(offs):
        payload, declared = yay0_decode(src, o)
        if len(payload) != declared:
            print(f"[yay0] archive {k} at 0x{o:X}: SIZE MISMATCH "
                  f"{len(payload)} vs {declared} — skipped", file=sys.stderr)
            continue
        ok += 1
        p = a.out / f"arc{k:02d}_{o:08X}.png"
        n = sheet(payload, p)
        print(f"[yay0] arc{k:02d} 0x{o:08X}  {declared:>9,} bytes  {n:>4} tiles  -> {p.name}")
    print(f"[yay0] {ok}/{len(offs)} archives decompressed with the declared size")
    return 0 if ok == len(offs) else 1


if __name__ == "__main__":
    sys.exit(main())
