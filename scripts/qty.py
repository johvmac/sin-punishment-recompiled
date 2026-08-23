#!/usr/bin/env python3
"""The quantities this project keeps stating from memory. Measure, don't recall.

WHY THIS EXISTS (T177)
----------------------
On 2026-08-23 the user caught me describing something FOUR DAYS OLD as "months
of checkpoints ago", twice, unhedged — on a project ten days old. Nothing in the
apparatus could have caught it: every ledger entry carries a FALSIFIER, which
says what would prove a claim wrong, but a claim about elapsed time is not the
kind of thing a falsifier is aimed at.

The cause was not ignorance. 554 entries, 230 rolls, 515 commits and ~12,000
lines of tooling FEEL like months, and I substituted the felt duration for the
measured one. That is the same substitution as quoting "GAME 9 / STACK 5" from
memory when recomputing gives 7:5 with two entries contested (A371).

THE RULE THIS SERVES, and it is deliberately smaller than the calibration
ledger it replaces: **a claim about a quantity gets the quantity MEASURED at the
moment it is stated.** Not recalled from an earlier entry, not estimated from a
feeling of how much has happened.

So this removes the excuse. Every number below is one command away, which means
stating it from memory is now a choice rather than a convenience.

`check_ledger.py` carries the other half — it flags vague duration language
about the project's own history and points here.

Usage:
    scripts/qty.py                     # everything, one screen
    scripts/qty.py age                 # how old is this project, really
    scripts/qty.py since A179          # how long ago was that entry, in days AND rolls
    scripts/qty.py between A92 A365    # elapsed between two entries
    scripts/qty.py counts              # entries by family, rolls, commits
    scripts/qty.py --self-check
"""
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"
ROUTELOG = ROOT / "docs" / "route-log.md"

DATE_RE = re.compile(r"20\d\d-\d\d-\d\d")
ROW_RE = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|")


def _today():
    return date.today()


def entry_dates(text=None):
    """{id: earliest date mentioned in its row}. The row's own date, not today's."""
    t = text if text is not None else LEDGER.read_text()
    out, skipping = {}, False
    for line in t.split("\n"):
        if line.startswith("## "):
            skipping = "USER QUEUE" in line.upper()
            continue
        if skipping:
            continue
        m = ROW_RE.match(line)
        if not m or m.group(1) in out:
            continue
        ds = DATE_RE.findall(line)
        if ds:
            out[m.group(1)] = min(ds)
    return out


def all_dates(text=None):
    t = text if text is not None else LEDGER.read_text()
    return sorted(set(DATE_RE.findall(t)))


def rolls(text=None):
    """(latest roll number, {entry: the roll that PRODUCED it}).

    The producing roll is read from the ENTRY'S OWN ROW ("Roll #99, EXPLORE..."),
    not from the route log. A first version matched the route log's `roll #N ->
    TARGET` and was answering a different question: the log records which item a
    roll was AIMED at, and the entry a roll produces is usually not that item.
    """
    latest = 0
    if ROUTELOG.exists():
        for line in ROUTELOG.read_text().split("\n"):
            m = re.search(r"roll #(\d+)", line)
            if m:
                latest = max(latest, int(m.group(1)))
    per, skipping = {}, False
    t = text if text is not None else LEDGER.read_text()
    for line in t.split("\n"):
        if line.startswith("## "):
            skipping = "USER QUEUE" in line.upper()
            continue
        if skipping:
            continue
        m = ROW_RE.match(line)
        if not m or m.group(1) in per:
            continue
        r = re.search(r"[Rr]oll #(\d+)", line)
        if r:
            per[m.group(1)] = int(r.group(1))
    return latest, per


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return ""


def cmd_age():
    ds = all_dates()
    first_commit = git("log", "--reverse", "--format=%ad", "--date=short").split("\n")[0]
    t = _today()
    print("PROJECT AGE — state this, never a feeling about it")
    if ds:
        d0 = date.fromisoformat(ds[0])
        print(f"  earliest ledger date : {ds[0]}   ({(t - d0).days} days ago)")
    if first_commit:
        c0 = date.fromisoformat(first_commit)
        print(f"  first commit         : {first_commit}   ({(t - c0).days} days ago)")
    print(f"  today                : {t.isoformat()}")
    print()
    print("  If you are about to write 'months', check this number first (T177).")
    return 0


def cmd_since(eid):
    eid = eid.upper()
    ed, (latest, per) = entry_dates(), rolls()
    if eid not in ed:
        print(f"[qty] no dated row for {eid}", file=sys.stderr)
        return 2
    d0 = date.fromisoformat(ed[eid])
    days = (_today() - d0).days
    print(f"{eid} — dated {ed[eid]}")
    print(f"  {days} day(s) ago")
    if eid in per:
        print(f"  roll #{per[eid]} of {latest}  ({latest - per[eid]} rolls since)"
              f"   [APPROXIMATE — first roll number in the row; a correction prefix"
              f" can put a LATER entry's roll first. The day count above is exact.]")
    print()
    print(f"  DAYS and ROLLS diverge here by design: this project does many rolls")
    print(f"  per day, so 'a long time ago' in rolls is often days in wall-clock.")
    return 0


def cmd_between(a, b):
    ed = entry_dates()
    a, b = a.upper(), b.upper()
    for e in (a, b):
        if e not in ed:
            print(f"[qty] no dated row for {e}", file=sys.stderr)
            return 2
    da, db = date.fromisoformat(ed[a]), date.fromisoformat(ed[b])
    print(f"{a} ({ed[a]})  ->  {b} ({ed[b]})   =  {abs((db - da).days)} day(s)")
    return 0


def cmd_counts():
    from collections import Counter
    c, skipping = Counter(), False
    for line in LEDGER.read_text().split("\n"):
        if line.startswith("## "):
            skipping = "USER QUEUE" in line.upper()
            continue
        if skipping:
            continue
        m = ROW_RE.match(line)
        if m:
            c[re.match(r"[A-Z]+", m.group(1)).group(0)] += 1
    latest, _ = rolls()
    print("COUNTS")
    print("  entries by family : " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    print(f"  total entries     : {sum(c.values())}")
    print(f"  latest roll       : #{latest}")
    print(f"  commits           : {git('rev-list', '--count', 'HEAD')}")
    return 0


def self_check():
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    syn = ("| A1 | MEASURED | body | 2026-08-13 |\n"
           "| A2 | MEASURED | body | 2026-08-19 |\n"
           "## THE USER QUEUE\n"
           "| U1 | LIVE 2026-08-01 | queue row |\n")
    ed = entry_dates(syn)
    chk("reads each row's OWN date", ed.get("A1") == "2026-08-13" and ed.get("A2") == "2026-08-19",
        f"got {ed}")
    chk("excludes user-queue rows", "U1" not in ed, "a queue row counted as an entry")
    chk("takes the EARLIEST date in a row, not the last",
        entry_dates("| A9 | s | later 2026-08-22 | 2026-08-13 |\n").get("A9") == "2026-08-13",
        "a row citing two dates would report the wrong one")

    _, per = rolls("| A9 | MEASURED | Roll #99, EXPLORE (drew 0.1) | 2026-08-19 |\n")
    chk("reads the PRODUCING roll from the entry's own row", per.get("A9") == 99,
        f"got {per.get('A9')} — the route log records a roll's TARGET, a different question")

    # THE CONTROL THAT MATTERS: the real ledger must NOT look months old. This
    # is the exact claim that was got wrong, asserted against live data.
    ds = all_dates()
    span = (date.fromisoformat(ds[-1]) - date.fromisoformat(ds[0])).days
    chk(f"the real ledger spans {span} days, which is under 60",
        span < 60, f"{span} days — if this ever legitimately exceeds 60, update the control")
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
        print(f"would read {LEDGER}, {ROUTELOG} and `git log`; writes nothing")
        return 0
    if not a:
        cmd_age(); print(); cmd_counts()
        return 0
    if a[0] == "age":
        return cmd_age()
    if a[0] == "counts":
        return cmd_counts()
    if a[0] == "since" and len(a) > 1:
        return cmd_since(a[1])
    if a[0] == "between" and len(a) > 2:
        return cmd_between(a[1], a[2])
    print(f"[qty] unknown command {' '.join(a)!r} — see --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
