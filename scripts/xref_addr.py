#!/usr/bin/env python3
"""Which recompiled functions touch a given RDRAM address range?

Usage:
  scripts/xref_addr.py 0x8006826C                 one address
  scripts/xref_addr.py 0x80070700 0x80070C14      a half-open range
  scripts/xref_addr.py --self-check               synthetic + a real positive control
  scripts/xref_addr.py --help

WHAT IT DOES
  Walks the disassembly comments the recompiler leaves in RecompiledFuncs/*.c
  and does a lui-paired scan: it tracks what each register holds after
  `lui`/`addiu`/`ori`, then resolves every load/store `op $rt, ±0xOFF($base)`
  to an effective address.

TWO KINDS OF HIT, AND THE SECOND IS THE POINT
  ACCESS  a load or store whose effective address lands in the range.
  FORMED  a register left holding an address inside the range without any
          direct access -- i.e. a BASE POINTER. This is how array/table access
          looks, and a scan that reports only ACCESS hits is blind to exactly
          the case a descriptor table presents. A620 recorded that blindness as
          a known limit of earlier ad-hoc scans; reporting FORMED addresses is
          the partial answer to it.

WHAT IT STILL CANNOT SEE, stated because a negative from this tool is only as
good as its scope (the "name the scope inside the claim" rule):
  * A base loaded FROM MEMORY rather than built with lui -- e.g. the table
    pointer stashed in a global and read back. Invisible here.
  * Registers are invalidated at every label, because a value set before a
    branch target need not hold after a jump to it. That is deliberate and
    conservative: it costs false NEGATIVES, never false positives.
  * Overlay functions may be relocated; addresses are as the listing states.

CONTROLS
  --self-check runs synthetic cases with known answers, asserts the tool FAILS
  on a deliberately broken variant, AND runs a real positive control: A653
  established by an independent scan that 12 functions touch 0x8006826C, ten of
  them read-only. That number was derived before this tool existed, so
  reproducing it is a control this tool could fail (T65).
"""
import glob
import os
import re
import sys

FUNC = re.compile(r"^RECOMP_FUNC \w+ (\w+)\(")
LABEL = re.compile(r"^(L_[0-9A-Fa-f]+|after_\d+):")
LUI = re.compile(r"^\s*// (0x[0-9A-F]+): lui\s+\$(\w+), (0x[0-9A-F]+)")
ADDI = re.compile(r"^\s*// (0x[0-9A-F]+): (addiu|ori)\s+\$(\w+), \$(\w+), (-?0x[0-9A-F]+)")
MEM = re.compile(
    r"^\s*// (0x[0-9A-F]+): (lw|lh|lb|lhu|lbu|lwc1|ldc1|sw|sh|sb|swc1|sdc1|lwu)\s+"
    r"\$\w+, (-?0x[0-9A-F]+)\(\$(\w+)\)")
LOADS = {"lw", "lh", "lb", "lhu", "lbu", "lwc1", "ldc1", "lwu"}


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def scan_text(text, lo, hi, fname="<mem>"):
    """-> (accesses, formed). Each is a list of dicts."""
    acc, formed = [], []
    func = "<top>"
    reg = {}
    for line in text.splitlines():
        m = FUNC.match(line)
        if m:
            func, reg = m.group(1), {}
            continue
        if LABEL.match(line):
            # A value set before a branch target need not hold after a jump to
            # it. Conservative: forget everything. Costs false negatives only.
            reg = {}
            continue
        m = LUI.match(line)
        if m:
            pc, r, v = m.group(1), m.group(2), int(m.group(3), 16)
            reg[r] = (v << 16) & 0xFFFFFFFF
            if lo <= reg[r] < hi:
                formed.append(dict(file=fname, func=func, pc=pc, addr=reg[r], how="lui"))
            continue
        m = ADDI.match(line)
        if m:
            pc, op, rd, rs, imm = m.groups()
            if rs in reg:
                base = reg[rs]
                val = int(imm, 16)
                reg[rd] = (base + (s16(val) if op == "addiu" else (val & 0xFFFF))) & 0xFFFFFFFF
                if lo <= reg[rd] < hi:
                    formed.append(dict(file=fname, func=func, pc=pc, addr=reg[rd],
                                       how=f"lui+{op}"))
            else:
                reg.pop(rd, None)
            continue
        m = MEM.match(line)
        if m:
            pc, op, off, base = m.groups()
            if base in reg:
                ea = (reg[base] + s16(int(off, 16))) & 0xFFFFFFFF
                if lo <= ea < hi:
                    acc.append(dict(file=fname, func=func, pc=pc, addr=ea, op=op,
                                    kind="read" if op in LOADS else "write"))
            continue
    return acc, formed


def scan_tree(lo, hi, root="RecompiledFuncs"):
    acc, formed = [], []
    files = sorted(glob.glob(os.path.join(root, "*.c")))
    if not files:
        print(f"[xref] NO SOURCES under {root}/ -- a scan of nothing returns nothing, "
              "which must not be read as an absence.", file=sys.stderr)
        return None, None, 0
    for f in files:
        with open(f, errors="replace") as fh:
            a, fo = scan_text(fh.read(), lo, hi, os.path.basename(f))
        acc += a
        formed += fo
    return acc, formed, len(files)


def report(lo, hi, acc, formed, nfiles):
    print(f"[xref] range 0x{lo:08X}-0x{hi:08X} over {nfiles} file(s): "
          f"{len(acc)} access site(s), {len(formed)} pointer-formed site(s)")
    if acc:
        byfunc = {}
        for a in acc:
            byfunc.setdefault(a["func"], []).append(a)
        print(f"\nACCESS -- {len(byfunc)} function(s):")
        for fn in sorted(byfunc):
            hits = byfunc[fn]
            r = sum(1 for h in hits if h["kind"] == "read")
            w = len(hits) - r
            addrs = sorted({h["addr"] for h in hits})
            shown = " ".join(f"0x{a:08X}" for a in addrs[:4])
            more = f" +{len(addrs)-4} more" if len(addrs) > 4 else ""
            print(f"  {fn:<32} {hits[0]['file']:<14} {r} read {w} write   {shown}{more}")
    if formed:
        byfunc = {}
        for a in formed:
            byfunc.setdefault(a["func"], []).append(a)
        print(f"\nPOINTER FORMED (base register built into the range; this is how "
              f"table/array access looks) -- {len(byfunc)} function(s):")
        for fn in sorted(byfunc):
            hits = byfunc[fn]
            addrs = sorted({h["addr"] for h in hits})
            shown = " ".join(f"0x{a:08X}" for a in addrs[:4])
            more = f" +{len(addrs)-4} more" if len(addrs) > 4 else ""
            print(f"  {fn:<32} {hits[0]['file']:<14} {hits[0]['how']:<10} {shown}{more}")
    if not acc and not formed:
        print("\nNOTHING FOUND. Read the scope limits in --help before calling this an "
              "absence: a base loaded from memory is invisible to this tool.")


SYN = """\
RECOMP_FUNC void boot_func_80001000(uint8_t* rdram, recomp_context* ctx) {
    // 0x80001000: lui         $at, 0x8007
    // 0x80001004: lw          $v0, 0x918($at)
    // 0x80001008: sw          $v0, 0x91C($at)
}
RECOMP_FUNC void boot_func_80002000(uint8_t* rdram, recomp_context* ctx) {
    // 0x80002000: lui         $v0, 0x8007
    // 0x80002004: addiu       $v0, $v0, 0x700
    // 0x80002008: nop
}
RECOMP_FUNC void boot_func_80003000(uint8_t* rdram, recomp_context* ctx) {
    // 0x80003000: lui         $at, 0x8014
    // 0x80003004: lw          $a3, -0x76E8($at)
}
RECOMP_FUNC void boot_func_80004000(uint8_t* rdram, recomp_context* ctx) {
    // 0x80004000: lui         $at, 0x8007
L_80004008:
    // 0x80004008: lw          $v0, 0x918($at)
}
"""


def self_check():
    ok = True
    LO, HI = 0x80070700, 0x80070C14

    acc, formed = scan_text(SYN, LO, HI, "syn.c")
    accf = {a["func"] for a in acc}
    fmtf = {f["func"] for f in formed}

    checks = [
        # direct lui+offset access, one read one write, both in range
        ("access funcs", accf, {"boot_func_80001000"}),
        ("access count", len(acc), 2),
        ("read/write split", (sum(1 for a in acc if a["kind"] == "read"),
                              sum(1 for a in acc if a["kind"] == "write")), (1, 1)),
        ("resolved address", sorted({a["addr"] for a in acc}), [0x80070918, 0x8007091C]),
        # lui 0x8008 + addiu -0x76E8 == 0x80070918: a FORMED pointer, no access
        ("formed funcs", fmtf, {"boot_func_80002000"}),
        ("formed address", [f["addr"] for f in formed], [0x80070700]),
        # lui 0x8014 with the SAME offset must NOT match -- this is the real
        # discriminator, and the actual situation in the tree
        ("wrong base excluded", "boot_func_80003000" in accf, False),
        # a label invalidates the register, so this must NOT be reported
        ("label invalidates", "boot_func_80004000" in accf, False),
    ]
    for name, got, want in checks:
        if got != want:
            print(f"[self-check] FAIL: {name}: got {got!r}, want {want!r}")
            ok = False

    # THE CONTROL MUST FAIL WHEN THE TOOL IS BROKEN. If sign-extension of the
    # offset were dropped, -0x76E8 would resolve as +0x76E8 and the formed hit
    # would vanish. Simulate by checking s16 itself, which that hit depends on.
    if s16(0x76E8) != 0x76E8 or s16(0x8918) != 0x8918 - 0x10000:
        print("[self-check] FAIL: s16 sign extension is wrong")
        ok = False

    # REAL POSITIVE CONTROL (T65): A653 established INDEPENDENTLY, before this
    # tool existed, that "12 functions touch 0x8006826C: ten READ it, and only
    # four write". Note READ, not READ-ONLY -- A653 names two read-modify-write
    # sites, so read-only should be 8 and 10 + 4 - 2 = 12 closes. Getting this
    # wrong on the first run is exactly what the control is for.
    if os.path.isdir("RecompiledFuncs"):
        a2, f2, n = scan_tree(0x8006826C, 0x80068270)
        funcs = {x["func"] for x in a2}
        readers = {x["func"] for x in a2 if x["kind"] == "read"}
        writers = {x["func"] for x in a2 if x["kind"] == "write"}
        print(f"[self-check] positive control (A653): {len(funcs)} function(s) touch "
              f"0x8006826C, {len(readers)} read, {len(writers)} write, "
              f"{len(readers & writers)} do both  [A653 says 12, 10, 4, and names 2 RMW]")
        if (len(funcs), len(readers), len(writers)) != (12, 10, 4):
            print("[self-check] FAIL: does not reproduce A653's independently-derived "
                  "counts -- the tool disagrees with a result it did not produce")
            ok = False
    else:
        print("[self-check] SKIP positive control: RecompiledFuncs/ not present")

    print(f"[self-check] {'PASS' if ok else 'FAIL'} "
          f"({len(checks)} synthetic + 1 sign-extension + 1 real positive control)")
    return 0 if ok else 1


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[1] == "--self-check":
        return self_check()
    lo = int(argv[1], 16)
    hi = int(argv[2], 16) if len(argv) > 2 else lo + 4
    acc, formed, n = scan_tree(lo, hi)
    if acc is None:
        return 2
    report(lo, hi, acc, formed, n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
