#!/usr/bin/env python3
"""Tests for route.py's frontier parsing.

WHY THIS EXISTS
route.py was the only tool in the handoff's FIRST FIVE MINUTES with no
self-test, and on 2026-08-19 it was the one that produced a wrong answer: it
decided openness with `"OPEN" in status.upper()`, so **A124** -- status cell
"READ -- ... answers A99's *open* question" -- was reported as an open frontier
item, and as UNPRICED, and therefore as a reason to distrust the whole ranking.

The important property is not "does it find the open rows" (the buggy version
did that fine). It is **does it reject the near-miss** -- prose containing the
word. A test that only asserts the positives would have passed against the bug,
and a control that cannot fail is not a control (T65). So POSITIVES and
NEGATIVES are asserted separately and the runner says so.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location("route", Path(__file__).resolve().parent / "route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)

OPEN_RE = route.OPEN_RE

# Verbatim status cells. The A124 line is the exact text that fooled the old
# version -- keep it verbatim; a paraphrase would not be the same test.
POSITIVE = [
    ("OPEN [cost=2] — **THE FRONTIER**", "A99, the live frontier"),
    ("OPEN [cost=4]", "bare tag with a cost"),
    ("OPEN", "bare tag alone"),
    ("**OPEN** [cost=3]", "bolded tag"),
    (" OPEN [cost=2]", "leading whitespace"),
]

NEGATIVE = [
    ("READ — static, cross-validated against the ROM; **answers A99's open question: "
     "what sets the walker's `$s0`**", "A124 VERBATIM — the bug this test exists for"),
    ("MEASURED — closes the open question in A122", "'open question' mid-sentence"),
    ("WD — superseded; was OPEN until roll #40", "withdrawn row citing its own history"),
    ("INFERRED — leaves one thing open", "'open' as an adjective at the end"),
    ("NEGATIVE(splat asm) — nothing reopens it", "'reopens' must not match"),
]


def main():
    fails = []
    for text, why in POSITIVE:
        if not OPEN_RE.match(text):
            fails.append(f"FAIL (missed an open row) {why}: {text[:60]!r}")
    for text, why in NEGATIVE:
        if OPEN_RE.match(text):
            fails.append(f"FAIL (false frontier)    {why}: {text[:60]!r}")

    # The discrimination check, run against the REAL ledger: the fix must change
    # the answer. If old and new agree, either the ledger no longer contains the
    # A124-shaped row or the anchor is not doing anything -- and in both cases
    # this file has stopped being evidence. Say so rather than passing quietly.
    ledger = Path(__file__).resolve().parent.parent / "docs" / "findings-ledger.md"
    old_hits, new_hits = set(), set()
    for line in ledger.read_text().split("\n"):
        m = re.match(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        if "OPEN" in m.group(2).upper():
            old_hits.add(m.group(1))
        if OPEN_RE.match(m.group(2)):
            new_hits.add(m.group(1))
    dropped = old_hits - new_hits
    gained = new_hits - old_hits
    if gained:
        fails.append(f"FAIL: anchoring ADDED rows, which it cannot legitimately do: {sorted(gained)}")

    # The checkpoint-closing requirement must survive in the roll output. It is
    # a standing user instruction (2026-08-19), and the reason it lives in a
    # tool rather than in a note is that notes are applied by the same judgement
    # that forgets them. Asserted here so that deleting it fails the FIRST FIVE
    # MINUTES rather than going unnoticed for a dozen checkpoints.
    req = getattr(route, "CLOSING_REQUIREMENT", "")
    src = (Path(__file__).resolve().parent / "route.py").read_text()
    if "plain-language sentence" not in req.lower():
        fails.append("FAIL: route.CLOSING_REQUIREMENT missing or reworded past recognition")
    elif "print(CLOSING_REQUIREMENT)" not in src:
        fails.append("FAIL: CLOSING_REQUIREMENT is defined but never printed — "
                     "a reminder nothing emits is not a reminder (cf. T56)")

    # The OPENING requirement, same shape and for the same reason: announce the
    # roll BEFORE the work. Standing user instruction 2026-08-19 (roll #85).
    # It is asserted separately from the closing one so that losing either is a
    # distinct failure rather than a single "requirements" check that can pass
    # on half its job.
    opn = getattr(route, "OPENING_REQUIREMENT", "")
    if "announce this roll" not in opn.lower():
        fails.append("FAIL: route.OPENING_REQUIREMENT missing or reworded past recognition")
    elif "print(OPENING_REQUIREMENT)" not in src:
        fails.append("FAIL: OPENING_REQUIREMENT is defined but never printed — "
                     "a reminder nothing emits is not a reminder (cf. T56)")
    else:
        # ORDER IS THE POINT. "Announce before the work" is worthless if the
        # reminder prints below the roll it refers to, so assert it precedes
        # the roll line in the source rather than merely existing.
        i_open = src.index("print(OPENING_REQUIREMENT)")
        i_roll = src.index('print(f"[route] roll #')
        if i_open > i_roll:
            fails.append("FAIL: OPENING_REQUIREMENT prints AFTER the roll line — "
                         "an 'announce first' reminder that appears second")

    # THE WITNESS (T98). Every other number in a roll line is guessable: a
    # verdict from two options, a draw that only has to look like a probability,
    # a target from a two-item frontier. T91 fabricated all three and was caught
    # by luck. The witness is the one field that cannot be written before the
    # tool produced it -- but only if it is genuinely unpredictable, so that is
    # what is asserted, not merely that it exists.
    w = getattr(route, "make_witness", None)
    if w is None:
        fails.append("FAIL: route.make_witness is gone — the roll is forgeable again")
    else:
        if len(set(w() for _ in range(64))) < 60:
            fails.append("FAIL: witnesses repeat — not a witness, a label")
        if len(w()) != route.WITNESS_BITS // 4:
            fails.append(f"FAIL: witness is {len(w())} hex chars, want {route.WITNESS_BITS // 4}")
        # THE CONTROL THAT MATTERS, and the one that fails if someone
        # "simplifies" secrets back to random: route seeds `random` for the roll
        # itself, so a witness drawn from that stream is reproducible from the
        # roll number -- forgeable without running anything. Seed identically
        # twice; the witnesses must still differ.
        import random as _r
        _r.seed(1234); a = w()
        _r.seed(1234); b = w()
        if a == b:
            fails.append("FAIL: the witness is drawn from the SEEDED random stream — "
                         "reproducible from the roll number, so it proves nothing")
        if "witness" not in src.lower() or "[witness `" not in src:
            fails.append("FAIL: the witness is generated but never written to route-log.md — "
                         "an unrecorded witness cannot be checked afterwards")
        if "WITNESS:" not in src:
            fails.append("FAIL: the witness is not PRINTED with the roll — it can only be "
                         "quoted in the announcement if it appears there (cf. T56)")

    # THE OBSERVED-RUN GATE (T103). Four directions, because each is a distinct
    # way for the policy to be worthless: not gating at all, gating so hard that
    # a deferral cannot clear it (I cannot clear it myself, so that would stall
    # every session the user is away), accepting YESTERDAY's run, or accepting a
    # deferral from a previous day.
    ot = getattr(route, "observed_today", None)
    if ot is None:
        fails.append("FAIL: route.observed_today is gone — the daily gate is off")
    else:
        today, other = "2026-08-20", "2026-08-19"
        cases = [
            (f"## {today}T10:00:00+10:00 — build abc\n", today, True,  "a run TODAY clears it"),
            (f"## DEFERRED {today} — user away\n",       today, True,  "a recorded DEFERRAL clears it"),
            (f"## {other}T10:00:00+10:00 — build abc\n", today, False, "YESTERDAY's run must NOT clear it"),
            (f"## DEFERRED {other} — user away\n",       today, False, "yesterday's deferral must NOT clear it"),
            ("",                                          today, False, "an empty log must NOT clear it"),
        ]
        for text, day, want, why in cases:
            if ot(text, day) != want:
                fails.append(f"FAIL: observed-run gate — {why} (got {ot(text, day)}, want {want})")
        # And it must actually be WIRED to the roll, not merely defined (T56).
        if "observed_today(" not in src.split("def observed_today")[-1]:
            fails.append("FAIL: observed_today is defined but never called — a gate "
                         "nothing consults is not a gate")
        if "REFUSING TO ROLL" not in src:
            fails.append("FAIL: the gate does not refuse the roll")

    # A brand-new entry must read as staleness 0, not `roll`. It defaulted to 0
    # in `last_seen`, so B67 was born at roll #74 with staleness 74 and ~90% of
    # the next explore draw -- the exact inverse of what staleness is for.
    st = {"roll": 74, "last_entry_count": 0, "last_seen": {"A99": 71}}
    new_stale = route.staleness(st, "B67_NEVER_SEEN")
    old_stale = route.staleness(st, "A99")
    if new_stale != 0:
        fails.append(f"FAIL: an unseen entry reports staleness {new_stale}, want 0 "
                     f"(it would dominate the explore draw)")
    elif old_stale != 3:
        fails.append(f"FAIL: a seen entry reports staleness {old_stale}, want 3 "
                     f"(the fix must not flatten real staleness)")

    # Cost ties must break on STALENESS, not document order. Document order was
    # removed as the primary ranking long ago but survived as the tie-break, and
    # since new entries are written near the top of the ledger a new cost-2 row
    # outranked every older cost-2 row forever. Roll #75 picked B67 over A99 on
    # exactly that -- both cost=2, B67 merely 81 lines higher.
    real = route.open_items()
    by_cost = {}
    for eid, _b, c in real:
        by_cost.setdefault(c, []).append(eid)
    ties = [v for c, v in by_cost.items() if c is not None and len(v) > 1]
    if ties:
        st_now = route.load()
        for grp in ties:
            stales = [route.staleness(st_now, e) for e in grp]
            if stales != sorted(stales, reverse=True):
                fails.append(f"FAIL: cost-tied rows {grp} are not ordered most-stale-first "
                             f"(staleness {stales}) — document order is deciding again")
    else:
        print("tie-break: NOTE — no cost ties in the current ledger, so this check "
              "is inert right now. The ordering rule still holds.")

    # +6, not +5: discrimination, closing-requirement, opening-requirement,
    # staleness, tie-break, and the witness group (T98). A check that runs
    # but is not counted makes the summary understate the suite -- and the
    # summary is what anyone actually reads.
    # PRIOR WORK MUST BE ON THE ROLL SCREEN (T147). T129 added a cited-by
    # footer to `ledger.py --show` and it works. T135 recorded me reading that
    # footer and expanding nothing; A305 is the same failure again, the same
    # day, on an item whose footer I had read twice. A reading rule that fails
    # twice in a day needs MOVING, not repeating: the duplication is decided
    # when the target is chosen, so the list belongs on the roll screen.
    _rsrc = (Path(__file__).resolve().parent / "route.py").read_text()
    # COUNTED, NOT MERELY PRESENT. The first version grepped for the function
    # NAME, which still matches when only the DEFINITION survives -- deleting
    # the CALL left the suite at 19/19 on code that no longer listed anything.
    # Definition plus at least one call site means two occurrences.
    if (_rsrc.count("_print_recent_work_on") < 2
            or "EXPAND BEFORE PLANNING" not in _rsrc):
        fails.append("FAIL: the roll does not list prior work on its target — "
                     "the cited-by footer alone is read too late (T135, A305)")
    # ...and its failure path must REPORT. A silent `except` would let the list
    # vanish unnoticed and the duplication return with no sign anything changed.
    if "could not list prior work on" not in _rsrc:
        fails.append("FAIL: the prior-work listing fails silently — a bare "
                     "except hides its own absence")

    # ------------------------------------------------------------------
    # THE COUNT IS SHARED ARITHMETIC, NOT A DISPLAY (T131 again, third tool).
    #
    # route.py kept a private row regex after T131 moved the user queue out of
    # the entry count everywhere else, so it counted 470 where check_ledger.py
    # counted 462. check_ledger.py subtracts OUR number from ITS number to
    # decide whether to nag about unrolled entries, so the 8-row offset raised
    # that trigger from 6 to 14 and had been silently suppressing it.
    #
    # These are BEHAVIOUR checks against a synthetic ledger, not greps of
    # route.py -- a source grep matches a definition that is no longer wired to
    # anything (T141/T146/T147), and this bug WAS a wiring bug.
    FIXTURE = "\n".join([
        "# Fixture ledger",
        "",
        "## FINDINGS",
        "",
        "| A1 | OPEN [cost=2] | a real open finding | 2026-08-22 |",
        "| T2 | MEASURED — settled | a real closed finding | 2026-08-22 |",
        "",
        "## THE USER QUEUE",
        "",
        "| U1 | LIVE 2026-08-21 | an ordinary queue item | — |",
        "| U2 | OPEN [cost=1] | a queue row wearing an OPEN status | — |",
        "",
        "## MORE FINDINGS",
        "",
        "| A3 | OPEN [cost=3] | a real open finding after the queue | 2026-08-22 |",
        ""])
    _fix = Path(tempfile.mkdtemp()) / "findings-ledger.md"
    _fix.write_text(FIXTURE)
    _real_ledger = route.LEDGER
    try:
        route.LEDGER = _fix
        # Vacuity guard FIRST. If the old regex and the new counter agree on
        # this fixture then the fixture cannot tell them apart and the two
        # controls below prove nothing -- which is how a control quietly stops
        # discriminating (T65/T100).
        naive = len(re.findall(r"^\|\s*[A-Z]+\d+[a-z]?\s*\|", FIXTURE, re.M))
        got = route.entry_count()
        if naive != 5:
            fails.append(f"FAIL: the fixture is not exercising the bug — the old "
                         f"regex counts {naive} rows in it, expected 5")
        elif got == naive:
            fails.append("FAIL: entry_count() still counts queue rows — it agrees "
                         f"with the pre-fix regex at {got}")
        elif got != 3:
            fails.append(f"FAIL: entry_count() = {got} on the fixture, expected 3 "
                         f"(A1, T2, A3 — never U1/U2)")

        # The latent half: a queue row is not a routable frontier item. Today
        # every queue row reads LIVE or SWEPT so nothing leaks, which is a fact
        # about the queue's wording and not about this parser.
        ids = [e for e, _b, _c in route.open_items()]
        if "U2" in ids:
            fails.append(f"FAIL: a queue row reached the frontier — open_items() "
                         f"returned {ids}; a roll could select U2")
        elif ids != ["A3", "A1"] and sorted(ids) != ["A1", "A3"]:
            fails.append(f"FAIL: open_items() returned {ids} on the fixture, "
                         f"expected A1 and A3")
    finally:
        route.LEDGER = _real_ledger

    # ...and the one that actually broke: the two counters must AGREE on the
    # REAL ledger, because one is subtracted from the other. Asserted against
    # check_ledger's parse(), not against a number written down here, so it
    # cannot drift into a copied constant.
    try:
        import check_ledger as _cl
        _cl_rows, _, _ = _cl.parse(route.LEDGER.read_text())
        if len(_cl_rows) != route.entry_count():
            fails.append(f"FAIL: route.py counts {route.entry_count()} entries, "
                         f"check_ledger.py counts {len(_cl_rows)} — check_ledger "
                         f"subtracts one from the other to decide when to nag")
    except Exception as e:
        fails.append(f"FAIL: could not compare the two entry counters ({e}) — "
                     f"this is the check that caught the 470-vs-462 split")

    # USER-DIRECTED ENTRIES MUST NOT ACCRUE TOWARD THE ROLL NAG (T155).
    # The user's rule: a roll distributes work I choose; user-directed work was
    # chosen by them and was never routed. Counting it manufactured a routing
    # alarm from a day in which no routing decision was skipped.
    #
    # DISCRIMINATING, not a smoke test: the fixture holds BOTH kinds, so a
    # routable_entry_count() that ignored the predicate would equal
    # entry_count() and fail here. Asserted against check_ledger's imported
    # predicate rather than a copied string.
    FIX2 = "\n".join([
        "# Fixture", "", "## FINDINGS", "",
        "| A1 | OPEN [cost=2] | a rolled finding | 2026-08-22 (roll #1) |",
        "| A2 | MEASURED | another rolled finding | 2026-08-22 |",
        "| T1 | INTERVENED | user asked for this | 2026-08-22 (user-directed, no roll consumed) |",
        "| T2 | INTERVENED | so did they | 2026-08-22 (USER-DIRECTED) |",
        ""])
    _f2 = Path(tempfile.mkdtemp()) / "findings-ledger.md"
    _f2.write_text(FIX2)
    _real2 = route.LEDGER
    try:
        route.LEDGER = _f2
        _all, _routable = route.entry_count(), route.routable_entry_count()
        if _all != 4:
            fails.append(f"FAIL: entry_count()={_all} on the T155 fixture, expected 4")
        elif _routable == _all:
            fails.append("FAIL: routable_entry_count() ignores the user-directed "
                         f"predicate — it equals entry_count() at {_all}")
        elif _routable != 2:
            fails.append(f"FAIL: routable_entry_count()={_routable}, expected 2 "
                         f"(A1, A2 — T1/T2 are user-directed)")
        # CASE-INSENSITIVE, because the marker is written both ways in the real
        # ledger and a case-sensitive predicate would silently count half of them.
        if _routable == 3:
            fails.append("FAIL: the predicate is case-sensitive — 'USER-DIRECTED' "
                         "was counted as routable")
    finally:
        route.LEDGER = _real2

    # ...and the roll must actually STORE the baseline, or check_ledger reads a
    # stale one forever. Definition plus a write is two occurrences (T147).
    if _rsrc.count("routable_entry_count") < 2 or 'st["last_routable_count"]' not in _rsrc:
        fails.append("FAIL: the roll does not record a routable baseline — "
                     "check_ledger would compare against a stale number")

    total = len(POSITIVE) + len(NEGATIVE) + 14
    if dropped:
        print(f"discrimination: OK — anchoring drops {sorted(dropped)} "
              f"({len(old_hits)} -> {len(new_hits)} open rows)")
    else:
        print("discrimination: NOTE — old and new agree on the current ledger. "
              "The unit negatives above still hold, but this ledger no longer "
              "contains a row that distinguishes them.")

    for f in fails:
        print(f)
    print(f"\n{total - len(fails)}/{total} correct "
          f"({len(POSITIVE)} positive, {len(NEGATIVE)} negative, 1 discrimination, "
          f"1 closing-requirement, 1 opening-requirement, 1 staleness, 1 tie-break, "
          f"1 witness, 1 observed-run gate, 2 prior-work, 3 entry-count, 2 routable)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
