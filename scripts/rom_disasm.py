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
    scripts/rom_disasm.py --section ovlfile19 0x800F9424 +0x40
    scripts/rom_disasm.py --self-check          # positive control, see below

OVERLAYS: `--section` IS NOT OPTIONAL WHERE IT APPLIES (A198)
------------------------------------------------------------
Overlays share vram, so fifteen sections can contain one address. This used to
NOTE that and disassemble the first anyway; the note went to stderr, a
`2>&1 | tail -25` dropped it, and the wrong overlay's bytes were read as the
answer and written up as a finding (A196).

So an ambiguous address is now a REFUSAL with EMPTY STDOUT, not a warning --
there is nothing left to misread. Main-segment addresses match exactly one
section and are unaffected; this fires only on overlay addresses, where
proceeding without naming the overlay means disassembling a different program.

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

    # --section CONTROLS (A197). This flag's output is now load-bearing evidence,
    # so it clears T71's gates rather than being trusted because it looks right.
    #
    # THE CONTROL THAT DISCRIMINATES is the first one: it asserts the flag
    # actually CHANGES THE BYTES. A --section that parsed cleanly and then
    # quietly disassembled the default overlay anyway would produce exactly the
    # confident-wrong output this whole tool exists to prevent (T49), and a
    # control that merely checked "it exits 0" would pass on it.
    me = [sys.executable, __file__]
    ambiguous, unambiguous = "0x800F9424", "0x800339C8"
    words = lambda s: [m.group(1) for m in re.finditer(r":\t([0-9a-f]{8}) ", s)]
    run = lambda a: subprocess.run(me + a, capture_output=True, text=True)
    checks = []

    # 1. THE DISCRIMINATING ONE: --section must actually SELECT. Two explicit
    #    overlays over the same address must disassemble to DIFFERENT bytes. A
    #    --section that parsed cleanly and then used the default anyway would
    #    produce exactly the confident-wrong output this tool exists to prevent
    #    (T49), and a control that only checked the exit code would pass on it.
    a = run(["--section", "ovlfile04", ambiguous, "+0x20"]).stdout
    b = run(["--section", "ovlfile19", ambiguous, "+0x20"]).stdout
    checks.append((bool(words(a)) and words(a) != words(b),
                   "--section SELECTS (ovlfile04 and ovlfile19 disassemble differently)",
                   f"ovlfile04={len(words(a))} words, ovlfile19={len(words(b))}, same bytes?"))

    # 2. AMBIGUITY REFUSES, AND STDOUT IS EMPTY (A198). Empty stdout is the half
    #    that matters: a refusal that still printed a disassembly could be piped
    #    into `tail` and read as an answer, which is the original failure.
    r = run([ambiguous, "+0x20"])
    checks.append((r.returncode == 2 and not r.stdout.strip(),
                   "an ambiguous address REFUSES with EMPTY stdout",
                   f"rc={r.returncode} (want 2), stdout={len(r.stdout)} bytes (want 0)"))

    # 3. THE REFUSAL IS SCOPED -- without this, control 2 passes on a tool that
    #    refuses everything and is therefore useless.
    r = run([unambiguous, "+0x20"])
    checks.append((r.returncode == 0 and bool(words(r.stdout)),
                   "an UNAMBIGUOUS address still works (the refusal is scoped)",
                   f"rc={r.returncode} (want 0), {len(words(r.stdout))} words (want >0)"))

    # 4. An unknown section name is a typo, not a licence to guess.
    r = run(["--section", "nosuchoverlay", ambiguous, "+0x20"])
    checks.append((r.returncode == 2 and "REFUSING" in r.stderr,
                   "--section REFUSES an unknown name",
                   f"rc={r.returncode}, want 2"))

    for got, label, detail in checks:
        print(f"{'ok  ' if got else 'FAIL'}  {label}" + ("" if got else f" -- {detail}"))

    extra_bad = sum(1 for got, _, _ in checks if not got)
    total = len(theirs) + len(checks)
    print(f"\n{total - len(bad) - extra_bad}/{total} controls pass "
          f"({len(theirs)} words vs splat's committed asm + {len(checks)} --section controls)")
    return 1 if (bad or extra_bad) else 0


def main():
    args = [a for a in sys.argv[1:]]
    if "--help" in args or "-h" in args or not args:
        print(__doc__)
        return 0
    if "--self-check" in args:
        return self_check()

    # --section <name>: PICK THE OVERLAY EXPLICITLY (A197).
    #
    # 15 sections contain an address like 0x800F9448 -- that is what an overlay
    # IS. This tool already NAMES all of them on stderr and says it is showing
    # the first, which is honest. But "showing the first" is a coin toss when
    # you are asking about a specific overlay's code, and on 2026-08-20 the
    # first was .ovlfile04 while the question was about ovlfile19. Without a
    # way to say which, the only options were to trust the wrong bytes or to
    # derive a delta by hand -- and deriving it by hand is T49.
    want = None
    if "--section" in args:
        i = args.index("--section")
        if i + 1 >= len(args):
            print("REFUSING: --section needs a name, e.g. --section ovlfile19",
                  file=sys.stderr)
            return 2
        want = args[i + 1].lstrip(".")
        del args[i:i + 2]

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
    if want is not None:
        picked = [h for h in hits if h[0].lstrip(".") == want]
        if not picked:
            print(f"REFUSING: no section named '{want}' contains 0x{start:08X}. "
                  f"Sections that do: {', '.join(h[0] for h in hits)}", file=sys.stderr)
            return 2
        print(f"# section CHOSEN EXPLICITLY: {picked[0][0]} (--section {want})",
              file=sys.stderr)
        return disasm(start, end, picked[0])

    if len(hits) > 1:
        # REFUSE, DO NOT WARN (A198). This used to print a NOTE naming all the
        # candidate overlays and then disassemble the first one anyway. The NOTE
        # was correct, complete, and went to stderr -- where `2>&1 | tail -25`
        # dropped it, and 25 lines of confident wrong disassembly were read as
        # though they were the answer (A196).
        #
        # A warning only works if it is READ. A refusal works even when it is
        # not, because there is no output to misread: stdout stays EMPTY.
        # That is the same move regenerate.sh made -- it cannot be forgotten
        # because there is nothing to remember.
        #
        # SCOPE, measured: main-segment addresses match exactly ONE section, so
        # this never fires on them. It fires only on overlay addresses, where
        # proceeding without knowing the overlay is not a shortcut -- it is
        # reading a different program's bytes.
        print(f"REFUSING: {len(hits)} sections contain 0x{start:08X}. Overlays share "
              f"vram, so there is no 'the' answer -- picking one silently is how A196 "
              f"read ovlfile04's bytes while asking about ovlfile19.", file=sys.stderr)
        print(f"Re-run with --section <name>. Candidates:", file=sys.stderr)
        for h in hits:
            print(f"  --section {h[0].lstrip('.'):<12} rom=0x{h[1]:08X}", file=sys.stderr)
        return 2
    return disasm(start, end, hits[0])


if __name__ == "__main__":
    sys.exit(main())
