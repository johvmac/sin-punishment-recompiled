#!/usr/bin/env python3
"""Yaz0 decompression, for reading the SIBLING PORT's ROM (T197).

WHY THIS EXISTS (A642, A650)
----------------------------
T197 wants to borrow function names from the Majora's Mask decomp. A642
verified our MM ROM is the right revision -- its md5 matches zeldaret/mm's
published `checksum-compressed.md5` exactly -- and then found the blocker:
**2,033 Yaz0 blocks starting at 0x956780, which is 70.8% of the image.** Skeleton
matching needs function BYTES, and you cannot read bytes out of a compressed ROM
by address.

A650 then fired A642's own falsifier -- "a decompressor already present in a
submodule or reachable from the toolchain" -- across four independent channels
(repo+submodule source, the toolchain directory, importable Python modules,
PATH) and found NOTHING. So the borrow arm is closed and this is the write arm.

**Our own game uses Yay0, not Yaz0** (28 blocks vs 0), which is why
`scripts/yay0_extract.py` exists and does not help here. Two different formats
with confusingly similar names: Yay0 stores its three streams separately, Yaz0
interleaves flag bytes with the data.

THE FORMAT
----------
Header, 16 bytes:  'Yaz0' | uncompressed_size (u32 BE) | 8 reserved bytes.
Then groups. Each group is one FLAG BYTE followed by 8 chunks, MSB first:
  bit set   -> one literal byte, copied straight out.
  bit clear -> a back-reference, 2 or 3 bytes:
                 b0 b1 : dist = ((b0 & 0x0F) << 8) | b1 ; src = out_len-dist-1
                         n = b0 >> 4
                 n == 0 -> read a third byte: count = b2 + 0x12
                 n != 0 -> count = n + 2
               The copy is BYTE AT A TIME because it may overlap itself (that
               is how runs are encoded); a slice copy silently gives the wrong
               answer on exactly the cases the format exists to compress.
A group's 8 chunks may run past the end -- stop as soon as out_len == size.

THE THREE GATES (T71)
---------------------
1. DRY RUN: `--dry-run <rom>` reports what it would decode and exits, touching
   nothing.
2. A CONTROL THAT CAN FAIL: `--self-check <rom>` decodes real blocks out of the
   ROM and asserts each output length equals the length its own header declares
   -- then DELIBERATELY CORRUPTS a block and asserts the decoder REJECTS it.
   Both arms, because a control that only passes is not a control (T65).
3. Written up in the playbook in the same checkpoint.

USAGE
    scripts/yaz0_extract.py --dry-run <rom>
    scripts/yaz0_extract.py --self-check <rom>
    scripts/yaz0_extract.py --list <rom>              # every Yaz0 block found
    scripts/yaz0_extract.py <rom> <offset> [outfile]  # decode one block
"""
import sys


class Yaz0Error(Exception):
    pass


def decompress(data, off=0):
    """Decode the Yaz0 block at `off`. Raises Yaz0Error rather than guessing."""
    if data[off:off + 4] != b"Yaz0":
        raise Yaz0Error(f"no Yaz0 magic at 0x{off:X}")
    size = int.from_bytes(data[off + 4:off + 8], "big")
    if size == 0 or size > 64 * 1024 * 1024:
        raise Yaz0Error(f"declared size {size} at 0x{off:X} is not plausible")
    src = off + 16
    out = bytearray()
    while len(out) < size:
        if src >= len(data):
            raise Yaz0Error(f"ran off the end of the ROM at 0x{off:X} "
                            f"({len(out)}/{size} bytes decoded)")
        flags = data[src]
        src += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                if src >= len(data):
                    raise Yaz0Error("truncated literal")
                out.append(data[src])
                src += 1
            else:
                if src + 1 >= len(data):
                    raise Yaz0Error("truncated back-reference")
                b0, b1 = data[src], data[src + 1]
                src += 2
                dist = ((b0 & 0x0F) << 8) | b1
                start = len(out) - dist - 1
                n = b0 >> 4
                if n == 0:
                    if src >= len(data):
                        raise Yaz0Error("truncated long back-reference")
                    n = data[src] + 0x12
                    src += 1
                else:
                    n += 2
                if start < 0:
                    raise Yaz0Error(f"back-reference before the start of output "
                                    f"(dist={dist}, out={len(out)}) at 0x{off:X}")
                # byte at a time: the copy may overlap itself
                for k in range(n):
                    if len(out) >= size:
                        break
                    out.append(out[start + k])
    return bytes(out), src - off


def find_blocks(data):
    """Offsets of every Yaz0 magic in the image."""
    hits, i = [], data.find(b"Yaz0")
    while i != -1:
        hits.append(i)
        i = data.find(b"Yaz0", i + 4)
    return hits


def self_check(path):
    data = open(path, "rb").read()
    blocks = find_blocks(data)
    checks, fails = [], 0

    def chk(label, ok, detail=""):
        nonlocal fails
        checks.append((label, ok, detail))
        fails += not ok

    chk("the ROM contains Yaz0 blocks at all", len(blocks) > 0,
        "no Yaz0 magic found -- wrong ROM for this tool")
    if not blocks:
        for l, o, d in checks:
            print(f"{'ok  ' if o else 'FAIL'}  {l}" + ("" if o else f" -- {d}"))
        print(f"\n{len(checks) - fails}/{len(checks)} controls pass")
        return 1

    # POSITIVE ARM: real blocks must decode to exactly their declared length.
    sample = blocks[:5] + blocks[len(blocks) // 2: len(blocks) // 2 + 5] + blocks[-5:]
    good = 0
    for off in sample:
        want = int.from_bytes(data[off + 4:off + 8], "big")
        try:
            out, _ = decompress(data, off)
            if len(out) == want:
                good += 1
            else:
                chk(f"block 0x{off:X} decodes to its declared length", False,
                    f"got {len(out)}, header says {want}")
        except Yaz0Error as e:
            chk(f"block 0x{off:X} decodes", False, str(e))
    chk(f"{good}/{len(sample)} sampled blocks decode to their DECLARED length",
        good == len(sample), f"only {good} of {len(sample)}")

    # NEGATIVE ARM: a corrupted block must be REJECTED, not silently decoded.
    # Corrupt the declared size to something impossible; the decoder must raise.
    off = blocks[0]
    bad = bytearray(data)
    bad[off + 4:off + 8] = (0xFFFFFFFF).to_bytes(4, "big")
    try:
        decompress(bytes(bad), off)
        chk("a corrupted SIZE field is REJECTED", False, "it decoded anyway")
    except Yaz0Error:
        chk("a corrupted SIZE field is REJECTED", True)

    # Second negative: truncate the image mid-block.
    off = blocks[0]
    want = int.from_bytes(data[off + 4:off + 8], "big")
    truncated = data[:off + 24]
    try:
        decompress(truncated, off)
        chk("a TRUNCATED block is REJECTED", False, "it returned a short result silently")
    except Yaz0Error:
        chk("a TRUNCATED block is REJECTED", True)

    # Third negative: the magic check itself must discriminate.
    try:
        decompress(data, off + 1)
        chk("a WRONG OFFSET is REJECTED", False, "decoded from a non-magic offset")
    except Yaz0Error:
        chk("a WRONG OFFSET is REJECTED", True)

    for l, o, d in checks:
        print(f"{'ok  ' if o else 'FAIL'}  {l}" + ("" if o else f" -- {d}"))
    print(f"\n{len(checks) - fails}/{len(checks)} controls pass")
    return 1 if fails else 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--self-check":
        if len(argv) < 3:
            print("[yaz0] --self-check needs a ROM path", file=sys.stderr)
            return 2
        return self_check(argv[2])
    if argv[1] == "--dry-run":
        if len(argv) < 3:
            print("[yaz0] --dry-run needs a ROM path", file=sys.stderr)
            return 2
        data = open(argv[2], "rb").read()
        blocks = find_blocks(data)
        print("=== DRY RUN — nothing decoded, nothing written ===")
        print(f" rom      : {argv[2]} ({len(data):,} bytes)")
        print(f" Yaz0     : {len(blocks)} block(s)")
        if blocks:
            first, last = blocks[0], blocks[-1]
            tot = sum(int.from_bytes(data[b + 4:b + 8], "big") for b in blocks)
            print(f" first    : 0x{first:X}   last: 0x{last:X}")
            print(f" declared : {tot:,} bytes uncompressed in total")
            print(f" would    : decode on request; --self-check verifies 15 blocks"
                  f" and 3 deliberate failures first")
        return 0
    if argv[1] == "--list":
        data = open(argv[2], "rb").read()
        for b in find_blocks(data):
            print(f"0x{b:08X}  declared {int.from_bytes(data[b+4:b+8],'big'):,}")
        return 0
    data = open(argv[1], "rb").read()
    off = int(argv[2], 0)
    out, used = decompress(data, off)
    if len(argv) > 3:
        open(argv[3], "wb").write(out)
        print(f"[yaz0] 0x{off:X}: {used:,} compressed -> {len(out):,} bytes -> {argv[3]}")
    else:
        sys.stdout.buffer.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
