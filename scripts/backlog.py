#!/usr/bin/env python3
"""The small-jobs backlog: what to do with leftover time, and nothing else.

WHY THIS EXISTS (T161/T162)
---------------------------
Three timed sessions on 2026-08-22 closed early -- 21m36s, 21m22s and 17m27s of
30m -- and the USER had to point it out. The reasoning error each time was
asking "does the BIGGEST pending item fit?" and stopping when it did not. The
`status` checkpoint counter catches the STOP; this gives the stop somewhere to
GO. It was the user's suggestion, and so was the warning that came with it:

    "or would that be counterintuitive"

THE RISK, WHICH IS REAL AND DESIGNED AGAINST
--------------------------------------------
**A backlog of tidy jobs is an excellent way to LOOK BUSY while avoiding the
expensive question.** This project already names that failure -- `route.py`
permits the closing sentence "nothing moved forward, I fixed a measuring
instrument" precisely so such a session cannot disguise itself. So:

  * **FRONTIER FIRST.** `next` REFUSES to hand out a job while a full checkpoint
    still fits. It is not a menu; it is what is left when rolling is not an
    option.
  * **OWED, NEVER INVENTED.** Every item names why it is already owed.
  * **DRAINABLE.** Items must be verifiably done or not done.

THE CONTROL THAT DISCRIMINATES
------------------------------
**A backlog that never empties and a backlog that is never consulted are BOTH
failures, and both are countable.** `--check` reports items added against items
closed and the age of the oldest open one. Growth with no closures means a
wish-list; no closures at all means the mechanism is decoration. Neither is
visible by reading the file.

Usage:
    scripts/backlog.py                      # list open items
    scripts/backlog.py --all                # include closed
    scripts/backlog.py next <minutes-left>  # a job, IF a checkpoint no longer fits
    scripts/backlog.py add "<job>" "<why it is owed>"
    scripts/backlog.py close BL3
    scripts/backlog.py --check              # the added-vs-closed control
    scripts/backlog.py --dry-run add ...    # print what it would write, change nothing
    scripts/backlog.py --self-check
"""
import re
import sys
from datetime import date
from pathlib import Path

# IDs ARE `BL<n>`, NOT `B<n>` (T171). The ledger already has a B family, and
# backlog B3/B6 collided with ledger B3/B6 -- both existed, meaning different
# things, so a bare "B3" was genuinely ambiguous. Caught by check_ledger's
# citation checker one day after this tool was built. Do not "simplify" it back.
ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs" / "BACKLOG.md"

# One checkpoint on this project, measured over six consecutive zero-run rolls
# on 2026-08-22 (17m27s / 6 = 2.9 min). Kept identical to session.py's CHECKPOINT
# so the two cannot disagree about when rolling is still possible.
CHECKPOINT_SECS = 3 * 60

ROW = re.compile(r"^\|\s*(BL\d+)\s*\|\s*([\d-]+)\s*\|\s*(\S+[^|]*?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def rows(text=None):
    t = text if text is not None else (BACKLOG.read_text() if BACKLOG.exists() else "")
    out = []
    for line in t.split("\n"):
        m = ROW.match(line)
        if m and m.group(1) != "id":
            out.append(dict(id=m.group(1), opened=m.group(2), status=m.group(3),
                            job=m.group(4), why=m.group(5)))
    return out


def is_open(r):
    return r["status"].strip().upper().startswith("OPEN")


def cmd_list(show_all):
    rs = rows()
    shown = rs if show_all else [r for r in rs if is_open(r)]
    if not shown:
        print("[backlog] empty." if show_all else "[backlog] nothing open.")
        return 0
    for r in shown:
        print(f"  {r['id']:<4} {r['status']:<18} {r['job']}")
        print(f"       owed because: {r['why']}")
    print(f"[backlog] {sum(1 for r in rs if is_open(r))} open, {len(rs)} total.")
    return 0


def cmd_next(mins):
    """Hand out a job ONLY if a real checkpoint no longer fits."""
    try:
        secs = float(mins) * 60
    except (TypeError, ValueError):
        print("[backlog] REFUSING: `next` needs the minutes remaining.", file=sys.stderr)
        return 2
    if secs >= CHECKPOINT_SECS:
        print(f"[backlog] REFUSING: {secs/60:.1f} min left and a checkpoint takes "
              f"{CHECKPOINT_SECS/60:.0f}. ROLL INSTEAD — the frontier comes first, and this "
              f"list is not a menu (T162).", file=sys.stderr)
        return 2
    op = [r for r in rows() if is_open(r)]
    if not op:
        print("[backlog] nothing open — the backlog is drained. Stop, or roll if there is time.")
        return 0
    r = op[0]
    print(f"[backlog] {r['id']}: {r['job']}")
    print(f"[backlog] owed because: {r['why']}")
    return 0


def _next_id(rs):
    n = max([int(r["id"][2:]) for r in rs], default=0)
    return f"BL{n + 1}"


def cmd_add(job, why, dry):
    job, why = (job or "").strip(), (why or "").strip()
    if len(job) < 10:
        print("[backlog] REFUSING: say what the job IS.", file=sys.stderr)
        return 2
    # The whole discipline in one check: an item with no stated debt is invented
    # work, and invented work is what turns a backlog into a way of looking busy.
    if len(why) < 15:
        print("[backlog] REFUSING: say WHY IT IS OWED — a count that drifted, a check not "
              "re-run, a flag unanswered. An item with no debt behind it is invented work "
              "(T162).", file=sys.stderr)
        return 2
    rs = rows()
    new = f"| {_next_id(rs)} | {date.today().isoformat()} | OPEN | {job} | {why} |"
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(new)
        return 0
    t = BACKLOG.read_text().rstrip("\n")
    BACKLOG.write_text(t + "\n" + new + "\n")
    print(f"[backlog] added {_next_id(rs)}")
    return 0


def cmd_close(bid, dry):
    t = BACKLOG.read_text()
    hit = [r for r in rows(t) if r["id"] == bid.upper()]
    if not hit:
        print(f"[backlog] REFUSING: no such item {bid}.", file=sys.stderr)
        return 2
    if not is_open(hit[0]):
        print(f"[backlog] {bid} is already closed.", file=sys.stderr)
        return 2
    old = f"| {hit[0]['id']} | {hit[0]['opened']} | {hit[0]['status']} |"
    new = f"| {hit[0]['id']} | {hit[0]['opened']} | CLOSED {date.today().isoformat()} |"
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(new)
        return 0
    BACKLOG.write_text(t.replace(old, new, 1))
    print(f"[backlog] closed {bid}")
    return 0


def cmd_check():
    """The control: growth without closure, or closure never happening at all."""
    rs = rows()
    op = [r for r in rs if is_open(r)]
    cl = [r for r in rs if not is_open(r)]
    print(f"[backlog] {len(rs)} items: {len(op)} open, {len(cl)} closed.")
    if not rs:
        print("[backlog] empty — nothing to judge yet.")
        return 0
    oldest = min((r["opened"] for r in op), default=None)
    if oldest:
        print(f"[backlog] oldest open item dates from {oldest}.")
    problems = 0
    if len(rs) >= 5 and not cl:
        print("[backlog] SUSPECT: items have been added and NONE closed. That is a "
              "wish-list, not a backlog — either work one or delete it.")
        problems += 1
    if len(op) >= 12:
        print(f"[backlog] SUSPECT: {len(op)} open. A list this long is not being drawn "
              "from; the mechanism is decoration (T162).")
        problems += 1
    if not problems:
        print("[backlog] OK — it both grows and drains.")
    return 0


def self_check():
    import tempfile
    global BACKLOG
    n = bad = 0

    def chk(name, ok, why):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    with tempfile.TemporaryDirectory() as td:
        BACKLOG = Path(td) / "BACKLOG.md"
        BACKLOG.write_text(
            "| id | opened | status | job | why it is owed |\n|---|---|---|---|---|\n"
            "| BL1 | 2026-08-01 | OPEN | a job that is owed | because something drifted |\n")

        chk("parses an existing row", len(rows()) == 1, "row not parsed")

        # THE RULE THAT MATTERS: the frontier comes first. `next` must refuse
        # while a checkpoint still fits, and must serve when one does not.
        # DISCRIMINATING PAIR -- a `next` that always served would pass half of
        # this and would be exactly the "menu" T162 forbids.
        chk("next REFUSES while a full checkpoint still fits",
            cmd_next("10") == 2, "handed out a tidy job when there was time to roll")
        chk("next SERVES when a checkpoint no longer fits",
            cmd_next("1") == 0, "refuses even in genuine remainder time, so it is useless")

        chk("add REFUSES an item with no stated debt",
            cmd_add("tidy up the docs a bit", "", False) == 2,
            "invented work accepted -- the failure T162 names")
        chk("add ACCEPTS an item that names its debt",
            cmd_add("re-run the staleness controls", "the script changed and they were not re-run", False) == 0,
            "cannot add a legitimate item")
        chk("--dry-run writes nothing",
            (cmd_add("another job entirely", "owed because a flag went unanswered", True) == 0
             and len(rows()) == 2), "dry run mutated the file")

        chk("close marks an item closed", cmd_close("BL1", False) == 0, "could not close")
        chk("close REFUSES an already-closed item", cmd_close("BL1", False) == 2,
            "double-closing accepted, so counts would drift")
        chk("close REFUSES an unknown id", cmd_close("BL99", False) == 2, "closed a phantom")

        # The control must FIRE on a wish-list, not merely exist.
        BACKLOG.write_text(
            "| id | opened | status | job | why it is owed |\n|---|---|---|---|---|\n"
            + "".join(f"| BL{i} | 2026-08-01 | OPEN | job number {i} | owed for a real reason |\n"
                      for i in range(1, 7)))
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_check()
        chk("--check FIRES on a list that only ever grows",
            "wish-list" in buf.getvalue(), "a never-drained backlog passes silently")
        buf2 = io.StringIO()
        BACKLOG.write_text(
            "| id | opened | status | job | why it is owed |\n|---|---|---|---|---|\n"
            "| BL1 | 2026-08-01 | OPEN | a job | owed for a real reason |\n"
            "| BL2 | 2026-08-01 | CLOSED 2026-08-02 | another | owed for a real reason |\n")
        with contextlib.redirect_stdout(buf2):
            cmd_check()
        chk("--check is QUIET on a backlog that drains",
            "OK — it both grows and drains" in buf2.getvalue(),
            "it complains about a healthy list, so the warning means nothing")

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
    if "--check" in a:
        return cmd_check()
    if not a:
        return cmd_list(False)
    if a[0] == "--all":
        return cmd_list(True)
    if a[0] == "next":
        return cmd_next(a[1] if len(a) > 1 else None)
    if a[0] == "add":
        return cmd_add(a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else "", dry)
    if a[0] == "close":
        return cmd_close(a[1] if len(a) > 1 else "", dry)
    print(f"[backlog] unknown command {a[0]!r} — see --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
