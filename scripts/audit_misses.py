#!/usr/bin/env python3
"""Which entries went wrong, and did the L1 audit catch them?

WHY THIS EXISTS (T171)
----------------------
`audit.py` has no `--self-check`. It is the level of the review ladder whose
whole job is catching what the level below missed, and there is no control on
it at all — so three consecutive quiet runs cannot be distinguished from three
runs of a checker that quietly stopped working.

The obvious fix is to write it a self-check. **That is the trap.** A control
written in the same sitting, from the same reading of the same source, by the
same reader, inherits whatever that reader misunderstood — which is exactly why
T153's control was VOID and why the agent brief's rule 5 says to seed a control
from GROUND TRUTH and never from one's own prior source reading.

So this does not invent failure modes. **The ledger already contains 75 natural
experiments**: entries that were later withdrawn, corrected, refuted or
scope-flagged. Each one is a fault that really happened, on a real day, in a
real window. The question for each is only: did an audit flag it?

WHAT THIS PRODUCES, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------
It sorts every known-bad entry into:

  CAUGHT       an audit flagged it, AND the flag names the thing it was wrong
               about — a genuine catch.
  CAUGHT-OTHER an audit flagged it for a DIFFERENT reason. Not a catch: the
               checker was right by accident, and counting it as a catch would
               overstate what the tool can do.
  MISSED       no audit ever flagged it.

**It does NOT decide whether a MISSED entry was CATCHABLE.** That is a judgement
about whether the fault was visible at the time or only became visible when a
later measurement contradicted it — and it is precisely the judgement the author
of both the mistake and the checker must not make alone. That is the sitting.

USAGE
    scripts/audit_misses.py               # the table
    scripts/audit_misses.py --sitting     # only the rows needing a human call
    scripts/audit_misses.py --dry-run
    scripts/audit_misses.py --self-check
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"
AUDITLOG = ROOT / "docs" / "audit-log.md"

ROW = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]*?)\s*\|")
AUDIT_HDR = re.compile(r"^## Audit #(\d+)\b(.*)$")
FLAG = re.compile(r"^\s+- ([A-Z]+\d+[a-z]?): (.+)$")

# A status cell meaning "THIS entry turned out to be wrong or overstated".
#
# THE SUBJECT MATTERS, NOT THE VOCABULARY. A first version matched these words
# anywhere in the cell and swept in 24 entries that were doing the CORRECTING --
# A156 corrects A154, A177 refutes A176, T57/T126 are method entries ABOUT
# withdrawals -- plus entries like A97 whose cell merely says "Superseded
# costing follows". That is A358's failure exactly: matching how a cell is
# WORDED instead of what it is ABOUT. Found by reading the output, not the code.
#
# So the marker must govern the cell: either it OPENS the status (after any
# bold), or it appears as "<verb> [IN PART] by <ID>", which names this entry as
# the thing corrected.
_VERB = r"(WD|WITHDRAWN|CORRECTED|REFUTED|SCOPE-FLAGGED|SUPERSEDED)"
BAD_OPENS = re.compile(rf"^\**\s*{_VERB}\b", re.I)
BAD_BY = re.compile(rf"{_VERB}(\s+IN\s+PART)?,?(\s+same\s+\w+,?)?\s+by\s+[A-Z]+\d+", re.I)


def is_bad(status):
    return bool(BAD_OPENS.match(status) or BAD_BY.search(status))

# Which flag reason corresponds to which kind of fault. Used ONLY to separate a
# real catch from a lucky one; deliberately coarse, and the row is printed with
# both strings so the classification can be disputed by eye.
KIND = {
    "withdrawn within one audit window": "withdrawn",
    "rests on ONE run": "single-run",
    "no control mentioned": "no-control",
    "no evidence": "no-evidence",
    "dangling": "dangling",
}


def audits():
    """-> [ (number, is_void, {id: [reasons]}) ] in file order."""
    out, cur = [], None
    for line in AUDITLOG.read_text().split("\n"):
        m = AUDIT_HDR.match(line)
        if m:
            void = "VOID" in m.group(2).upper()
            cur = (int(m.group(1)), void, {})
            out.append(cur)
            continue
        m = FLAG.match(line)
        if m and cur is not None:
            cur[2].setdefault(m.group(1), []).append(m.group(2))
    return out


def bad_entries():
    """-> {id: status_cell} for entries whose status says they went wrong."""
    out = {}
    skipping = False
    for line in LEDGER.read_text().split("\n"):
        if line.startswith("## "):
            skipping = "USER QUEUE" in line.upper()
            continue
        if skipping:
            continue
        m = ROW.match(line)
        if m and m.group(1) not in out and is_bad(m.group(2)):
            out[m.group(1)] = m.group(2)
    return out


def kind_of(text):
    for frag, k in KIND.items():
        if frag.lower() in text.lower():
            return k
    return "other"


def classify():
    aud = audits()
    flagged = {}
    for n, void, flags in aud:
        if void:
            continue                    # a VOID audit never really ran
        for eid, reasons in flags.items():
            flagged.setdefault(eid, []).extend((n, r) for r in reasons)

    rows = []
    for eid, status in sorted(bad_entries().items()):
        hits = flagged.get(eid, [])
        if not hits:
            verdict = "MISSED"
        elif any(kind_of(r) == "withdrawn" for _, r in hits):
            verdict = "CAUGHT"          # flagged FOR being withdrawn in-window
        else:
            verdict = "CAUGHT-OTHER"    # flagged, but for something else
        rows.append((verdict, eid, status, hits))
    return aud, rows


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--dry-run" in a:
        print(f"would read {LEDGER} and {AUDITLOG}")
        print("would sort every withdrawn/corrected entry into CAUGHT / "
              "CAUGHT-OTHER / MISSED by whether an audit flagged it")
        print("would NOT judge whether a MISSED entry was catchable — that is the sitting")
        return 0
    if "--self-check" in a:
        return self_check()

    aud, rows = classify()
    real = [x for x in aud if not x[1]]
    print(f"{len(aud)} audit blocks, {len(real)} real ({len(aud)-len(real)} VOID)")
    print(f"{len(rows)} entries whose status says they went wrong\n")
    from collections import Counter
    c = Counter(v for v, *_ in rows)
    for k in ("CAUGHT", "CAUGHT-OTHER", "MISSED"):
        print(f"  {k:<14} {c[k]:>3}")
    print()
    only = "--sitting" in a
    for verdict, eid, status, hits in rows:
        if only and verdict != "MISSED":
            continue
        print(f"[{verdict:<12}] {eid}")
        print(f"    status: {status[:150]}")
        for n, r in hits:
            print(f"    audit #{n}: {r[:120]}")
    if only:
        print("\nThese are the rows needing a human call: was the fault VISIBLE at the\n"
              "time, or did it only become visible when a later measurement contradicted\n"
              "it? The first kind is a test case. The second is not a miss at all.")
    return 0


def self_check():
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    aud = audits()
    ids = [x[0] for x in aud]
    chk("parses every audit block", len(aud) >= 20, f"only {len(aud)}")
    chk("recognises the VOID blocks", any(v for _, v, _ in aud),
        "no audit marked VOID — the two known non-events are being counted as real")

    # A VOID AUDIT'S FLAGS MUST NOT COUNT -- tested by INJECTION, because the
    # two real VOID blocks carry ZERO flag lines, so no control over the real
    # file could ever discriminate. Verified by deleting the `if void: continue`
    # in classify(): without this control the suite still passed 9/9, which is
    # exactly the "control that cannot fail" T65 forbids. Found by running the
    # break rather than by reading the code.
    global AUDITLOG
    import tempfile
    _real = AUDITLOG
    try:
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "audit-log.md"
            fake.write_text(
                "## Audit #1 — VOID (never a real audit)\n"
                "  - A161: created and withdrawn within one audit window.\n\n"
                "## Audit #2 — since deadbeef\n"
                "- ledger: 1 entries (+1 this window), 0 withdrawn\n")
            AUDITLOG = fake
            _, rows = classify()
            v = {eid: verdict for verdict, eid, *_ in rows}
            chk("a VOID audit's flags are IGNORED (injected case)",
                v.get("A161") == "MISSED",
                f"got {v.get('A161')} — a non-event is being credited with a catch")
    finally:
        AUDITLOG = _real

    # GROUND TRUTH, read off the log by eye before this ran: audit #7 flagged
    # A161 for being created and withdrawn inside its window. If the parser
    # cannot find that exact pairing it is not reading the log.
    a7 = [f for num, void, f in aud if num == 7 and not void]
    chk("finds a KNOWN flag (audit #7 flagged A161)",
        bool(a7) and "A161" in a7[0], f"got {sorted(a7[0]) if a7 else 'no audit 7'}")
    chk("keeps the flag's REASON, not just the id",
        bool(a7) and "withdrawn" in " ".join(a7[0].get("A161", [])).lower(),
        "reasons dropped, so a real catch cannot be told from a lucky one")

    bads = bad_entries()
    # PRINCIPLED FLOOR, NOT A MAGIC NUMBER. The first version asserted ">= 60",
    # calibrated against the LOOSE matcher's 81; tightening the subject test to
    # 51 fired it, which was the control working but on a stale threshold.
    # Every WITHDRAWN entry is by definition an entry that went wrong, so the
    # population must contain all of them -- a floor that moves with the ledger
    # and still collapses loudly if the matcher breaks.
    wd = {eid for eid, st in
          ((m.group(1), m.group(2)) for m in
           (ROW.match(l) for l in LEDGER.read_text().split("\n")) if m)
          if re.match(r"^\**\s*WD\b", st, re.I)}
    chk(f"population contains every WITHDRAWN entry ({len(wd)} of them)",
        wd <= set(bads), f"missing {sorted(wd - set(bads))[:6]}")
    # NAMED NEGATIVE CONTROL, and the "<25% of the file" version it replaced was
    # useless: loosening the subject test back to a bare word-search still
    # passed it. These four entries are NOT faulty -- they are entries that
    # DESCRIBE a correction (A156 corrects A154; A177 refutes A176's suspect;
    # T57 is a method entry about withdrawals) or merely say "Superseded costing
    # follows" (A97, which is OPEN). A word-matcher sweeps in all four.
    NOT_BAD = {"A156", "A177", "T57", "A97"}
    intruders = NOT_BAD & set(bads)
    chk("entries that DESCRIBE a correction are excluded",
        not intruders,
        f"swept in {sorted(intruders)} — matching vocabulary, not subject (A358's failure)")
    chk("A161 is in that population", "A161" in bads, "a known-withdrawn entry is missing")
    chk("excludes user-queue rows", not any(k.startswith("U") for k in bads),
        f"queue rows counted: {[k for k in bads if k.startswith('U')]}")

    _, rows = classify()
    v = {eid: verdict for verdict, eid, *_ in rows}
    chk("A161 classifies as CAUGHT", v.get("A161") == "CAUGHT", f"got {v.get('A161')}")
    chk("the three verdicts all occur", len({verdict for verdict, *_ in rows}) == 3,
        f"got {sorted({verdict for verdict, *_ in rows})} — a classifier that only "
        f"ever says MISSED would look like a damning result and mean nothing")
    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
