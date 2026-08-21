#!/usr/bin/env python3
"""Read THE USER QUEUE out of the ledger, and nag when it is worth a sitting.

WHY THIS EXISTS (T131)
----------------------
Several open items can only be advanced by the user at a real display: the RT64
inspector needs F1, which does nothing under Xvfb or Xephyr (A245), and naming
what a texture IS is recognition work that belongs to a person (A227's split).

Each of those needs a launch, a real screen, and the user present. Run them one
at a time and that setup cost is paid over and over; batched, one sitting clears
several. **The queue exists to make the sweep worth doing.**

THE FAILURE IT MUST NOT BECOME
------------------------------
T122: two confirmed problems were written up as findings and never marked open,
so the router offered a single candidate for five consecutive rolls while they
sat there. **A queue nothing forces you to empty is a way of feeling like you
dealt with something.** The alarm is the load-bearing half.

WHY THE ALARM COUNTS ITEMS AND NOT "CHECKPOINTS THAT POINTED AT F1"
-------------------------------------------------------------------
That was the shape first proposed, and it needs a judgement: did this checkpoint
"point at" the inspector? `route.py`'s own history says a checker built on that
kind of threshold trains skimming -- T118 measured a 6-of-7 noise rate, and T122
recorded exactly this class as debt rather than mechanise it badly.

So BLOCKED counts distinct ledger entries the live items CITE. An entry is in
that count only because an item explicitly names it, so the count is exact and
no judgement is involved. It is the same signal, made countable.

IT IS A REMINDER, NEVER A GATE (T127)
-------------------------------------
Nothing here refuses a roll. I cannot clear a single item myself, and a block
only the user can lift would halt all work while they are away. T127 is the
entry where I reported a reminder as a hard gate and sent the user to watch a
run nothing required; this does not repeat it.

**It does not forget** (T120): there is no high-water mark, so it keeps firing
every run until the queue is actually swept. A reminder that reports itself once
is a reminder you can lose.

    scripts/user_queue.py                 # the queue + the alarm
    scripts/user_queue.py --check         # cross-references resolve
    scripts/user_queue.py --dry-run       # what it would report, no side effects
    scripts/user_queue.py --self-check    # controls, incl. ones verified to FAIL
"""
import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"

SECTION = "## THE USER QUEUE"
GROUP_RE = re.compile(r"^### Queue:\s*(.+?)\s*$")
ROW_RE = re.compile(r"^\|\s*(U\d+)\s*\|(.*)$")
ID_RE = re.compile(r"\b([AT]\d+)\b")
# status cell: LIVE <date> | SWEPT <date> -> <ID> | DROPPED <date> (<reason>)
STATUS_RE = re.compile(r"^\**(LIVE|SWEPT|DROPPED)\**\s+(\d{4}-\d{2}-\d{2})(.*)$", re.I)

# Printed, never hidden -- they are arguable and a reader must be able to argue.
T_DEPTH, T_AGE_DAYS, T_BLOCKED = 3, 2, 3


def parse(text):
    """Return (items, groups). Each item: id, group, status, date, tail, serves."""
    items, group, inside = [], None, False
    for line in text.split("\n"):
        if line.startswith("## "):
            inside = line.startswith(SECTION)
            group = None
            continue
        if not inside:
            continue
        g = GROUP_RE.match(line)
        if g:
            group = g.group(1)
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).strip().strip("|").split("|")]
        if not cells:
            continue
        sm = STATUS_RE.match(cells[0])
        status, date, tail = (sm.group(1).upper(), sm.group(2), sm.group(3).strip()) \
            if sm else ("MALFORMED", None, cells[0])
        serves = ID_RE.findall(cells[-1]) if len(cells) > 1 else []
        # Column counts vary because bodies contain pipes -- same hazard
        # ledger.py's parse() documents. First cell is status, LAST is serves,
        # everything between is prose. A fixed split silently drops content.
        items.append({"id": m.group(1), "group": group, "status": status,
                      "date": date, "tail": tail, "serves": serves,
                      "what": cells[1] if len(cells) > 2 else "",
                      "prose": " ".join(cells[1:-1]) if len(cells) > 2 else ""})
    return items


def ledger_ids(text):
    from check_ledger import is_non_entry_section
    ids, skip = set(), False
    for line in text.split("\n"):
        if line.startswith("## "):
            skip = is_non_entry_section(line)
        if skip:
            continue
        m = re.match(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|", line)
        if m:
            ids.add(m.group(1))
    return ids


def check(items, ids):
    """Cross-references must resolve. Returns a list of problem strings.

    A dangling ID is the usual way a cross-reference rots, and an unchecked
    `SERVES` is decoration. **A SWEPT item must name the entry recording its
    result** -- an item is not done when the observation is made, it is done
    when an entry records it. Otherwise this becomes A227: data gathered,
    nothing resolved.
    """
    # T131: excluding this section from ledger parsing ALSO excluded it from the
    # prose checks, which had legitimately flagged two of these very items for
    # unscoped absences. That is coverage I removed, so it is restored here
    # rather than silently enjoyed -- the scope rule applies to "what the answer
    # would mean" just as much as to a finding, since that IS a claim.
    try:
        from check_ledger import NEGATIVE, SCOPE
    except ImportError:            # pragma: no cover
        NEGATIVE = SCOPE = None

    bad = []
    for it in items:
        if NEGATIVE is not None:
            prose = f"{it['prose']} {it['tail']}"
            if NEGATIVE.search(prose) and not SCOPE.search(prose):
                bad.append(f"{it['id']}: asserts an absence with no stated scope. "
                           f"Say WHERE the user should have looked, inside the claim.")
        if it["status"] == "MALFORMED":
            bad.append(f"{it['id']}: status is not LIVE/SWEPT/DROPPED + a date — {it['tail'][:48]!r}")
            continue
        for sid in it["serves"]:
            if sid not in ids:
                bad.append(f"{it['id']}: SERVES {sid}, which is not in the ledger")
        if not it["serves"] and it["status"] == "LIVE":
            bad.append(f"{it['id']}: LIVE but serves no entry — nothing would be updated by doing it")
        if it["status"] == "SWEPT":
            res = ID_RE.findall(it["tail"])
            if not res:
                bad.append(f"{it['id']}: SWEPT but names no entry recording the result")
            else:
                for r in res:
                    if r not in ids:
                        bad.append(f"{it['id']}: SWEPT -> {r}, which is not in the ledger")
    return bad


def alarm(items, today):
    """The three counts. None of them needs a judgement."""
    live = [i for i in items if i["status"] == "LIVE"]
    depth = len(live)
    dates = [datetime.date.fromisoformat(i["date"]) for i in live if i["date"]]
    age = max((today - d).days for d in dates) if dates else 0
    blocked = sorted({s for i in live for s in i["serves"]})
    fired = []
    if depth >= T_DEPTH:
        fired.append(f"DEPTH {depth} >= {T_DEPTH} — a sitting now clears more than it costs to set up")
    if age >= T_AGE_DAYS:
        fired.append(f"AGE {age}d >= {T_AGE_DAYS}d — the oldest live item is starving")
    if len(blocked) >= T_BLOCKED:
        fired.append(f"BLOCKED {len(blocked)} >= {T_BLOCKED} entries waiting on this: {', '.join(blocked)}")
    return live, depth, age, blocked, fired


def report(text, today, quiet=False):
    items = parse(text)
    ids = ledger_ids(text)
    live, depth, age, blocked, fired = alarm(items, today)
    problems = check(items, ids)
    if not quiet:
        by_group = {}
        for i in live:
            by_group.setdefault(i["group"] or "(ungrouped)", []).append(i)
        for g, its in by_group.items():
            print(f"\n[queue] {g}")
            for i in its:
                print(f"[queue]   {i['id']}  queued {i['date']}  serves {', '.join(i['serves']) or '—'}")
                print(f"[queue]        {i['what'][:150]}")
        print(f"\n[queue] DEPTH {depth} (threshold {T_DEPTH}) | "
              f"AGE {age}d (threshold {T_AGE_DAYS}d) | "
              f"BLOCKED {len(blocked)} (threshold {T_BLOCKED})")
        for f in fired:
            print(f"[queue] ALARM — {f}")
        if fired:
            print("[queue] This is a REMINDER, not a gate (T127) — nothing here refuses a roll.")
            print("[queue] It does not forget: it fires every run until the queue is swept (T120).")
        for p in problems:
            print(f"[queue] BROKEN CROSS-REF — {p}")
    return fired, problems


def self_check():
    checks = []

    def chk(name, ok, detail):
        checks.append((name, ok, detail))

    today = datetime.date(2026, 8, 21)
    good = (
        f"{SECTION} — x\n"
        "### Queue: F1\n"
        "| id | status | do this | means | serves |\n"
        "| U1 | LIVE 2026-08-19 | press F1 | it opens | A219, A235 |\n"
        "| U2 | LIVE 2026-08-21 | step slider | copies appear | A218 |\n"
        "| U3 | SWEPT 2026-08-20 -> A247 | done | — | A219 |\n"
        "## Other\n"
        "| A218 | OPEN | x | y |\n| A219 | OPEN | x | y |\n"
        "| A235 | MEASURED | x | y |\n| A247 | MEASURED | x | y |\n"
    )
    items = parse(good)
    chk("parses items and ignores rows outside the section",
        [i["id"] for i in items] == ["U1", "U2", "U3"], f"got {[i['id'] for i in items]}")
    live, depth, age, blocked, fired = alarm(items, today)
    chk("SWEPT items are not counted as live", depth == 2, f"depth={depth}")
    chk("AGE is measured from the OLDEST live item", age == 2, f"age={age}d, want 2")
    chk("BLOCKED counts DISTINCT entries across items", len(blocked) == 3,
        f"{blocked}")
    chk("cross-references that all resolve produce NO problems",
        check(items, ledger_ids(good)) == [], str(check(items, ledger_ids(good))))

    # DISCRIMINATING: a dangling SERVES must be REPORTED. Without this the
    # cross-reference is decoration -- it would "pass" against any text at all.
    bad = good.replace("A219, A235", "A219, A999")
    probs = check(parse(bad), ledger_ids(bad))
    chk("a SERVES pointing at a NONEXISTENT entry is REPORTED",
        any("A999" in p for p in probs), f"{probs}")

    # DISCRIMINATING: a swept item that records nothing must be REPORTED --
    # that is the A227 failure (data gathered, nothing resolved) in one line.
    bad2 = good.replace("SWEPT 2026-08-20 -> A247", "SWEPT 2026-08-20")
    probs2 = check(parse(bad2), ledger_ids(bad2))
    chk("a SWEPT item naming NO result entry is REPORTED",
        any("names no entry" in p for p in probs2), f"{probs2}")

    # DISCRIMINATING: an alarm that always fires is not an alarm. A one-item,
    # same-day queue must be SILENT.
    quiet_q = (f"{SECTION} — x\n### Queue: F1\n"
               "| U1 | LIVE 2026-08-21 | x | y | A218 |\n"
               "## Other\n| A218 | OPEN | x | y |\n")
    _, _, _, _, qf = alarm(parse(quiet_q), today)
    chk("a small, fresh queue raises NO alarm (else it always fires)",
        qf == [], f"{qf}")
    chk("a deep, stale queue DOES raise the alarm", len(fired) >= 2,
        f"{len(fired)} fired: {[f.split(' ')[0] for f in fired]}")

    # DISCRIMINATING: the scope rule must still bite in here. Excluding this
    # section from ledger parsing removed it from the prose checks that had
    # already flagged two real items, so this is restored coverage, not new.
    bad4 = good.replace("| U2 | LIVE 2026-08-21 | step slider | copies appear |",
                        "| U2 | LIVE 2026-08-21 | step slider | nothing is drawn twice |")
    probs4 = check(parse(bad4), ledger_ids(bad4))
    chk("an UNSCOPED absence in an item is REPORTED (restored coverage)",
        any("no stated scope" in p and "U2" in p for p in probs4), f"{probs4}")
    chk("a SCOPED absence in an item is NOT reported (else it always fires)",
        not any("no stated scope" in p for p in
                check(parse(good.replace("copies appear",
                                         "nothing in the truncated frame is drawn twice")),
                      ledger_ids(good))),
        "'nothing in <scope>' must pass")

    # DISCRIMINATING: a malformed status must be caught, not silently skipped.
    bad3 = good.replace("LIVE 2026-08-19", "sometime soon")
    chk("a status with no date is REPORTED, not silently dropped",
        any("MALFORMED" in i["status"] for i in parse(bad3)), "status must not parse")

    n_bad = 0
    for name, ok, detail in checks:
        n_bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:62} — {detail}")
    print(f"\n{len(checks)-n_bad}/{len(checks)} controls pass")
    return 1 if n_bad else 0


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    if a.help:
        print(__doc__)
        return 0
    if a.self_check:
        return self_check()
    if not LEDGER.exists():
        print(f"[queue] ledger not found: {LEDGER}", file=sys.stderr)
        return 2
    text = LEDGER.read_text()
    if a.dry_run:
        items = parse(text)
        live = [i for i in items if i["status"] == "LIVE"]
        print(f"[queue] --dry-run: {len(items)} item(s), {len(live)} live, "
              f"{len({s for i in live for s in i['serves']})} entries cited. "
              f"Would print the queue and up to 3 alarm lines. No side effects.")
        return 0
    fired, problems = report(text, datetime.date.today(), quiet=a.quiet)
    if a.check:
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
