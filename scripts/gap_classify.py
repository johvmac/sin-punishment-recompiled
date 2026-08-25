#!/usr/bin/env python3
"""T11 step 2: classify each unclaimed gap by DECODING THE ROM, not by asking splat.

WHY THIS EXISTS AND WHY IT IS NOT A THIRD STRUCTURAL RULE
---------------------------------------------------------
A261 built two structural rules for this and killed both:

  * RULE 1, "scan forward for the first `jr $ra`" -- borrows a NEIGHBOUR's
    return, and flagged 172 of 251 candidates. Not credible.
  * RULE 2, "does it return inside its declared size" -- assumes every function
    ends in `jr $ra`, and `ovlfile07_func_800E4780` does not.

Both passed all four of A261's controls, because **all four controls were the
same shape** -- a truncation, flagged or not. Four controls that vary only in
the answer are one control.

So this does the thing that DID work. A292 settled one boundary by reading the
overlay's own ROM bytes directly and counting exits, with no splat anywhere in
the chain, and that is the only splat-independent answer T11 has. This
generalises A292's read to every candidate.

THE CLASSIFICATION IS THREE-WAY, WHICH IS THE POINT
---------------------------------------------------
A gap's bytes are read and placed in one of these, tested IN THIS ORDER:

  PADDING       every word in the gap is zero. Not a truncation. Nothing owed.
  SEPARATE      the gap OPENS with a stack prologue (`addiu sp,sp,-N`), so it
                is an unlabelled FUNCTION sitting in the gap -- the previous
                symbol is not truncated, the next one is missing.
  CONTINUATION  the gap contains `jr $ra` and the declared body contains NONE.
                The epilogue is in the gap: the symbol is TRUNCATED. This is
                L1's shape (0x14 declared, 0x8C real), L7's (0x54 vs 0x118),
                and A292's proven ovlfile07 case.
  RETURNS-BOTH  both halves return. Ambiguous by construction -- most likely a
                leaf function with no frame. NOT reported as a truncation.
  UNCLEAR       anything else. Reported, never guessed at.

SEPARATE is tested BEFORE CONTINUATION on purpose: a truncated function's gap
opens mid-body, never on a prologue, so a prologue at offset 0 is the stronger
signal and must win. PADDING first because zeros satisfy nothing else.

The three non-PADDING classes fail in DIFFERENT DIRECTIONS, which is what
A261's controls lacked: over-flagging shows up as SEPARATE bodies called
CONTINUATION, under-flagging as CONTINUATION called RETURNS-BOTH.

THE DELTA IS NOT DERIVED HERE
-----------------------------
vram->ROM comes from `rom_disasm.sections()`, imported, which reads the
`[[section]]` blocks. Deriving it by hand is T49. The symbol list comes from
`symbol_gaps.parse_sections()`, imported for the same reason -- a second parser
is a copy that goes stale (T199/T200).

COSTING, NOT FIXING. Read-only: it prints a classification and changes nothing.
Acting on a CONTINUATION means editing the declared size in
symbols/sinpunishment.syms.toml and re-running the recompile -- never editing
RecompiledFuncs/.

    scripts/gap_classify.py                  # top 20 outside ovlfile12
    scripts/gap_classify.py --all            # every candidate
    scripts/gap_classify.py --limit 40
    scripts/gap_classify.py --include-ovl12  # ovlfile12 too (T11 says do not)
    scripts/gap_classify.py --self-check     # controls, incl. two that over-flag
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rom_disasm import ROM, OBJDUMP, sections as rom_sections   # noqa: E402
from symbol_gaps import parse_sections, find_gaps               # noqa: E402

KNOWN = {"--all", "--help", "-h", "--self-check", "--limit", "--include-ovl12"}

# --- the whole instruction decoder. Deliberately tiny; cross-checked against
#     objdump by control C6, because a hand-rolled decoder is exactly the kind
#     of tool T60/T62/T63 shipped confident wrong answers from.
JR_RA = 0x03E00008                    # jr $ra, encoded exactly


def is_jr_ra(w):
    return w == JR_RA


def is_j(w):
    """j target -- opcode 0b000010. A TAIL CALL is how a function can end
    without `jr $ra`, so a gap holding several functions can show few returns
    and many of these. A292 counted J and JAL for exactly this reason; leaving
    them out would make a multi-function gap look like one long function."""
    return (w >> 26) == 0x02


def is_jal(w):
    return (w >> 26) == 0x03


def is_prologue(w):
    """addiu $sp, $sp, -N -- opcode 0b001001, rs=rt=29, negative immediate."""
    return (w & 0xFFFF0000) == 0x27BD0000 and (w & 0x8000) != 0


def words(vram, end, sect):
    """Big-endian words of [vram, end) read out of the ROM at sect's delta."""
    _, rom, svram, _ = sect
    off = rom + (vram - svram)
    n = end - vram
    with open(ROM, "rb") as fh:
        fh.seek(off)
        blob = fh.read(n)
    if len(blob) < n:
        return None
    return [int.from_bytes(blob[i:i + 4], "big") for i in range(0, len(blob), 4)]


def section_named(name):
    want = name.lstrip(".")
    for s in rom_sections():
        if s[0].lstrip(".") == want:
            return s
    return None


def classify(decl, gap):
    """decl/gap are word lists. -> (verdict, why)."""
    if not gap:
        return "UNCLEAR", "empty gap"
    if all(w == 0 for w in gap):
        return "PADDING", f"{len(gap)} zero words"

    lead = 0
    while lead < len(gap) and gap[lead] == 0:
        lead += 1
    if lead < len(gap) and is_prologue(gap[lead]):
        return "SEPARATE", f"prologue at gap+0x{lead * 4:X}"

    gap_ret = sum(1 for w in gap if is_jr_ra(w))
    decl_ret = sum(1 for w in decl if is_jr_ra(w))
    gap_j = sum(1 for w in gap if is_j(w))
    gap_jal = sum(1 for w in gap if is_jal(w))
    exits = f"J={gap_j} JAL={gap_jal} JR$ra={gap_ret}"

    if gap_ret and not decl_ret:
        last = max(i for i, w in enumerate(gap) if is_jr_ra(w))
        # A292's shape: the sole return sits one delay slot short of the next
        # symbol, i.e. ONE function runs to the true boundary. Called out
        # because it is much stronger than "a return is in there somewhere",
        # which is all A261's rejected rule 1 ever established.
        tail = "" if last * 4 != len(gap) * 4 - 8 else "  [A292 shape: sole exit ends exactly at the next symbol]"
        return "CONTINUATION", (f"declared body has no return; gap {exits}, "
                                f"last return at gap+0x{last * 4:X}{tail}")
    if gap_ret and decl_ret:
        return "RETURNS-BOTH", f"{decl_ret} return(s) declared, gap {exits}"
    if gap_j or gap_jal:
        return "UNCLEAR", f"no return either side but gap {exits} ({len(gap)} words)"
    return "NO-CODE", (f"no return, no jump either side ({len(gap)} words) "
                       f"-- reads as DATA, not truncated code")


def run(argv):
    if not ROM.exists():
        print(f"[gapc] no ROM at {ROM}", file=sys.stderr)
        return 1

    _, candidates = find_gaps(parse_sections())
    if "--include-ovl12" not in argv:
        candidates = [c for c in candidates if c[1].lstrip(".") != "ovlfile12"]

    limit = 20
    if "--all" in argv:
        limit = len(candidates)
    for i, a in enumerate(argv):
        if a == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])

    show = sorted(candidates, reverse=True)[:limit]
    print(f"[gapc] {len(candidates)} candidate(s) outside ovlfile12; "
          f"classifying the largest {len(show)}")
    if len(show) < len(candidates):
        print(f"[gapc] {len(candidates) - len(show)} NOT classified "
              f"(--all, or --limit N, to widen). They are not cleared, only unread.")
    print()

    tally = Counter()
    rows, skipped = [], []
    for gap, sec, name, vram, size, nxt in show:
        sect = section_named(sec)
        if sect is None:
            skipped.append((name, sec, "no [[section]] block"))
            continue
        decl = words(vram, vram + size, sect)
        gapw = words(vram + size, nxt, sect)
        if decl is None or gapw is None:
            skipped.append((name, sec, "read past end of ROM"))
            continue
        verdict, why = classify(decl, gapw)
        tally[verdict] += 1
        rows.append((verdict, gap, sec, name, vram, size, why))

    order = ["CONTINUATION", "SEPARATE", "RETURNS-BOTH", "UNCLEAR", "NO-CODE", "PADDING"]
    for want in order:
        hits = [r for r in rows if r[0] == want]
        if not hits:
            continue
        print(f"=== {want}  ({len(hits)}) ===")
        for verdict, gap, sec, name, vram, size, why in hits:
            print(f"  {name:<32} {sec:<11} vram={vram:#x} "
                  f"size={size:#x} gap={gap:#x}")
            print(f"      {why}")
        print()

    if skipped:
        print(f"=== NOT READ  ({len(skipped)}) ===")
        for name, sec, why in skipped:
            print(f"  {name:<32} {sec:<11} {why}")
        print()

    n = sum(tally.values())
    print(f"[gapc] {n} classified: " +
          ", ".join(f"{k}={tally[k]}" for k in order if tally[k]))
    if n:
        print(f"[gapc] TRUNCATION HIT RATE: {tally['CONTINUATION']}/{n} = "
              f"{100 * tally['CONTINUATION'] / n:.0f}%  "
              f"(A261's rejected rule 1 scored 69%, which was not credible)")
    print("[gapc] SCOPE: this reads bytes, so it says where returns and prologues")
    print("[gapc] are. It does NOT prove a CONTINUATION's exact extent -- that is")
    print("[gapc] a per-function read like A292's before any size is edited.")
    return 0


# ----------------------------------------------------------------- controls
def objdump_region(vram, end, sect):
    """objdump's own text for a region -- the independent decoder for C6."""
    _, rom, svram, _ = sect
    delta = svram - rom
    cmd = [OBJDUMP, "-D", "-b", "binary", "-m", "mips:4300", "-EB",
           f"--adjust-vma=0x{delta:X}",
           f"--start-address=0x{vram:X}", f"--stop-address=0x{end:X}", str(ROM)]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def self_check():
    """Controls that vary the FAILURE MODE, not just the answer (A261).

    C1/C2/C3 must FLAG (under-flagging fails them).
    C4/C5 must NOT flag (over-flagging fails them) -- these are the mode A261
    found missing, and they are why rules 1 and 2 would fail here.
    C6 checks the hand-rolled decoder against objdump.
    """
    ok, fail = 0, 0

    def check(label, got, want):
        nonlocal ok, fail
        good = got == want
        ok, fail = ok + good, fail + (not good)
        print(f"  [{'PASS' if good else 'FAIL'}] {label}: got {got}, want {want}")

    print("--- MUST FLAG: recorded truncations, at their OLD declared sizes ---")
    for label, sec, vram, old_size, real_end in [
        # L1, the START crash: 0x14 declared, 0x8C real.
        ("C1 L1 ovlfile02_func_800E4F34 @0x14", "ovlfile02", 0x800E4F34, 0x14, 0x800E4F34 + 0x8C),
        # L7, the attract freeze: 0x54 declared, 0x118 real.
        ("C2 L7 ovlfile20_func_800E5634 @0x54", "ovlfile20", 0x800E5634, 0x54, 0x800E5634 + 0x118),
        # A292's static proof, and the case that killed A261's rule 2.
        ("C3 A292 ovlfile07_func_800E4780 @0x40", "ovlfile07", 0x800E4780, 0x40, 0x800E4780 + 0x518),
    ]:
        s = section_named(sec)
        v, _ = classify(words(vram, vram + old_size, s),
                        words(vram + old_size, real_end, s))
        check(label, v, "CONTINUATION")

    print("--- MUST NOT FLAG: the over-flagging mode A261's controls lacked ---")
    # C4: a real all-zero gap, found rather than asserted.
    _, cands = find_gaps(parse_sections())
    zero_case = None
    for gap, sec, name, vram, size, nxt in sorted(cands, reverse=True):
        s = section_named(sec)
        if s is None:
            continue
        w = words(vram + size, nxt, s)
        if w and all(x == 0 for x in w):
            zero_case = (name, sec, vram, size, nxt, s)
            break
    if zero_case:
        name, sec, vram, size, nxt, s = zero_case
        v, _ = classify(words(vram, vram + size, s), words(vram + size, nxt, s))
        check(f"C4 all-zero gap after {name}", v, "PADDING")
    else:
        print("  [FAIL] C4: no all-zero gap found to test with")
        fail += 1

    # C5: feed a CORRECTLY-declared function's real successor in as the "gap",
    # where the PREDECESSOR NEVER RETURNS. That last condition is the whole
    # control and it was missing on the first attempt: with a predecessor that
    # does return, "scan forward for a return" declines to flag anyway, so the
    # ordering bug hides and the control passes for the wrong reason. T44
    # measured 138 functions that legitimately never return (thread loops,
    # BC-3 spin-waits), so this pairing is common, not contrived.
    #
    # Correct order  -> SEPARATE   (the successor opens with its own prologue)
    # A261's rule 1  -> CONTINUATION, a false truncation. Caught.
    #
    # The FIXTURE SEARCH uses literal encodings, not the module's predicates:
    # a search built on the thing under test reports "no fixture found" when
    # the predicate breaks, which hides a wrong verdict behind a missing case.
    def raw_ret(w):
        return w == 0x03E00008

    def raw_pro(w):
        return (w & 0xFFFF0000) == 0x27BD0000 and (w & 0x8000) != 0

    secs = dict((n.lstrip("."), f) for n, f in parse_sections())
    c5 = None
    for secname, funcs in secs.items():
        s = section_named(secname)
        if s is None:
            continue
        funcs = sorted(funcs, key=lambda t: t[1])
        for (n1, v1, s1), (n2, v2, s2) in zip(funcs, funcs[1:]):
            if v1 + s1 != v2 or s1 == 0 or s2 == 0:
                continue                      # want an exact fit, no real gap
            w1, w2 = words(v1, v1 + s1, s), words(v2, v2 + s2, s)
            if not w1 or not w2:
                continue
            if any(raw_ret(x) for x in w1):
                continue                      # predecessor MUST NOT return
            if raw_pro(w2[0]) and any(raw_ret(x) for x in w2):
                c5 = (n1, n2, w1, w2)
                break
        if c5:
            break
    if c5:
        n1, n2, w1, w2 = c5
        v, _ = classify(w1, w2)
        check(f"C5 {n2} as {n1}'s gap ({n1} never returns)", v, "SEPARATE")
    else:
        print("  [FAIL] C5: no non-returning/returning adjacent pair to test with")
        fail += 1

    print("--- decoder agreement ---")
    # C6: my two predicates against objdump's mnemonics over a real region.
    s = section_named("ovlfile07")
    lo, hi = 0x800E4780, 0x800E4780 + 0x518
    txt = objdump_region(lo, hi, s)
    od_ret = len(re.findall(r"\bjr\s+ra\b", txt))
    od_pro = len(re.findall(r"\baddiu\s+sp,sp,-", txt))
    w = words(lo, hi, s)
    check("C6 jr $ra count vs objdump", sum(1 for x in w if is_jr_ra(x)), od_ret)
    check("C6 prologue count vs objdump", sum(1 for x in w if is_prologue(x)), od_pro)

    print(f"\n[gapc] self-check {ok}/{ok + fail}")
    if od_ret == 0 and od_pro == 0:
        print("[gapc] WARNING: objdump matched nothing -- C6 compared 0 with 0 and")
        print("[gapc] cannot discriminate. Treat C6 as NOT RUN.", file=sys.stderr)
        return 1
    return 0 if fail == 0 else 1


def main():
    argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    vals = {argv[i + 1] for i, a in enumerate(argv) if a == "--limit" and i + 1 < len(argv)}
    unknown = [a for a in argv if a.startswith("-") and a not in KNOWN and a not in vals]
    if unknown:
        print(f"[gapc] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print(f"[gapc] known: {', '.join(sorted(KNOWN))}", file=sys.stderr)
        return 2
    if "--self-check" in argv:
        return self_check()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
