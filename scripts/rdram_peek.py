#!/usr/bin/env python3
"""Read game memory out of an RDRAM snapshot, without re-running the game.

An RDRAM snapshot (written by `SNP_RDRAM_DUMP=<path> scripts/gdb_fault.sh`) is
8MB of game memory plus the register file at the moment of the fault. It exists
because a real core file of this process is 11.8 GB -- librecomp reserves 4GB
and commits 512MB -- while every address this project has ever examined lives in
the first few MB of RDRAM (T63/T64).

    scripts/rdram_peek.py <snap> 0x8013C278              # one word
    scripts/rdram_peek.py <snap> 0x802E1680 20           # 20 words
    scripts/rdram_peek.py <snap> --regs                  # the register file
    scripts/rdram_peek.py <snap> --stride 0x14 0x802E1680 8
                                                         # 8 records of 0x14

Addresses are KSEG0 (0x8xxxxxxx), the same form the ledger uses.

WHY IT IS WORTH KEEPING SNAPSHOTS
Re-running to the A99 fault costs ~158s and yields one fixed set of values.
A snapshot answers new questions about the SAME crash for free -- which is
exactly what cost a re-run on 2026-08-19 when the first pass used the release
binary and `ctx` would not resolve (A122).
"""
import struct
import sys
from pathlib import Path

BASE = 0x80000000
REG_NAMES = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
             "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
             "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
             "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def load(path):
    data = Path(path).read_bytes()
    ctx = Path(str(path) + ".ctx")
    regs, rdram_base = None, None
    if ctx.exists():
        raw = ctx.read_bytes()
        rdram_base = struct.unpack_from("<Q", raw, 0)[0]
        regs = [struct.unpack_from("<Q", raw, 8 + 8 * i)[0] for i in range(32)]
    return data, regs, rdram_base


def word(data, vram):
    off = vram - BASE
    if not (0 <= off + 4 <= len(data)):
        raise IndexError(f"0x{vram:08X} is outside the {len(data)//1024//1024}MB snapshot")
    # LITTLE-endian. The runtime stores RDRAM in HOST word order -- MEM_W is
    # `*(int32_t*)(rdram + off)` on a little-endian host -- which is the same
    # fact that makes byte access need the `^3` swap (I7).
    #
    # The first version of this reader used ">I" and produced clean, plausible,
    # byte-reversed values: 0x8013C278 read as 0x00000002 instead of 0x02000000,
    # and A110's nodes as 34162E80 instead of 802E1634. Caught on the FIRST use
    # because the snapshot was checked against a known value rather than eyeballed
    # -- exactly the I7 failure, which also printed convincing reversed bytes.
    return struct.unpack_from("<I", data, off)[0]


def main():
    a = sys.argv[1:]
    if not a or "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    snap = a[0]
    rest = a[1:]
    data, regs, rdram_base = load(snap)
    print(f"# snapshot {snap}: {len(data)/1e6:.1f} MB of RDRAM"
          + (f", rdram base was 0x{rdram_base:x}" if rdram_base else ", no .ctx alongside"))

    if "--regs" in rest:
        if not regs:
            print("no .ctx file alongside the snapshot", file=sys.stderr)
            return 1
        for i in range(0, 32, 4):
            print("  " + "  ".join(
                f"${REG_NAMES[i+j]:<4}=0x{regs[i+j] & 0xFFFFFFFF:08X}" for j in range(4)))
        return 0

    stride = None
    if "--stride" in rest:
        k = rest.index("--stride")
        stride = int(rest[k + 1], 16)
        rest = rest[:k] + rest[k + 2:]

    start = int(rest[0], 16)
    count = int(rest[1], 0) if len(rest) > 1 else 1

    try:
        if stride:
            for i in range(count):
                a0 = start + i * stride
                ws = [word(data, a0 + o) for o in range(0, stride, 4)]
                print(f"  [{i:>2}] 0x{a0:08X}  " + " ".join(f"{w:08X}" for w in ws))
        else:
            for i in range(count):
                a0 = start + i * 4
                w = word(data, a0)
                note = "  <- plausible KSEG0 pointer" if 0x80000000 <= w < 0x80800000 else ""
                print(f"  0x{a0:08X}  = 0x{w:08X}{note}")
    except IndexError as e:
        print(f"REFUSING: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
