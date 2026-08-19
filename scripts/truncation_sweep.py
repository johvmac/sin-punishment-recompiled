#!/usr/bin/env python3
"""A96: sweep every generated function for A85's truncation signature (BC-2).

THE SIGNATURE
-------------
A function whose generated C **allocates a stack frame but never returns** --
`addiu $sp, $sp, -N` at entry, and no `jr $ra` anywhere -- while control
demonstrably does return to its caller at runtime. That means the C is CUT OFF
before the epilogue, because `symbols/sinpunishment.syms.toml` declared the
function shorter than it really is.

This class has produced two confirmed, user-verified defects:

  * L1 -- `ovlfile02_func_800E4F34` declared 0x14, really 0x8C. The START crash.
  * L7 -- `ovlfile20_func_800E5634` declared 0x54, really 0x118. The attract
    freeze: it leaked 0x18 of stack per frame until the stack walked onto the
    dispatch table.

WHY THE SIGNATURE ALONE OVER-FIRES
----------------------------------
Some functions genuinely never return -- thread entry loops, and the BC-3
call-free spin-waits. So "allocates and never returns" is necessary but not
sufficient. A85's evidence had a second half: the symbol also leaves an
**unclaimed gap** (`vram + size < next vram`), i.e. there are bytes after the
declared end that no symbol owns -- which is where the missing epilogue went.

Functions matching BOTH are the real lead list. Reported separately so the
over-firing is visible rather than hidden.

DETECTION USES THE MIPS COMMENTS, NOT THE C. N64Recomp emits the original
instruction verbatim above each translated line, so `jr $ra` and
`addiu $sp, $sp, -N` are read from disassembly rather than inferred from
`ctx->r29 = ADD32(...)`, which would also match ordinary pointer arithmetic.

READ-ONLY. Prints; changes nothing. Fixing means correcting the declared size
in symbols/sinpunishment.syms.toml and re-running -- never editing
RecompiledFuncs/ (see the playbook).

    scripts/truncation_sweep.py           # summary + top candidates
    scripts/truncation_sweep.py --all     # every BOTH-signature function
    scripts/truncation_sweep.py --signature-only   # ignore the gap half
"""
import re
import sys
from collections import Counter
from pathlib import Path

KNOWN = {"--all", "--signature-only", "--help", "-h"}
_unknown = [a for a in sys.argv[1:] if a.startswith("-") and a not in KNOWN]
if "--help" in sys.argv or "-h" in sys.argv:
    print(__doc__)
    sys.exit(0)
if _unknown:
    print(f"[sweep] unknown argument(s): {' '.join(_unknown)}", file=sys.stderr)
    print(f"[sweep] known: {', '.join(sorted(KNOWN))}", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
FUNCS = ROOT / "RecompiledFuncs"
SYMS = ROOT / "symbols" / "sinpunishment.syms.toml"

FUNC_START = re.compile(r"^RECOMP_FUNC void (\w+)\(")
ALLOC = re.compile(r"//\s*0x[0-9A-Fa-f]+:\s*addiu\s+\$sp,\s*\$sp,\s*-0x[0-9A-Fa-f]+")
RESTORE = re.compile(r"//\s*0x[0-9A-Fa-f]+:\s*addiu\s+\$sp,\s*\$sp,\s*0x[0-9A-Fa-f]+")
JR_RA = re.compile(r"//\s*0x[0-9A-Fa-f]+:\s*jr\s+\$ra\b")

SECTION = re.compile(r'^\s*name\s*=\s*"([^"]+)"')
SYM = re.compile(
    r'\{\s*name\s*=\s*"([^"]+)"\s*,\s*vram\s*=\s*(0x[0-9A-Fa-f]+)\s*,'
    r'\s*size\s*=\s*(0x[0-9A-Fa-f]+)\s*\}'
)
ALIGN = 16


def scan_generated():
    """name -> (allocates, has_restore, has_jr_ra)."""
    out = {}
    for path in sorted(FUNCS.glob("*.c")):
        name = None
        alloc = restore = jr = False
        for line in path.read_text(errors="replace").splitlines():
            m = FUNC_START.match(line)
            if m:
                if name:
                    out[name] = (alloc, restore, jr)
                name = m.group(1)
                alloc = restore = jr = False
                continue
            if name is None:
                continue
            if ALLOC.search(line):
                alloc = True
            elif RESTORE.search(line):
                restore = True
            if JR_RA.search(line):
                jr = True
        if name:
            out[name] = (alloc, restore, jr)
    return out


def symbol_gaps():
    """name -> (section, vram, size, gap). Only genuine gaps, not alignment."""
    sections, cur, funcs = [], "?", []
    for line in SYMS.read_text().splitlines():
        m = SECTION.match(line)
        if m:
            if funcs:
                sections.append((cur, funcs))
            cur, funcs = m.group(1), []
            continue
        m = SYM.search(line)
        if m:
            funcs.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
    if funcs:
        sections.append((cur, funcs))

    gaps = {}
    for sec, fs in sections:
        fs = sorted(fs, key=lambda t: t[1])
        for (nm, vram, size), (_, nxt, _) in zip(fs, fs[1:]):
            end = vram + size
            gap = nxt - end
            if gap <= 0:
                continue
            if gap < ALIGN and end % ALIGN != 0 and (end + gap) % ALIGN == 0:
                continue          # alignment padding
            gaps[nm] = (sec, vram, size, gap)
    return gaps


def main():
    if not FUNCS.is_dir():
        print(f"[sweep] no {FUNCS} — run scripts/recompile.sh first", file=sys.stderr)
        return 1

    gen = scan_generated()
    gaps = symbol_gaps()

    signature = {n for n, (a, r, j) in gen.items() if a and not j and not r}
    # Generated names carry a segment prefix (boot_/main_/ovlfileNN_); the syms
    # table uses the same names, so they join directly.
    both = sorted(signature & set(gaps), key=lambda n: -gaps[n][3])
    sig_no_gap = signature - set(gaps)

    print(f"generated functions scanned : {len(gen)}")
    print(f"allocates but never returns : {len(signature)}   <- signature alone; OVER-FIRES")
    print(f"  ... and no unclaimed gap  : {len(sig_no_gap)}   <- thread loops / BC-3 spin-waits")
    print(f"  ... AND an unclaimed gap  : {len(both)}   <- THE LEAD LIST (A96)")

    if not both:
        print("\nnothing matches both halves of the signature.")
        return 0

    print("\nby section:")
    for sec, n in Counter(gaps[n][0] for n in both).most_common():
        tot = sum(gaps[x][3] for x in both if gaps[x][0] == sec)
        print(f"  {sec:<14} {n:4d} functions   {tot:7d} unclaimed bytes")

    show = both if "--all" in sys.argv else both[:25]
    print(f"\ntop {len(show)} by gap size — the gap is where the missing epilogue went:")
    print(f"  {'gap':>7}  {'section':<12} {'symbol':<34} {'vram':>10} {'declared':>9}")
    for n in show:
        sec, vram, size, gap = gaps[n]
        print(f"  {gap:>#7x}  {sec:<12} {n:<34} {vram:>#10x} {size:>#9x}")

    print("\nTo fix one: correct `size` in symbols/sinpunishment.syms.toml so the")
    print("function ends at its real `jr $ra`, re-run scripts/recompile.sh and")
    print("scripts/build.sh, then re-run this sweep — the entry should disappear.")
    print("Confirm the true end from the ROM (splat endlabel / scripts/decomp.sh),")
    print("NEVER from the gap alone: the gap says bytes are unclaimed, not that")
    print("they belong to this function.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
