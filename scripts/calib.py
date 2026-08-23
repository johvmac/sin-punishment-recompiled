#!/usr/bin/env python3
"""Confidence, recorded when a claim is made and SCORED when it is settled.

WHY THIS EXISTS (T177, T179)
----------------------------
Every load-bearing entry carries a FALSIFIER — what would prove it wrong. That
says how to CHECK a claim. It never says how SURE I was, and nothing anywhere
scores that against what actually held.

So a confidently wrong claim survives until a roll happens to revisit it, which
is luck. Five instances in one session, and THREE were surfaced by the user
asking a question rather than by any check.

Calibration is the property that when you say 80% you are right about 80% of the
time. It is deliberately separate from being right: 70%-and-right-70%-of-the-time
is perfect calibration with a mediocre hit rate. The forecasting result that
makes it worth the trouble is that calibration IMPROVES WITH SCORING and drifts
silently without it — and that expertise tends to make it worse, because
confidence rises faster than accuracy.

THREE HONESTY PROPERTIES, EACH LOAD-BEARING
-------------------------------------------
1. **FORWARD ONLY. Never retrofit.** Assigning a confidence to an entry whose
   outcome is already known is hindsight, and it would manufacture perfect
   calibration out of nothing. The table starts empty and fills as claims are
   made. There is no shortcut and this tool will not offer one.

2. **THE UNSCORED COUNT IS REPORTED AS LOUDLY AS THE SCORES.** Most entries here
   are never revisited, so the scored set is biased toward claims that turned
   out interesting or wrong — exactly the wrong sample. A calibration figure
   without its denominator is worse than none.

3. **A CONFIDENCE IS A NUMBER, NOT A WORD.** "Likely" cannot be scored. The
   field is a decimal 0..1 and the parser refuses anything else.

THE FIELD
---------
In any entry making a checkable claim:

    CONFIDENCE: 0.8 — that the census interval is the only cause

Scored when a LATER entry corrects, withdraws, refutes or confirms it, using
check_ledger's SUPERSEDES_RE so "corrected" means one thing project-wide.

Usage:
    scripts/calib.py                 # the table, with the unscored count
    scripts/calib.py --base-rate     # how often entries get overturned at all
    scripts/calib.py --unscored      # what is waiting on an outcome
    scripts/calib.py --dry-run
    scripts/calib.py --self-check
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"

ROW = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|")
# A NUMBER, not a word. "high" cannot be scored, so it is not accepted.
CONF = re.compile(r"CONFIDENCE:\s*(0?\.\d+|0|1(?:\.0+)?)\b")
BANDS = [(0.0, 0.6, "<0.6"), (0.6, 0.8, "0.6-0.8"),
         (0.8, 0.95, "0.8-0.95"), (0.95, 1.01, ">=0.95")]


def _cl():
    spec = importlib.util.spec_from_file_location(
        "_cl_calib", ROOT / "scripts" / "check_ledger.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rows(text=None):
    """{id: full row text}, user-queue rows excluded."""
    t = text if text is not None else LEDGER.read_text()
    out, skipping = {}, False
    for line in t.split("\n"):
        if line.startswith("## "):
            skipping = "USER QUEUE" in line.upper()
            continue
        if skipping:
            continue
        m = ROW.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = line
    return out


def claims(text=None):
    """{id: confidence} for entries that recorded one."""
    out = {}
    for eid, line in rows(text).items():
        m = CONF.search(line)
        if m:
            out[eid] = float(m.group(1))
    return out


def outcome(eid, rs, cl):
    """'overturned' if a later entry corrects it, else None (= not yet settled).

    Uses check_ledger's own definition of supersession so that "corrected" means
    the same thing here as it does in the audit ladder.
    """
    packed = {k: (v, v, 0) for k, v in rs.items()}
    later = cl.superseded_by_later(eid, packed)
    return "overturned" if later else None


def report(text=None):
    cl = _cl()
    rs = rows(text)
    cs = claims(text)
    scored, unscored = [], []
    for eid, conf in sorted(cs.items()):
        o = outcome(eid, rs, cl)
        (scored if o else unscored).append((eid, conf, o))
    return rs, cs, scored, unscored


def cmd_table(text=None):
    rs, cs, scored, unscored = report(text)
    print(f"CONFIDENCE, recorded on {len(cs)} of {len(rs)} entries")
    print(f"  scored (an outcome exists) : {len(scored)}")
    print(f"  UNSCORED (no outcome yet)  : {len(unscored)}")
    print()
    if not scored:
        print("  NO SCORED CLAIMS YET — and that is correct, not a fault.")
        print("  Confidence is recorded going FORWARD only. Retrofitting a")
        print("  confidence to an entry whose outcome is known is hindsight and")
        print("  would manufacture perfect calibration out of nothing.")
        print()
        print("  This table becomes readable after enough claims have settled.")
        return 0
    print(f"  {'band':<10} {'n':>4} {'held':>6} {'overturned':>11}   actual vs stated")
    print("  " + "-" * 58)
    for lo, hi, name in BANDS:
        b = [x for x in scored if lo <= x[1] < hi]
        if not b:
            continue
        over = sum(1 for x in b if x[2] == "overturned")
        held = len(b) - over
        rate = held / len(b)
        mid = sum(x[1] for x in b) / len(b)
        print(f"  {name:<10} {len(b):>4} {held:>6} {over:>11}   "
              f"held {rate:.0%} where {mid:.0%} was claimed")
    print("  " + "-" * 58)
    print("  A band whose HELD rate sits below its claimed confidence is")
    print("  overconfidence; above it is underconfidence. Both are information.")
    print()
    print(f"  READ THE UNSCORED COUNT FIRST: {len(unscored)} claims have no outcome.")
    print("  Entries are revisited only when a roll lands on them, so the scored")
    print("  set is biased toward claims that turned out interesting or wrong.")
    return 0


# An entry whose OWN status says it went wrong -- the marker must GOVERN the
# cell, not merely appear in it. Same test A372 arrived at after its first
# version swept in 30 entries that were doing the CORRECTING.
_VERB = r"(WD|WITHDRAWN|CORRECTED|REFUTED|SCOPE-FLAGGED|SUPERSEDED)"
_BAD_OPENS = re.compile(rf"^\|\s*[A-Z]+\d+[a-z]?\s*\|\s*\**\s*{_VERB}\b", re.I)
_BAD_BY = re.compile(rf"{_VERB}(\s+IN\s+PART)?,?(\s+same\s+\w+,?)?\s+by\s+[A-Z]+\d+", re.I)


def cmd_base_rate(text=None):
    cl = _cl()
    rs = rows(text)
    packed = {k: (v, v, 0) for k, v in rs.items()}
    loose = [e for e in rs if cl.superseded_by_later(e, packed)]
    tight = [e for e, l in rs.items() if _BAD_OPENS.match(l) or _BAD_BY.search(l)]
    n = len(rs)
    print("BASE RATE — the prior a confidence is judged against")
    print(f"  entries                                    : {n}")
    print(f"  REVISITED with a correction-flavoured word : {len(loose)}"
          f"  ({100*len(loose)/n:.1f}%)")
    print(f"  whose OWN status says they went wrong      : {len(tight)}"
          f"  ({100*len(tight)/n:.1f}%)")
    print()
    print("  USE THE SECOND NUMBER. The first is an OVER-COUNT and reporting it")
    print("  as an error rate would be the exact failure this tool exists to")
    print("  prevent: `superseded_by_later` matches 'closed by' and 'vindicat',")
    print("  so an entry that was ANSWERED or CONFIRMED counts the same as one")
    print("  that was refuted. Being finished is not being wrong.")
    print()
    print("  This is ACCURACY, not calibration — how often a claim here turns")
    print("  out wrong at all. A claim stated at 0.95 has to earn the gap.")
    return 0


def cmd_unscored(text=None):
    _, _, _, unscored = report(text)
    if not unscored:
        print("  nothing recorded a confidence yet.")
        return 0
    print(f"{len(unscored)} claim(s) awaiting an outcome:")
    for eid, conf, _ in unscored:
        print(f"  {eid:<6} {conf}")
    return 0


def self_check():
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    hdr = "| # | s | f | e |\n|---|---|---|---|\n"
    syn = (hdr
           + "| A1 | MEASURED | claim one. CONFIDENCE: 0.9 — that it holds | 2026-01-01 |\n"
           + "| A2 | MEASURED | claim two. CONFIDENCE: 0.5 — shaky | 2026-01-01 |\n"
           + "| A3 | MEASURED | no confidence recorded here | 2026-01-01 |\n"
           + "| A4 | MEASURED | CORRECTED: A1 is refuted by this | 2026-01-02 |\n"
           + "## THE USER QUEUE\n| U1 | LIVE | CONFIDENCE: 0.7 | x |\n")

    c = claims(syn)
    chk("parses a numeric confidence", c.get("A1") == 0.9 and c.get("A2") == 0.5, f"got {c}")
    chk("ignores an entry with none", "A3" not in c, "invented a confidence")
    chk("excludes user-queue rows", "U1" not in c, "a queue row scored as a claim")
    chk("REFUSES a worded confidence",
        not claims(hdr + "| A9 | M | CONFIDENCE: high | 2026-01-01 |\n"),
        "'high' accepted — a word cannot be scored")

    _, _, scored, unscored = report(syn)
    sids = {e for e, _, _ in scored}
    chk("scores a claim a later entry corrected", "A1" in sids, f"scored={sids}")
    chk("leaves an uncorrected claim UNSCORED", "A2" in {e for e, _, _ in unscored},
        "an unsettled claim counted as held")

    # THE HONESTY CONTROLS. Both of these are the point of the tool, not extras.
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_table(syn)
    out = buf.getvalue()
    # THE COUNT, not the word. A first version asserted "UNSCORED" appeared
    # anywhere in the output and passed with the count line deleted, because the
    # closing paragraph also says UNSCORED. Matching vocabulary where the
    # subject was meant -- the fourth instance of that shape this week.
    _, _, _sc, _un = report(syn)
    chk("the table reports the unscored COUNT, not just the word",
        f": {len(_un)}" in out and "UNSCORED" in out,
        "a calibration figure without its denominator is worse than none")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        cmd_table(hdr + "| A5 | M | CONFIDENCE: 0.8 — nothing settled | 2026-01-01 |\n")
    chk("says so plainly when nothing is scored yet",
        "NO SCORED CLAIMS YET" in buf2.getvalue(),
        "an empty table that looks like a result")

    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    if "--dry-run" in a:
        print(f"would read {LEDGER}; writes nothing")
        print("would report confidence bands, the unscored count, and the base rate")
        return 0
    if "--base-rate" in a:
        return cmd_base_rate()
    if "--unscored" in a:
        return cmd_unscored()
    return cmd_table()


if __name__ == "__main__":
    sys.exit(main())
