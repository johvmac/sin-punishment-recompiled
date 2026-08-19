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
    for line in LEDGER.read_text().split("\n"):
        m = re.match(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|", line)
        if m and "OPEN" in m.group(2).upper():
            raw = m.group(3)
            # the marker may sit in the status cell (`| A18 | OPEN [cost=2] |`)
            # or in the body; accept either
            c = COST_RE.search(m.group(2)) or COST_RE.search(raw)
            cost = int(c.group(1)) if c else None
            body = re.sub(r"[*`~]", "", COST_RE.sub("", raw)).strip()
            items.append((m.group(1), body[:96], cost))
    # None sorts last; ties keep file order (sort is stable)
    items.sort(key=lambda x: (x[2] is None, x[2] if x[2] is not None else 0))
    return items


def unpriced(items):
    return [e for e, _, c in items if c is None]


def entry_count():
    return len(re.findall(r"^\|\s*[A-Z]+\d+[a-z]?\s*\|", LEDGER.read_text(), re.M))


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"roll": 0, "last_entry_count": 0, "last_seen": {}}


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
            stale = st["roll"] - st["last_seen"].get(eid, 0)
            cs = f"cost={cost:<3d}" if cost is not None else "cost=?  "
            print(f"  {'CHEAPEST' if i == 0 and cost is not None else '        '} {eid:5s} "
                  f"{cs} stale={stale:2d}  {body}")
        if unpriced(items):
            print(f"  [route] UNPRICED (sorted last, not ranked): {', '.join(unpriced(items))}")
            print("          add [cost=N] to those rows or the ordering is not a ranking")
        return 0

    st["roll"] += 1
    draw = random.random()
    frontier = items[0][0]
    explore = draw < EPS and len(items) > 1

    picks = []
    if explore:
        # Second RNG draw picks WHICH open item. Weighted by staleness: an item
        # untouched for many rolls is exactly the one whose cost estimate is
        # most likely out of date. --uniform makes it a flat draw instead.
        cands = [x for x in items if x[0] != frontier]
        if "--uniform" in sys.argv:
            weights = [1] * len(cands)
        else:
            weights = [1 + (st["roll"] - st["last_seen"].get(e, 0)) for e, _, _ in cands]
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
        note = ("ONE bounded check, hard budget. Record the outcome either way — "
                "'still expensive, because X' is itself a costing improvement.")
    else:
        target, body, cost = items[0]
        verdict = "EXPLOIT"
        note = ("Continue the cheapest OPEN item (cost=%s)." % cost if cost is not None
                else "WARNING: no OPEN row carries [cost=N], so this is NOT a cost "
                     "ranking -- it is document order. Price the rows before trusting it.")

    st["last_seen"][target] = st["roll"]
    st["last_entry_count"] = entry_count()
    STATE.write_text(json.dumps(st, indent=1))

    line = (f"- roll #{st['roll']}: **{verdict}** (drew {draw:.3f} vs eps {EPS}) "
            f"-> `{target}` — {body}")
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

    print(f"[route] roll #{st['roll']} — {verdict}  (drew {draw:.3f}, eps {EPS})")
    print(f"        target: {target} — {body}")
    print(f"        {note}")
    if explore:
        print(f"        chosen by a second draw over the frontier {frontier}:")
        for e, w, p in picks:
            mark = "<-- picked" if e == target else ""
            print(f"          {e:5s} weight {w:2d}  p={p:.2f} {mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
