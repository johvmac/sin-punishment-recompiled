#!/usr/bin/env python3
"""Disassemble the ROM at a VRAM address, resolving the segment delta for you.

WHY THIS EXISTS RATHER THAN A BARE objdump
------------------------------------------
The vram->ROM delta is per SEGMENT, and deriving it by hand is how T49 happened:
one anchor, misread by 0x3C, produced a clean and entirely wrong dispatch table
that survived until an unrelated prior measurement contradicted it. Nothing in
the output looked wrong -- three plausible function pointers, then a structure
change, exactly what a real table looks like.

So the delta is not an argument here. It is looked up from the `[[section]]`
blocks in `symbols/sinpunishment.syms.toml`, which are the same numbers the
recompiler uses, and the section that actually contains the address is the one
that gets used. If no section contains it, this REFUSES rather than guessing --
a wrong delta is worse than no disassembly.

    scripts/rom_disasm.py 0x800339C8 0x800339F4
    scripts/rom_disasm.py 0x800E4780 +0x40      # length form
    scripts/rom_disasm.py --self-check          # positive control, see below

SELF-CHECK
----------
`--self-check` disassembles a region whose splat output is committed and
compares them instruction-for-instruction. That is a positive control on the
toolchain, on the invocation and on the delta lookup at once (T61). Run it if
you doubt any output from this script.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYMS = ROOT / "symbols" / "sinpunishment.syms.toml"
ROM = Path("/home/joh/Documents/sin_and_punishment/splat-project/baserom.z64")
OBJDUMP = "mips-linux-gnu-objdump"


def sections():
    """Yield (name, rom, vram, size) for every [[section]] in the syms toml."""
    out, cur = [], {}
    for line in SYMS.read_text().split("\n"):
        if line.startswith("[[section]]"):
            cur = {}
            continue
        m = re.match(r'\s*name\s*=\s*"([^"]+)"', line)
        if m and "vram" not in cur:
            cur["name"] = m.group(1)
        for key in ("rom", "vram", "size"):
            m = re.match(rf"\s*{key}\s*=\s*(0x[0-9A-Fa-f]+)", line)
            if m:
                cur[key] = int(m.group(1), 16)
        if {"name", "rom", "vram", "size"} <= set(cur):
            out.append((cur["name"], cur["rom"], cur["vram"], cur["size"]))
            cur = {}
    return out


def find_section(vram):
    """The section CONTAINING vram. Overlays share vram, so report all matches."""
    hits = [s for s in sections() if s[2] <= vram < s[2] + s[3]]
    return hits


def disasm(start, end, sect):
    name, rom, vram, size = sect
    delta = vram - rom
    print(f"# section {name}: rom=0x{rom:08X} vram=0x{vram:08X} size=0x{size:X}")
    print(f"# vram->rom delta = 0x{delta:08X}  (looked up, not derived by hand -- T49)")
    cmd = [OBJDUMP, "-D", "-b", "binary", "-m", "mips:4300", "-EB",
           f"--adjust-vma=0x{delta:X}",
           f"--start-address=0x{start:X}", f"--stop-address=0x{end:X}", str(ROM)]
    print("# " + " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    if p.returncode:
        sys.stderr.write(p.stderr)
    return p.returncode


def self_check():
    """Compare against splat's committed asm for a known region."""
    start, end = 0x800339C8, 0x800339F4
    hits = find_section(start)
    if not hits:
        print("FAIL: no section contains the self-check address", file=sys.stderr)
        return 1
    name, rom, vram, size = hits[0]
    delta = vram - rom
    cmd = [OBJDUMP, "-D", "-b", "binary", "-m", "mips:4300", "-EB",
           f"--adjust-vma=0x{delta:X}",
           f"--start-address=0x{start:X}", f"--stop-address=0x{end:X}", str(ROM)]
    got = subprocess.run(cmd, capture_output=True, text=True).stdout
    mine = {}
    for line in got.split("\n"):
        m = re.match(r"\s*([0-9a-f]{8,16}):\s+([0-9a-f]{8})\s", line)
        if m:
            mine[int(m.group(1), 16) & 0xFFFFFFFF] = m.group(2)

    splat = Path("/home/joh/Documents/sin_and_punishment/splat-project/asm/1050.s")
    theirs = {}
    for line in splat.read_text().split("\n"):
        m = re.match(r"\s*/\* \w+ ([0-9A-F]{8}) ([0-9A-F]{8}) \*/", line)
        if m:
            a = int(m.group(1), 16)
            if start <= a < end:
                theirs[a] = m.group(2).lower()

    if not mine or not theirs:
        print(f"FAIL: nothing to compare (objdump {len(mine)}, splat {len(theirs)})",
              file=sys.stderr)
        return 1
    bad = [a for a in sorted(theirs) if mine.get(a) != theirs[a]]
    for a in sorted(theirs):
        flag = "ok  " if mine.get(a) == theirs[a] else "FAIL"
        print(f"{flag}  0x{a:08X}  objdump={mine.get(a, '--------')}  splat={theirs[a]}")
    print(f"\n{len(theirs) - len(bad)}/{len(theirs)} words match splat's committed asm")
    return 1 if bad else 0


def main():
    args = [a for a in sys.argv[1:]]
    if "--help" in args or "-h" in args or not args:
        print(__doc__)
        return 0
    if "--self-check" in args:
        return self_check()

    start = int(args[0], 16)
    if len(args) > 1:
        end = (start + int(args[1][1:], 16)) if args[1].startswith("+") else int(args[1], 16)
    else:
        end = start + 0x40

    hits = find_section(start)
    if not hits:
        print(f"REFUSING: no [[section]] in {SYMS.name} contains 0x{start:08X}, so the "
              f"vram->ROM delta is unknown. Guessing one is exactly the T49 failure -- "
              f"a wrong delta produces plausible, confident nonsense.", file=sys.stderr)
        return 2
    if len(hits) > 1:
        print(f"# NOTE: {len(hits)} sections contain this address (overlays share vram -- "
              f"A85/G3.1). Showing the first; the others are:", file=sys.stderr)
        for h in hits[1:]:
            print(f"#   {h[0]} rom=0x{h[1]:08X}", file=sys.stderr)
    return disasm(start, end, hits[0])


if __name__ == "__main__":
    sys.exit(main())
