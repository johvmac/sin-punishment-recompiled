#!/usr/bin/env python3
"""Ideas raised and NOT acted on. Recorded immediately, swept deliberately.

WHY THIS EXISTS (T181, T182)
----------------------------
Three things from one week's conversations reached no file at all: a reading
list the user asked for, the calibration idea, and two sub-agent sweeps that had
been scoped and cleared. The pattern was exact and it is not about caution:

**Everything unrecorded was something I SAID, not something a tool produced.**

Tool output lands in the ledger because the workflow puts it there — a run
writes a log, a script writes a file, an entry gets committed. A remark in
conversation has no such path. So it evaporates, and the user's standing rule —
"memories don't work in the long term, all important info has to go somewhere
properly" — gets broken by omission rather than by decision.

THE STANDING PERMISSION THIS IMPLEMENTS (user, 2026-08-23)
----------------------------------------------------------
**Any idea raised gets written here immediately, without asking.** Recording is
cheap, reversible and has no downside. ACTING still goes through the roll for
project work, or an explicit ask for anything expensive or irreversible — that
distinction is the point, and this file is what makes it safe to keep.

NOT THE BACKLOG, AND THE DIFFERENCE MATTERS
-------------------------------------------
`backlog.py` holds SMALL OWED JOBS and refuses anything that cannot say why it
is owed — deliberately, so it cannot become a wish-list. An idea is not owed.
Putting ideas there would break the one property that makes the backlog usable.

WHY IT IS NOT A DAILY TASK
--------------------------
The user's own objection, and it is right: this project already carries enough
recurring work, and adding a daily sweep would add to the mass rather than help.
So it fires **on a THRESHOLD and then goes quiet** — the shape `calib.py --due`
uses. A nag that fires every day is skimmed; T118 measured a 6-of-7 noise rate
on exactly that failure.

Usage:
    scripts/ideas.py                       # open ideas
    scripts/ideas.py --all
    scripts/ideas.py add "<idea>" "<why it was not acted on>"
    scripts/ideas.py close IDEA3 "<what was decided or done>"
    scripts/ideas.py --due                 # is a sweep worth it yet
    scripts/ideas.py --mark-read
    scripts/ideas.py --self-check
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDEAS = ROOT / "docs" / "IDEAS.md"
STATE = ROOT / "docs" / ".ideas-state.json"

# `IDEA<n>`, NOT `I<n>`. The ledger already has an I family, and BL had to be
# renamed a day after it was built for exactly this collision (T175).
ROW = re.compile(r"^\|\s*(IDEA\d+)\s*\|\s*([\d-]+)\s*\|\s*(\S[^|]*?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")

DUE_OPEN = 6        # a sweep is worth setting up for this many
DUE_GROWTH = 4      # re-fire only after this much growth


def rows(text=None):
    t = text if text is not None else (IDEAS.read_text() if IDEAS.exists() else "")
    out = []
    for line in t.split("\n"):
        m = ROW.match(line)
        if m and m.group(1) != "id":
            out.append(dict(id=m.group(1), raised=m.group(2), status=m.group(3),
                            idea=m.group(4), why=m.group(5)))
    return out


def is_open(r):
    return r["status"].strip().upper().startswith("OPEN")


def _state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"last_read_at": 0}


def due(text=None):
    """(is_due, n_open, reason)."""
    n = sum(1 for r in rows(text) if is_open(r))
    last = _state().get("last_read_at", 0)
    if n < DUE_OPEN:
        return False, n, f"{n} open, a sweep is worth it at {DUE_OPEN}"
    if n < last + DUE_GROWTH:
        return False, n, f"swept at {last} open, only {n - last} new since"
    return True, n, f"{n} ideas raised and never addressed"


def cmd_list(show_all):
    rs = rows()
    shown = rs if show_all else [r for r in rs if is_open(r)]
    if not shown:
        print("[ideas] none open." if not show_all else "[ideas] empty.")
        return 0
    for r in shown:
        print(f"  {r['id']:<7} {r['status']:<18} {r['idea']}")
        print(f"          not acted on because: {r['why']}")
    print(f"[ideas] {sum(1 for r in rs if is_open(r))} open, {len(rs)} total.")
    return 0


def _next_id(rs):
    return f"IDEA{max([int(r['id'][4:]) for r in rs], default=0) + 1}"


def cmd_add(idea, why, dry):
    idea, why = (idea or "").strip(), (why or "").strip()
    if len(idea) < 10:
        print("[ideas] REFUSING: say what the idea IS.", file=sys.stderr)
        return 2
    # The honest half. An idea with no stated reason for inaction is one that was
    # simply forgotten, and this file exists because forgetting is the failure.
    if len(why) < 10:
        print("[ideas] REFUSING: say WHY IT WAS NOT ACTED ON — needs a roll, needs "
              "the user, too expensive, superseded, or just unexamined. That reason "
              "is what a later sweep actually reads (T182).", file=sys.stderr)
        return 2
    rs = rows()
    new = f"| {_next_id(rs)} | {date.today().isoformat()} | OPEN | {idea} | {why} |"
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(new)
        return 0
    if not IDEAS.exists():
        IDEAS.write_text(
            "# Ideas raised and not acted on\n\n"
            "**Written by `scripts/ideas.py`. Recording is automatic and needs no\n"
            "permission; ACTING still goes through the roll or an explicit ask.**\n\n"
            "Not the backlog: that holds small OWED jobs and refuses anything that\n"
            "cannot say why it is owed. An idea is not owed.\n\n"
            "| id | raised | status | idea | why it was not acted on |\n"
            "|---|---|---|---|---|\n")
    IDEAS.write_text(IDEAS.read_text().rstrip("\n") + "\n" + new + "\n")
    print(f"[ideas] added {_next_id(rs)}")
    return 0


def cmd_close(iid, what, dry):
    t = IDEAS.read_text() if IDEAS.exists() else ""
    hit = [r for r in rows(t) if r["id"] == iid.upper()]
    if not hit:
        print(f"[ideas] REFUSING: no such idea {iid}.", file=sys.stderr)
        return 2
    if not is_open(hit[0]):
        print(f"[ideas] {iid} is already closed.", file=sys.stderr)
        return 2
    if len((what or "").strip()) < 10:
        print("[ideas] REFUSING: say what was DECIDED. 'Dropped' is a fine outcome "
              "and still needs a reason — an idea closed silently is one nobody can "
              "tell was considered.", file=sys.stderr)
        return 2
    old = f"| {hit[0]['id']} | {hit[0]['raised']} | {hit[0]['status']} |"
    new = f"| {hit[0]['id']} | {hit[0]['raised']} | CLOSED {date.today().isoformat()}: {what.strip()} |"
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(new)
        return 0
    IDEAS.write_text(t.replace(old, new, 1))
    print(f"[ideas] closed {iid}")
    return 0


def cmd_due():
    d, n, why = due()
    print(f"{'DUE' if d else 'not due'} — {why}")
    if d:
        print("  scripts/ideas.py              # read them")
        print("  scripts/ideas.py close IDEAn '<what was decided>'")
        print("  scripts/ideas.py --mark-read  # then quiet until it grows")
    return 0 if d else 1


def cmd_mark_read():
    n = sum(1 for r in rows() if is_open(r))
    STATE.write_text(json.dumps({"last_read_at": n}, indent=1) + "\n")
    print(f"[ideas] marked swept at {n} open; quiet until {n + DUE_GROWTH}.")
    return 0


def self_check():
    import tempfile
    global IDEAS, STATE
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    _i, _s = IDEAS, STATE
    try:
        with tempfile.TemporaryDirectory() as td:
            IDEAS = Path(td) / "IDEAS.md"
            STATE = Path(td) / "s.json"
            hdr = ("| id | raised | status | idea | why it was not acted on |\n"
                   "|---|---|---|---|---|\n")
            IDEAS.write_text(hdr)

            chk("add REFUSES an idea with no stated reason for inaction",
                cmd_add("a perfectly good idea here", "", False) == 2,
                "an idea with no reason is one that was simply forgotten")
            chk("add ACCEPTS one that gives the reason",
                cmd_add("a perfectly good idea here", "needs a roll to select it", False) == 0)
            chk("close REFUSES without saying what was decided",
                cmd_close("IDEA1", "", False) == 2,
                "an idea closed silently cannot be told from one never considered")
            chk("close ACCEPTS with a decision", cmd_close("IDEA1", "dropped: too expensive", False) == 0)
            chk("close REFUSES an already-closed idea",
                cmd_close("IDEA1", "again for some reason", False) == 2)

            # THE THRESHOLD, four directions -- same shape as calib's due flag.
            IDEAS.write_text(hdr + "".join(
                f"| IDEA{i} | 2026-01-01 | OPEN | idea number {i} | not yet examined |\n"
                for i in range(1, 4)))
            chk("NOT due below the threshold", not due()[0], "nags on a handful")
            IDEAS.write_text(hdr + "".join(
                f"| IDEA{i} | 2026-01-01 | OPEN | idea number {i} | not yet examined |\n"
                for i in range(1, 8)))
            chk("DUE once enough have piled up", due()[0], f"{due()}")
            STATE.write_text(json.dumps({"last_read_at": 7}))
            chk("SILENT again once swept", not due()[0], "keeps nagging after a sweep")
            IDEAS.write_text(hdr + "".join(
                f"| IDEA{i} | 2026-01-01 | OPEN | idea number {i} | not yet examined |\n"
                for i in range(1, 13)))
            chk("DUE again after real growth", due()[0], "never fires again after one sweep")
    finally:
        IDEAS, STATE = _i, _s

    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    dry = "--dry-run" in a
    a = [x for x in a if x != "--dry-run"]
    if "--due" in a:
        return cmd_due()
    if "--mark-read" in a:
        return cmd_mark_read()
    if not a:
        return cmd_list(False)
    if a[0] == "--all":
        return cmd_list(True)
    if a[0] == "add":
        return cmd_add(a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else "", dry)
    if a[0] == "close":
        return cmd_close(a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else "", dry)
    print(f"[ideas] unknown command {a[0]!r} — see --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
