#!/usr/bin/env python3
"""Force the explore/exploit decision instead of leaving it to judgement.

WHY
---
Cheapest-path routing assumes edge costs are KNOWN. Ours are estimates, and the
estimates have a bad track record -- which is exactly the condition where greedy
search underperforms and exploration pays.

There is direct evidence on this project. The largest result of 2026-08-18 (two
apparently separate bugs collapsing into one) came from an off-path jab: taking
the attract freeze's workaround and trying it against the START stall for no
better reason than "it is cheap". One 30s run closed a whole problem. Over the
same period the disciplined cheapest-path chain produced four wrong conclusions.

The second failure this fixes is subtler: **cost estimates go stale.** A finding
can slash the cost of an unrelated open problem, but only the current frontier
ever gets re-costed, so the bargain is never noticed. Weighting the explore pick
by staleness attacks that directly.

Why a script rather than a rule: a rule that says "occasionally try something
else" is applied by the same judgement that mis-costs everything, and can be
rationalised away silently. A roll cannot. Every roll is appended to
docs/route-log.md, so skipping one is visible.

Usage:
    scripts/route.py                # roll, record, print the decision
    scripts/route.py --status       # show open items + staleness, do NOT roll
    scripts/route.py --history      # past decisions
    SNP_ROUTE_EPS=0.25 scripts/route.py     # override epsilon (default 0.30)
"""
import json
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"
STATE = ROOT / "docs" / ".route-state.json"
LOG = ROOT / "docs" / "route-log.md"
# Raised 0.20 -> 0.30 on 2026-08-18, on 31 rolls of evidence rather than taste.
# Observed rate was 13% (4 of 31) against a nominal 20%, with a longest EXPLOIT
# streak of 12 -- and the four explores yielded three closures or tooling fixes
# (A44 closed; B31 closed as not-worth-doing, which also surfaced T19, a wrong
# path that would have broken the next day's scheduled task; B36 surfaced T21,
# three ledger IDs cited but never written). The 27 exploits produced the
# headline fix, but per roll the explores paid better, which is exactly what the
# docstring above predicts when cost estimates are unreliable -- and today they
# repeatedly were (A80 stayed "frontier" for four rolls after being answered;
# A96 and A97 were not even on the list).
# Revisit after ~20 rolls: audit.py reports the ratio, and if frontier progress
# stalls this is the first thing to put back.
EPS = float(os.environ.get("SNP_ROUTE_EPS", "0.30"))


COST_RE = re.compile(r"\[cost=(\d+)\]")

# The same row shape ledger.py's ROW matches. Kept here only as the SHAPE of a
# table row; what makes a row an ENTRY is is_non_entry_section(), imported.
ROW_RE = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|")

# The status cell must OPEN with the tag, not merely contain the word.
#
# This used to be `"OPEN" in status.upper()`, and on 2026-08-19 that put **A124**
# on the frontier -- a READ entry whose status cell says "answers A99's *open*
# question". Ordinary English prose, matched as a status tag. It also reported
# A124 as UNPRICED, so `--status` ended with "the ordering is not a ranking":
# a real warning about an entry that was never open. Six items were claimed;
# five existed.
#
# That is the ledger's own rule 2 failing inside the tooling that enforces it --
# a test that could not distinguish the tag from the word cannot have been
# evidence for either. Anchoring is what makes it discriminate; `test_route.py`
# asserts the discrimination, using A124's literal status string as the negative.
#
# LEADING `>>> ... <<<` ANNOTATION BLOCKS ARE SKIPPED BEFORE THE ANCHOR (A550).
# This project's standing convention for recording a correction is to PREFIX the
# status cell with `>>> what changed <<<`. Anchoring at position zero meant that
# every open item so annotated SILENTLY LEFT THE ROUTABLE FRONTIER -- the dice
# could never select it again, and nothing said so. Five items were lost this
# way (A211, A225, T211, A218, A219), including one with a measured result and a
# four-minute next step. The frontier had collapsed from seven items to two.
#
# The skip is deliberately NARROW: it consumes only complete `>>>...<<<` blocks
# at the START, then applies the SAME anchored test to what remains. A status
# that is genuinely closed still fails -- `>>> ... <<< MEASURED (...)` anchors on
# MEASURED, and `CLOSED ... Was: OPEN [cost=2]` still never matches, which a
# looser "OPEN anywhere" rule would have got wrong on three real entries.
OPEN_RE = re.compile(r"\s*(?:>>>.*?<<<\s*)*\**OPEN\b", re.I)

# Same anchoring, same reason, for the WITHDRAWN tag. `"WD" in tag` marked T72
# withdrawn because its status explains that A138 is "the WD entry" -- and
# check_ledger.py and ledger.py then disagreed about the withdrawn count (35 vs
# 36). Three tools must not each carry their own idea of what a tag means.
WD_RE = re.compile(r"\s*\**WD\b", re.I)

# Printed at the end of EVERY roll, because a roll is how a checkpoint starts and
# skipping one leaves a gap in docs/route-log.md. Requested by the user
# 2026-08-19 and deliberately NOT left to a memory file or to habit: this
# project's whole method is that a discipline applied by judgement is a
# discipline that gets rationalised away silently. `test_route.py` asserts this
# string survives, so deleting it fails a check in the FIRST FIVE MINUTES.
CLOSING_REQUIREMENT = (
    "\n[route] CLOSE THIS CHECKPOINT WITH ONE PLAIN-LANGUAGE SENTENCE\n"
    "        saying what it achieved. No hex, no entry IDs, no tool names.\n"
    "        If the honest answer is 'nothing moved forward, I fixed a\n"
    "        measuring instrument' -- say that. Exposing it is the point."
)

# Standing user instruction, 2026-08-19 (roll #85): ANNOUNCE the roll before
# doing the work, not after.
#
# Why this is mechanised rather than remembered: the roll is what makes the
# routing auditable, and a roll reported only in the write-up is indistinguish-
# able from a roll rationalised after the fact. The user cannot tell whether the
# target was drawn or chosen unless the draw is stated BEFORE the work appears.
# T28's rule applies -- every discipline left to memory on this project has been
# forgotten -- and this is the twin of CLOSING_REQUIREMENT, which exists for the
# same reason. test_route.py asserts both are defined and both are printed.
OPENING_REQUIREMENT = (
    "\n[route] ANNOUNCE THIS ROLL BEFORE DOING THE WORK -- verdict, draw,\n"
    "        eps, target AND THE WITNESS BELOW, at the TOP of the checkpoint.\n"
    "        A roll reported only afterwards cannot be told apart from one\n"
    "        rationalised after the fact, which is the whole thing the roll\n"
    "        prevents."
)

# THE WITNESS (T98) -- why a random token and not a stronger instruction.
#
# T91: a checkpoint header was written BEFORE route.py ran -- invented verdict,
# invented draw, invented target. It was caught only because the real output
# appeared one line later and disagreed. The response at the time was a rule
# ("the announcement is a TRANSCRIPTION, not a composition"), and T89/T90/T95
# are all the same lesson: a rule with no checker is a preference. Every number
# in a roll line is guessable -- a verdict from two options, a draw that only
# has to look like a probability, a target from a two-item frontier. A plausible
# fabrication is indistinguishable from a transcription.
#
# A random witness is not guessable. It is generated at roll time, recorded in
# route-log.md, and printed as part of the announcement, so quoting it is
# PROOF THE TOOL RAN. This does not make lying impossible -- it makes it
# impossible to do by accident, which is what actually happened.
#
# `secrets`, not `random`: the module-level `random` here is seeded for the
# roll itself and its stream is reproducible by design. A witness drawn from
# that stream would be predictable from the roll number, which is the one
# property it must not have.
WITNESS_BITS = 24


def observed_today(text, today):
    """Has an observed run — or an explicit DEFERRAL — been recorded today?

    Both count, and that is deliberate. **I cannot perform an observed run
    myself**: it needs the user's eyes and ears. A gate I am unable to clear
    alone would stall every checkpoint whenever they are away, and a rule that
    blocks all work is one that gets deleted rather than followed (T29).

    So a DEFERRAL clears it too. The discipline is not "the run happened", it is
    **"the run was not silently skipped"** -- recorded either way, the same rule
    the ledger uses. A deferral is a decision with a reason attached; a silent
    skip is the thing this exists to prevent.
    """
    return bool(re.search(rf"^## {re.escape(today)}T", text, re.M) or
                re.search(rf"^## DEFERRED {re.escape(today)}\b", text, re.M))


def make_witness():
    """A witness for one roll. MUST NOT come from the seeded `random` stream.

    `random` is seeded and reproducible by design -- that is what makes the roll
    itself auditable. A witness drawn from it would be predictable from the roll
    number, i.e. forgeable without running anything, which is the single
    property it exists to deny. test_route.py asserts this by seeding `random`
    identically twice and requiring the two witnesses to DIFFER.
    """
    import secrets
    return secrets.token_hex(WITNESS_BITS // 8)


def open_items():
    """OPEN rows, CHEAPEST FIRST.

    This used to return them in file order and the caller called items[0] "the
    cheapest frontier item". It was nothing of the kind -- it was whichever OPEN
    row happened to sit highest in the document, and the ledger is append-ish, so
    that mostly meant "the oldest open question". 15 of the first 19 rolls were
    EXPLOIT decisions steered by that, and on 2026-08-18 it pointed at A53 (a
    re-costing chore whose premise had just been demolished) while the actual
    frontier was A18. Calling document order a cost ranking is exactly the
    claim-broader-than-evidence failure this ledger exists to prevent, so the
    ordering is now explicit or it is not claimed at all.

    Annotate an OPEN row with `[cost=N]` -- N is a rough relative price (build
    cycles, run minutes, tokens; the scale only has to be consistent). Rows
    without one sort last and are reported as unpriced.
    """
    items = []
    # Queue rows are excluded here too. Today they are all LIVE/SWEPT so none
    # of them matches OPEN_RE and nothing leaks -- but that is a property of
    # the current queue's wording, not of this parser, and a queue item written
    # as `| U9 | OPEN [cost=2] |` would become a routable frontier item. The
    # roll is not the place to discover that.
    for line in ledger_rows():
        m = re.match(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|", line)
        if m and OPEN_RE.match(m.group(2)):
            raw = m.group(3)
            # the marker may sit in the status cell (`| A18 | OPEN [cost=2] |`)
            # or in the body; accept either
            c = COST_RE.search(m.group(2)) or COST_RE.search(raw)
            cost = int(c.group(1)) if c else None
            body = re.sub(r"[*`~]", "", COST_RE.sub("", raw)).strip()
            items.append((m.group(1), body[:96], cost))
    # None sorts last. TIES BREAK ON STALENESS, most-stale first -- NOT on file
    # order.
    #
    # This function's docstring above records that document order was removed as
    # the primary ranking. It survived as the tie-break, and that is just as
    # wrong: new entries are written near the top of the ledger, so a new cost-2
    # row outranks every older cost-2 row FOREVER. Roll #75 picked B67 over A99
    # on exactly that, both cost=2, purely because B67 sat 81 lines higher.
    #
    # Staleness is the right tie-break because it is the one metric that already
    # exists for "which of these has been neglected", and it cannot be gamed by
    # where an entry happens to be written.
    st = load()
    items.sort(key=lambda x: (x[2] is None, x[2] if x[2] is not None else 0,
                              -staleness(st, x[0])))
    return items


def staleness(st, eid):
    """Rolls since this entry was last picked -- 0 for an entry never seen.

    `last_seen` used to default to 0, so a BRAND-NEW entry read as
    `roll - 0 = roll`: B67 was born at roll #74 with staleness 74 and an explore
    weight of 75 against the frontier's 4, i.e. ~90% of the next explore draw.
    That inverts the reason staleness is weighted at all -- this file's own
    docstring says the point is that "an item untouched for many rolls is
    exactly the one whose cost estimate is most likely out of date", and a new
    entry has the FRESHEST estimate on the board.

    Unknown -> 0. Entries are seeded into `last_seen` when a roll happens, so
    they then age normally from birth.
    """
    return st["roll"] - st["last_seen"].get(eid, st["roll"])


def unpriced(items):
    return [e for e, _, c in items if c is None]


def ledger_rows():
    """Every line that is a LEDGER ENTRY row -- queue rows excluded.

    T131 removed the user queue from the entry count in check_ledger.py and
    ledger.py and said, in as many words, that the rule must be IMPORTED and
    not copied "because two definitions would let a row be an entry for one
    tool and not for another and nobody could say which was authoritative".
    This file then kept a third, private regex, and that is exactly what
    happened: route.py counted 470 while check_ledger.py counted 462.

    It was not cosmetic. check_ledger.py computes `since = len(rows) -
    state["last_entry_count"]` -- ITS count minus OUR stored count -- and nags
    at `since >= 6`. With an 8-row offset baked in, `since` started at -8, so
    the "you have written N entries without rolling" reminder needed 14 new
    entries to fire instead of 6, and had been silent since the queue was
    added. A disagreement between two counters is not a display bug when one
    of them is subtracted from the other.

    Fails OPEN: if check_ledger cannot be imported we count every row rather
    than crash, because route.py must be able to roll even when the ledger
    tooling is broken. That is the same bias as cited_by() above.
    """
    text = LEDGER.read_text()
    try:
        _sd = str(Path(__file__).resolve().parent)
        if _sd not in sys.path:
            sys.path.insert(0, _sd)
        from check_ledger import is_non_entry_section   # T131: ONE definition
    except Exception:
        is_non_entry_section = lambda _h: False

    rows, skip = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            skip = is_non_entry_section(line)
        if not skip and ROW_RE.match(line):
            rows.append(line)
    return rows


def entry_count():
    return len(ledger_rows())


def routable_entry_count():
    """Entries a ROLL could have chosen -- user-directed ones excluded (T155).

    Fails OPEN, like ledger_rows(): if check_ledger cannot be imported every row
    counts, which over-reports rather than silently under-reporting. An alarm
    that fires too often is noise; one that never fires is broken.
    """
    try:
        _sd = str(Path(__file__).resolve().parent)
        if _sd not in sys.path:
            sys.path.insert(0, _sd)
        from check_ledger import is_user_directed      # T131: ONE definition
    except Exception:
        return len(ledger_rows())
    return sum(1 for line in ledger_rows() if not is_user_directed(line))


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"roll": 0, "last_entry_count": 0, "last_seen": {}}


def _print_recent_work_on(target, n=4):
    """The last few entries that CITE the target, printed AT ROLL TIME.

    WHY THIS IS NOT A NAG (T135, A305). `ledger.py --show` has printed a
    cited-by footer since T129, and it works -- it names exactly the entries
    that would stop a duplicated measurement. It has now failed TWICE IN ONE
    DAY for the same reason: I read the footer and did not open anything.
    T135's remedy was a READING RULE and A305 is that rule breaking again.

    A rule that fails twice in a day is not a rule that needs repeating, it
    needs moving. The duplication is decided HERE -- at the moment the target
    is chosen and before any work is planned -- not later when the write-up is
    being assembled. So the most recent work on this item goes on the same
    screen as the roll.

    It is DERIVED, never declared: it re-uses ledger.py's own citation match,
    so a third definition of 'cites' cannot drift from the other two (T121).
    Silent when nothing cites the target, and never fatal -- route.py must roll
    even if the ledger cannot be parsed.
    """
    try:
        import importlib.util
        # ledger.py imports check_ledger for the ONE definition of "plain"
        # (T121), so the scripts dir must be importable before it is loaded.
        _sd = str(Path(__file__).resolve().parent)
        if _sd not in sys.path:
            sys.path.insert(0, _sd)
        spec = importlib.util.spec_from_file_location(
            "_led", Path(__file__).resolve().parent / "ledger.py")
        led = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(led)
        rows = led.parse()
        t = target.upper()
        pat = re.compile(rf"\b{re.escape(t)}\b")
        hits = [(eid, tag, claim)
                for (eid, tag, claim), r in zip(led.index_lines(rows), rows)
                if eid.upper() != t and pat.search(r[4].upper())]
        if not hits:
            return
        print(f"        THE LAST {min(n, len(hits))} ENTRIES THAT CITE {t} "
              f"({len(hits)} total) — EXPAND BEFORE PLANNING, NOT AFTER:")
        for eid, tag, claim in hits[:n]:
            print(f"          {eid:6} {tag[:20]:20} {claim[:88]}")
        shown = [e for e, _, _ in hits[:n]]

        # AND THE LOAD-BEARING PRIOR WORK, WHICH IS NOT THE SAME LIST (T173).
        #
        # The recency list is what a target's work looked like LAST. It is not
        # what ANSWERED it. Roll #223 re-derived A237 -- which had resolved
        # A225's central ambiguity 89 rolls earlier, in almost the same words --
        # because A237 sat at position 24 of 28 newest-first and the footer
        # showed four. **19 other entries rest on A237; it was the second most
        # load-bearing entry on that target and the least visible.**
        #
        # So rank the citers by how much OTHER work cites THEM. The entry
        # everything else leans on is the one most likely to already contain
        # the answer, and recency is uncorrelated with that.
        ids = [r[0] for r in rows]
        blob = {r[0]: (r[4] or "").upper() for r in rows}
        weight = {}
        for eid, _, _ in hits:
            pe = re.compile(rf"\b{re.escape(eid.upper())}\b")
            weight[eid] = sum(1 for o in ids
                              if o != eid and pe.search(blob.get(o, "")))
        heavy = [h for h in sorted(hits, key=lambda h: -weight[h[0]])
                 if h[0] not in shown and weight[h[0]] > 0][:2]
        if heavy:
            print(f"        MOST LOAD-BEARING PRIOR WORK ON {t} — what other entries "
                  f"REST ON, which is NOT the newest:")
            for eid, tag, claim in heavy:
                print(f"          {eid:6} [{weight[eid]:>2} rest on it] "
                      f"{tag[:16]:16} {claim[:70]}")
            shown += [e for e, _, _ in heavy]
        print(f"          scripts/ledger.py --show {' '.join(shown)}")
    except Exception as e:
        # NOT `pass`. A silent failure here means the citation list quietly
        # stops appearing and the duplication it prevents comes back with no
        # sign that anything changed -- the same signal-with-no-reader shape
        # this whole feature exists to fix. It must still never be fatal:
        # route.py has to roll even if the ledger cannot be parsed.
        print(f"        [route] could not list prior work on {target}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)


def schedule():
    """Anything due or overdue in docs/SCHEDULE.md.

    Dated side-tasks (upstreaming, triage, writeups) are the ones that quietly
    never happen -- the root-cause work needs no reminder because it is the
    default. Surfaced here because this is the tool consulted at every
    checkpoint, so a due item cannot sit unnoticed.
    """
    import datetime
    sched = ROOT / "docs" / "SCHEDULE.md"
    if not sched.exists():
        return [], []
    today = datetime.date.today().isoformat()
    due, upcoming = [], []
    for line in sched.read_text().split("\n"):
        m = re.match(r"- \[( |x)\] \*\*(\d{4}-\d{2}-\d{2})\*\* — (.*)", line)
        if not m:
            continue
        done, when, what = m.group(1) == "x", m.group(2), re.sub(r"[*`]", "", m.group(3))
        if done:
            continue
        if when <= today:
            due.append((when, what))
        else:
            upcoming.append((when, what))
    return due, upcoming[:1]


def main():
    if not LEDGER.exists():
        print("[route] no ledger", file=sys.stderr)
        return 1
    st = load()
    items = open_items()

    # An unrecognised argument must NEVER fall through to a roll. It did once
    # (2026-08-19, T37): `route.py --help` -- a flag this script does not have --
    # was silently ignored, so the script took the no-argument path and ROLLED.
    # That consumed roll #35 and discarded a pending EXPLORE from #34, which is
    # precisely the bias the roll exists to prevent (T14/T31: the roll is used
    # but under-applied). Rolling mutates .route-state.json and appends to
    # docs/route-log.md; a mutation must be the explicit case, never a fallback.
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    KNOWN = {"--status", "--history", "--uniform", "--help", "-h"}
    unknown = [a for a in sys.argv[1:] if a not in KNOWN]
    if unknown:
        print(f"[route] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print(f"[route] known flags: {', '.join(sorted(KNOWN))}", file=sys.stderr)
        print("[route] (a roll is the NO-ARGUMENT case: scripts/route.py)", file=sys.stderr)
        print("[route] REFUSING to roll — a roll must be asked for explicitly, "
              "never as a fallback for input this script did not understand.",
              file=sys.stderr)
        return 2

    if "--history" in sys.argv:
        print(LOG.read_text() if LOG.exists() else "[route] no history yet")
        return 0

    if not items:
        print("[route] nothing OPEN — nothing to route.")
        return 0

    if "--status" in sys.argv:
        print(f"[route] {len(items)} open, last roll #{st['roll']}, "
              f"entries at last roll {st['last_entry_count']} (now {entry_count()})")
        for i, (eid, body, cost) in enumerate(items):
            stale = staleness(st, eid)
            cs = f"cost={cost:<3d}" if cost is not None else "cost=?  "
            print(f"  {'CHEAPEST' if i == 0 and cost is not None else '        '} {eid:5s} "
                  f"{cs} stale={stale:2d}  {body}")
        if unpriced(items):
            print(f"  [route] UNPRICED (sorted last, not ranked): {', '.join(unpriced(items))}")
            print("          add [cost=N] to those rows or the ordering is not a ranking")
        return 0

    # THE OBSERVED RUN IS THE FIRST TASK OF THE DAY (T103, standing user policy).
    #
    # Gated HERE, on the roll, and deliberately not on all work. A roll is the
    # unit of real work -- it consumes a routing decision and commits the
    # project to a direction -- so blocking it is meaningful. Blocking
    # everything would not be: I CANNOT CLEAR THIS GATE MYSELF, it needs the
    # user's eyes and ears, so a total block stalls the whole session whenever
    # they are away, and a rule that halts all work gets deleted (T29).
    #
    # A recorded DEFERRAL clears it. The discipline is not "the run happened",
    # it is "the run was not SILENTLY SKIPPED" -- recorded either way, the same
    # rule the ledger lives by.
    _obs = LOG.parent / "observed-runs.md"
    _today = __import__("datetime").date.today().isoformat()
    _obs_text = _obs.read_text() if _obs.exists() else ""
    if not observed_today(_obs_text, _today):
        # THE USER IS AWAY: supply the deferral REASON, do not bypass the gate.
        #
        # The gate has always accepted a recorded deferral, because the rule is
        # "the run was not SILENTLY skipped", not "the run happened". So an
        # absence does not need a hole cut in it -- it needs the reason filled
        # in automatically. Every skipped day still gets a dated, reasoned line
        # in `observed-runs.md`, written ON the day, and Monday still owes
        # exactly ONE run rather than three (T151, the user's own rule).
        try:
            _sd = str(Path(__file__).resolve().parent)
            if _sd not in sys.path:
                sys.path.insert(0, _sd)
            import away as _away
            _b = _away.banner()
        except Exception:
            _b = None          # fail towards ASKING, never towards silence
        if _b:
            with _obs.open("a") as _f:
                _f.write(f"## DEFERRED {_today} — user away ({_away.status()[2]})\n"
                         f"- no observed run today; deferred deliberately, not skipped.\n\n")
            print(f"[route] {_b}", file=sys.stderr)
            print(f"[route] deferral RECORDED for {_today} — the roll proceeds.",
                  file=sys.stderr)
            _obs_text = _obs.read_text()

    if not observed_today(_obs_text, _today):
        print("[route] REFUSING TO ROLL — no user-observed run recorded today.", file=sys.stderr)
        print("        It is the FIRST task of the day (T103). I cannot do it myself:", file=sys.stderr)
        print("        I cannot hear audio at all, and scene identity has been wrong", file=sys.stderr)
        print("        twice from sampling (A93, A161).", file=sys.stderr)
        print("", file=sys.stderr)
        print("          scripts/observed_run.sh              # do it", file=sys.stderr)
        print("          scripts/observed_run.sh --defer '<reason>'   # or record why not",
              file=sys.stderr)
        print("", file=sys.stderr)
        print("        NO ROLL WAS CONSUMED. Other work is unaffected.", file=sys.stderr)
        return 3

    st["roll"] += 1
    draw = random.random()
    frontier = items[0][0]
    explore = draw < EPS and len(items) > 1

    # A DEGENERATE FRONTIER IS NOT A ROUTING RESULT, IT IS A MISSING LIST (T123).
    #
    # On 2026-08-20 six consecutive rolls "selected" the same target. The
    # machinery was working perfectly; the frontier had ONE item on it, because
    # two substantial problems had been written up as findings and never marked
    # OPEN. The user noticed, not the tool -- and nothing here said anything,
    # because picking the only candidate looks exactly like picking the best one.
    #
    # No threshold is needed for this. With one item exploration CANNOT fire at
    # all (the `len(items) > 1` above), and a second draw over a single
    # candidate reports p=1.00 -- a probability with one outcome. Both are
    # arithmetic facts about the list, not judgements about the work.
    if len(items) <= 1:
        print("[route] >>> THE FRONTIER HAS %d ITEM. Exploration cannot fire, so"
              % len(items), file=sys.stderr)
        print("[route]     every roll from here is EXPLOIT on the same target and", file=sys.stderr)
        print("[route]     the verdict carries no information. That is usually not", file=sys.stderr)
        print("[route]     'one problem left' -- it is problems recorded as findings", file=sys.stderr)
        print("[route]     and never priced as OPEN work. Check before rolling again.", file=sys.stderr)

    picks = []
    if explore:
        # Second RNG draw picks WHICH open item. Weighted by staleness: an item
        # untouched for many rolls is exactly the one whose cost estimate is
        # most likely out of date. --uniform makes it a flat draw instead.
        cands = [x for x in items if x[0] != frontier]
        if "--uniform" in sys.argv:
            weights = [1] * len(cands)
        else:
            weights = [1 + staleness(st, e) for e, _, _ in cands]
        total = sum(weights)
        pick = random.random()
        acc, target, body = 0.0, cands[-1][0], cands[-1][1]
        for (e, b, _c), w in zip(cands, weights):
            acc += w / total
            if pick <= acc:
                target, body = e, b
                break
        picks = [(e, w, w / total) for (e, _, _), w in zip(cands, weights)]
        verdict = "EXPLORE"
        if len(cands) == 1:
            # An exploration draw with one candidate. It prints p=1.00, which
            # reads like a confident weighting and is in fact no choice at all.
            print("[route] >>> THIS 'EXPLORE' HAD ONE CANDIDATE (p=1.00). Nothing was",
                  file=sys.stderr)
            print("[route]     explored -- the frontier is too small for the verdict",
                  file=sys.stderr)
            print("[route]     to mean anything. Price the open work you already know about.",
                  file=sys.stderr)
        note = ("ONE bounded check, hard budget. Record the outcome either way — "
                "'still expensive, because X' is itself a costing improvement.")
    else:
        target, body, cost = items[0]
        verdict = "EXPLOIT"
        note = ("Continue the cheapest OPEN item (cost=%s)." % cost if cost is not None
                else "WARNING: no OPEN row carries [cost=N], so this is NOT a cost "
                     "ranking -- it is document order. Price the rows before trusting it.")

    # Seed any entry we have never seen, so it ages from THIS roll rather than
    # from roll 0. Done at roll time only -- --status must not mutate state.
    for _e, _b, _c in items:
        st["last_seen"].setdefault(_e, st["roll"])
    st["last_seen"][target] = st["roll"]
    st["last_entry_count"] = entry_count()
    # ROUTABLE baseline (T155). check_ledger's "you have not rolled" nag counts
    # from THIS, not from the total, because user-directed entries were never
    # routed and never would have been -- the user chose the target. Without it
    # a day of user-directed work manufactures a routing alarm out of nothing.
    # The predicate is IMPORTED, never restated (T131/T149).
    st["last_routable_count"] = routable_entry_count()
    STATE.write_text(json.dumps(st, indent=1))

    witness = make_witness()
    line = (f"- roll #{st['roll']}: **{verdict}** (drew {draw:.3f} vs eps {EPS}) "
            f"-> `{target}` [witness `{witness}`] — {body}")
    if not LOG.exists():
        LOG.write_text("# Routing log\n\nEvery explore/exploit decision, machine-rolled.\n"
                       "A gap in the numbering means a roll was skipped.\n\n")
    with LOG.open("a") as f:
        f.write(line + "\n")

    due, upcoming = schedule()
    for when, what in due:
        tag = "OVERDUE" if when < __import__("datetime").date.today().isoformat() else "DUE TODAY"
        print(f"[sched] {tag} {when}: {what[:100]}")
    for when, what in upcoming:
        print(f"[sched] next    {when}: {what[:100]}")
    if due:
        print("        (scheduled work comes first — the roll below covers the"
              " root-cause investigation)")

    print(OPENING_REQUIREMENT)
    print(f"[route] roll #{st['roll']} — {verdict}  (drew {draw:.3f}, eps {EPS})")
    print(f"        WITNESS: {witness}   <-- quote this in the announcement and in")
    print(f"                 the checkpoint's ledger entry. It is random, so it")
    print(f"                 cannot be written before this line existed.")
    print(f"        target: {target} — {body}")
    print(f"        {note}")
    _print_recent_work_on(target)
    if explore:
        print(f"        chosen by a second draw over the frontier {frontier}:")
        for e, w, p in picks:
            mark = "<-- picked" if e == target else ""
            print(f"          {e:5s} weight {w:2d}  p={p:.2f} {mark}")
    print(CLOSING_REQUIREMENT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
