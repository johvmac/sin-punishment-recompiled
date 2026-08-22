#!/usr/bin/env python3
"""A timed working session: a deadline, a shelf, and a summary that is required.

    scripts/session.py start 25m ["the first task"]
    scripts/session.py status
    scripts/session.py shelve "<what is blocked>" "<why work can continue elsewhere>"
    scripts/session.py block  "<what is blocked>" "<why NOTHING else can proceed>"
    scripts/session.py end    "<one plain-language sentence>"
    scripts/session.py --dry-run start 25m
    scripts/session.py --self-check

WHY THIS EXISTS (T121)
----------------------
On 2026-08-20 the same shape was asked for three times: "set a timer for N
minutes, start with this, then roll through checkpoints until the timer ends or
you hit something that needs me, and finish with a plain-language summary."
Run by hand, three parts went wrong, and none of them were judgement calls:

  * **THE CLOCK.** I estimated elapsed time from how much work had happened and
    was wrong by up to eleven minutes in both directions -- once nearly stopping
    a session at its halfway point. `status` measures it instead.
  * **THE SHELF.** "Shelve it and move on" was agreed and then existed only in
    my head, so a shelved item could be silently dropped rather than reported.
  * **THE SUMMARY.** The closing sentence is the part with no mechanical check,
    and it is the part that got skipped (T120). `end` REFUSES without one, and
    applies the same plain-language test the ledger now applies.

WHAT IT CANNOT DO, and this is the honest boundary
--------------------------------------------------
**It cannot tell a hard block from a soft one.** Whether something needs the
user before ANY further progress, or can be shelved while work continues
elsewhere, is a judgement. What it can do is make the judgement EXPLICIT and
COSTLY to skip: both take a mandatory reason, and both end up in the summary.

It also cannot interrupt. `start` prints a background command that fires a
notification at the deadline; `status` is the reliable path and is cheap.

DRIFT IS MEASURED, NOT TRUSTED (T119)
-------------------------------------
`start` records the roll number and ledger size; `end` re-reads them and reports
rolls consumed against entries added. **Every entry added during the session
must either cite a roll or say it was user-directed** -- an entry that says
neither is work no roll selected, which is exactly T119, and it is named at the
end rather than noticed weeks later by a human.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "docs" / ".session-state.json"
LOG = ROOT / "docs" / "session-log.md"
LEDGER = ROOT / "docs" / "findings-ledger.md"
ROUTELOG = ROOT / "docs" / "route-log.md"

# The user's standing decision, 2026-08-21: running ~5 minutes over any time
# budget is fine. A checkpoint truncated to land on the minute -- no entry, no
# SO WHAT line, no commit -- costs the NEXT session more than the overrun saves.
# ONE definition, shared by `status` and `end`, so the two cannot drift.
GRACE = 5 * 60
# THE FINISHING ALLOWANCE, the user's instruction on 2026-08-22: "better to just
# extend whatever time I say by five minutes -- worst case I wait a few minutes
# while you finish up". Added to the BUDGET, which is a different thing from
# GRACE above: grace permits running over to finish work already in flight,
# this permits STARTING work in those five minutes. Printed, never silent --
# a tool that quietly changes the number you asked for is a tool you stop
# trusting about numbers.
FINISHING_ALLOWANCE = 5 * 60
# A zero-run checkpoint, measured: 17m27s over 6 rolls on 2026-08-22 = 2.9 min.
CHECKPOINT = 3 * 60

sys.path.insert(0, str(ROOT / "scripts"))
try:
    from check_ledger import not_plain          # ONE definition of "plain" (T121)
except Exception:                                # pragma: no cover
    def not_plain(_):
        return None


def parse_duration(text):
    """'25m' / '90s' / '1h' / '25' (bare = minutes) -> seconds. None if unparseable."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(s|sec|secs|m|min|mins|h|hr|hrs)?\s*", text or "",
                     re.I)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    if unit.startswith("s"):
        return int(n)
    if unit.startswith("h"):
        return int(n * 3600)
    return int(n * 60)


def hms(secs):
    secs = int(secs)
    sign = "-" if secs < 0 else ""
    secs = abs(secs)
    return f"{sign}{secs // 60}m{secs % 60:02d}s"


def last_roll():
    try:
        nums = [int(x) for x in re.findall(r"#(\d+)", ROUTELOG.read_text(errors="replace"))]
        return max(nums) if nums else 0
    except Exception:
        return 0


def entry_ids():
    """The set of entry IDs currently in the ledger."""
    try:
        return set(re.findall(r"^\| ([A-Z]+\d+) \|", LEDGER.read_text(errors="replace"), re.M))
    except Exception:
        return set()


def entry_rows():
    """id -> full row text, for the accountability check."""
    out = {}
    try:
        for line in LEDGER.read_text(errors="replace").split("\n"):
            m = re.match(r"^\| ([A-Z]+\d+) \|", line)
            if m:
                out.setdefault(m.group(1), line)
    except Exception:
        pass
    return out


def load():
    try:
        return json.loads(STATE.read_text()) if STATE.exists() else None
    except Exception:
        return None


def save(d):
    STATE.write_text(json.dumps(d, indent=1))


def cmd_start(args, dry=False, now=None):
    secs = parse_duration(args[0] if args else "")
    if secs is None:
        print("[session] REFUSING: give a duration -- 25m, 90s, 1h.", file=sys.stderr)
        return 2
    if secs < 60 or secs > 6 * 3600:
        print(f"[session] REFUSING: {hms(secs)} is outside 1 minute .. 6 hours.",
              file=sys.stderr)
        return 2
    task = args[1] if len(args) > 1 else ""
    open_s = load()
    if open_s and not open_s.get("ended"):
        print(f"[session] REFUSING: a session started {hms((now or time.time()) - open_s['start'])} "
              f"ago is still open. End it first -- two overlapping deadlines is no deadline.",
              file=sys.stderr)
        return 2
    t0 = now if now is not None else time.time()
    requested = secs
    secs = secs + FINISHING_ALLOWANCE
    d = {"start": t0, "deadline": t0 + secs, "requested": requested, "task": task, "shelf": [], "blocks": [],
         "roll_at_start": last_roll(), "entries_at_start": sorted(entry_ids()), "ended": False}
    if dry:
        print("=== DRY RUN — no session started ===")
        print(f" duration : {hms(requested)} requested + {hms(FINISHING_ALLOWANCE)} "
              f"finishing allowance = {hms(secs)}")
        print(f" task     : {task or '(none given — first checkpoint is a roll)'}")
        print(f" roll now : #{d['roll_at_start']}   ledger: {len(d['entries_at_start'])} entries")
        print(" would write: docs/.session-state.json")
        return 0
    save(d)
    print(f"[session] started — {hms(requested)} requested + {hms(FINISHING_ALLOWANCE)} finishing allowance = {hms(secs)}")
    print(f"[session] ends at {time.strftime('%H:%M:%S', time.localtime(d['deadline']))}")
    print(f"[session] task: {task or '(none — start with a roll)'}")
    print(f"[session] baseline: roll #{d['roll_at_start']}, {len(d['entries_at_start'])} ledger entries")
    print(f"[session] optional notification (run in background):")
    print(f"    sleep {secs} && echo '=== SESSION DEADLINE ==='")
    print(f"[session] check the clock with `scripts/session.py status` — do NOT estimate it")
    return 0


def cmd_status(now=None):
    d = load()
    if not d or d.get("ended"):
        print("[session] no session open.")
        return 1
    t = now if now is not None else time.time()
    left = d["deadline"] - t
    # The user's standing decision (2026-08-21): ~5 minutes over any budget is
    # fine, because a truncated checkpoint costs the next session more than the
    # overrun saves. So the deadline is a boundary for STARTING work, and only
    # past the grace does this shout. Kept identical to the skill's wording --
    # a tool and its doc disagreeing about the rule is how the rule gets
    # argued with rather than followed (T121).
    over = -left
    if left > 0:
        note = ""
    elif over <= GRACE:
        note = (f"   <<< past the deadline by {hms(over)} — inside the {hms(GRACE)} "
                "grace. FINISH what is in flight; do not START anything new.")
    else:
        note = f"   <<< OVER by {hms(over)}, BEYOND the {hms(GRACE)} grace — close it"
    print(f"[session] elapsed {hms(t - d['start'])}, remaining {hms(left)}" + note)
    # T161: I closed three sessions early on 2026-08-22 by asking "does the
    # BIGGEST pending item fit?" instead of "does ANY item fit?". Minutes
    # invite the first question; checkpoints invite the second. A zero-run
    # checkpoint on this project measured ~2.9 minutes over six consecutive
    # rolls, so the remaining time is restated in the unit of the decision.
    if left > 0:
        n = int(left // CHECKPOINT)
        if n >= 1:
            print(f"[session] that is room for ~{n} more checkpoint(s) at "
                  f"{hms(CHECKPOINT)} each. DO NOT ask whether the biggest pending\n"
                  f"[session]     item fits — ask whether ANY does. Roll again (T161).")
        else:
            print(f"[session] under one checkpoint left — finishing up is right now.")
    if d.get("task"):
        print(f"[session] opening task: {d['task']}")
    print(f"[session] rolls consumed so far: {last_roll() - d['roll_at_start']}"
          f"   entries added: {len(entry_ids()) - len(set(d['entries_at_start']))}")
    for s in d.get("shelf", []):
        print(f"[session] SHELVED: {s['what']}  — {s['why']}")
    for b in d.get("blocks", []):
        print(f"[session] HARD BLOCK: {b['what']}  — {b['why']}")
    if d.get("blocks"):
        print("[session] >>> STOP. A hard block is open: nothing else can proceed until")
        print("[session]     the user answers. Close with `end` and say so.")
    return 0


def _add(kind, args, label):
    if len(args) < 2 or not args[0].strip() or not args[1].strip():
        print(f"[session] REFUSING: {label} needs WHAT and WHY. A blocker with no reason "
              f"is one nobody can act on later.", file=sys.stderr)
        return 2
    d = load()
    if not d or d.get("ended"):
        print("[session] REFUSING: no session open.", file=sys.stderr)
        return 2
    d.setdefault(kind, []).append({"what": args[0].strip(), "why": args[1].strip()})
    save(d)
    print(f"[session] {label} recorded: {args[0].strip()}")
    if kind == "blocks":
        print("[session] >>> This says NOTHING else can proceed. Stop and ask the user.")
    else:
        print("[session] >>> Shelved. Keep working on something else.")
    return 0


def cmd_end(args, now=None):
    d = load()
    if not d or d.get("ended"):
        print("[session] REFUSING: no session open.", file=sys.stderr)
        return 2
    summary = (args[0] if args else "").strip()
    if len(summary) < 15:
        print("[session] REFUSING: a session ends with ONE PLAIN SENTENCE saying what "
              "happened. This is the part with no other check on it, and it is the part "
              "that gets skipped (T120).", file=sys.stderr)
        return 2
    what = not_plain(summary)
    if what:
        print(f"[session] REFUSING: the summary contains {what}. Write it for someone who "
              f"was not here.", file=sys.stderr)
        return 2

    t = now if now is not None else time.time()
    rolls = last_roll() - d["roll_at_start"]
    added = sorted(entry_ids() - set(d["entries_at_start"]))
    rows = entry_rows()
    unaccounted = [e for e in added
                   if not re.search(r"Roll #\d+|user-directed|no roll", rows.get(e, ""), re.I)]

    _over = t - d["deadline"]
    print(f"[session] ran {hms(t - d['start'])} (planned {hms(d['deadline'] - d['start'])})"
          + ("" if _over <= 0
             else f"  — over by {hms(_over)}, within the {hms(GRACE)} grace" if _over <= GRACE
             else f"  — OVER by {hms(_over)}, BEYOND the {hms(GRACE)} grace"))
    print(f"[session] {rolls} roll(s) consumed, {len(added)} entr(y/ies) added")
    if unaccounted:
        print(f"[session] DRIFT (T119): {len(unaccounted)} entr(y/ies) cite neither a roll nor "
              f"user direction: {', '.join(unaccounted)}")
        print(f"[session] That is work no roll selected. Not an error — but say it in the summary.")
    for s in d.get("shelf", []):
        print(f"[session] still shelved: {s['what']}  — {s['why']}")
    for b in d.get("blocks", []):
        print(f"[session] hard block: {b['what']}  — {b['why']}")

    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(d["start"]))
    line = (f"| {stamp} | {hms(t - d['start'])} / {hms(d['deadline'] - d['start'])} | {rolls} | "
            f"{len(added)} | {len(d.get('shelf', []))} | {len(d.get('blocks', []))} | "
            f"{len(unaccounted)} | {summary} |\n")
    if not LOG.exists():
        LOG.write_text("# Session log\n\nAppend-only. Written by `scripts/session.py end`.\n\n"
                       "| started | ran / planned | rolls | entries | shelved | blocked | "
                       "unaccounted | what happened |\n|---|---|---|---|---|---|---|---|\n")
    with LOG.open("a") as f:
        f.write(line)
    d["ended"] = True
    save(d)
    print(f"[session] recorded in docs/session-log.md")
    return 0


def self_check():
    import tempfile
    fails = 0
    n = 0

    def chk(label, got, detail=""):
        nonlocal fails, n
        n += 1
        print(f"{'ok  ' if got else 'FAIL'}  {label}" + ("" if got else f" -- {detail}"))
        if not got:
            fails += 1

    me = [sys.executable, str(Path(__file__).resolve())]

    def run(args, cwd):
        return subprocess.run(me + args, capture_output=True, text=True, cwd=cwd)

    with tempfile.TemporaryDirectory() as td:
        # Probe against a THROWAWAY tree. A self-check must not be able to
        # clobber a real session -- snapshot_build.sh learned that by writing a
        # 94 MB snapshot into the live archive while testing its own guard.
        root = Path(td)
        (root / "docs").mkdir()
        (root / "scripts").mkdir()
        for f in ("session.py", "check_ledger.py"):
            (root / "scripts" / f).write_bytes((ROOT / "scripts" / f).read_bytes())
        (root / "docs" / "findings-ledger.md").write_text(
            "| # | status | finding | evidence |\n|---|---|---|---|\n"
            "| A1 | MEASURED | x | y |\n")
        (root / "docs" / "route-log.md").write_text("roll #7\n")
        probe = [sys.executable, str(root / "scripts" / "session.py")]

        def p(args):
            return subprocess.run(probe + args, capture_output=True, text=True, cwd=str(root))

        chk("a duration is required", p(["start"]).returncode == 2, "started with no duration")
        chk("an absurd duration is refused", p(["start", "99h"]).returncode == 2, "accepted 99h")

        r = p(["start", "30m", "first task"])
        chk("start records a session", r.returncode == 0 and (root / "docs" / ".session-state.json").exists(),
            f"rc={r.returncode}")

        chk("a second start REFUSES while one is open", p(["start", "10m"]).returncode == 2,
            "two overlapping deadlines is no deadline")

        chk("shelve needs a reason", p(["shelve", "a thing"]).returncode == 2, "accepted no reason")
        chk("block needs a reason", p(["block", "a thing"]).returncode == 2, "accepted no reason")

        p(["shelve", "the audio probe", "needs a tool we do not have"])
        st = p(["status"])
        chk("status reports a shelved item", "SHELVED" in st.stdout, "shelf not surfaced")

        p(["block", "a decision", "nothing else can move until the user chooses"])
        st = p(["status"])
        chk("a hard block makes status say STOP", "STOP" in st.stdout, "block not escalated")

        # THE GRACE MUST BE BOUNDED, AND THE TWO SIDES OF IT MUST DIFFER.
        # A grace that never ends is not a grace, it is a removed deadline --
        # and the user asked for ~5 minutes, not for the clock to stop
        # mattering. So this asserts BOTH directions: inside the window status
        # says finish-what-is-in-flight, and past it status still shouts.
        # A single-sided check would pass on a grace of infinity.
        _sf = root / "docs" / ".session-state.json"
        _d = json.loads(_sf.read_text())
        _dl = _d["deadline"]

        # THE OFFSETS ARE LITERALS, NOT DERIVED FROM `GRACE`. The first version
        # wrote `time.time() - (GRACE + 60)`, so raising GRACE moved the test's
        # own needle with it: set GRACE to 10**9 and the suite still scored
        # 16/16 on a grace that had effectively removed the deadline. That is
        # T100's pattern -- a control computing its needle from the thing it
        # checks -- and it is why the rule is "~5 minutes" written HERE as a
        # number the implementation cannot move. Change the policy and this
        # control must be changed deliberately, which is the point.
        _d["deadline"] = time.time() - 60             # 1 min over
        _sf.write_text(json.dumps(_d))
        _in = p(["status"]).stdout
        _d["deadline"] = time.time() - (11 * 60)      # 11 min over: past ANY
        _sf.write_text(json.dumps(_d))                # grace this rule allows
        _out = p(["status"]).stdout
        _d["deadline"] = _dl                          # put it back
        _sf.write_text(json.dumps(_d))

        chk("inside the grace, status says finish — it does not shout",
            "grace" in _in and "BEYOND" not in _in,
            f"got: {_in.splitlines()[0] if _in else 'nothing'}")
        chk("PAST the grace, status still shouts (a grace is bounded)",
            "BEYOND" in _out,
            f"got: {_out.splitlines()[0] if _out else 'nothing'}")

        # THE DISCRIMINATING CLOCK CONTROL. A status that printed a constant --
        # or the planned duration -- would look perfectly healthy. This asserts
        # the number actually MOVES, which is the whole reason the clock is
        # mechanical rather than estimated.
        a = p(["status"]).stdout
        time.sleep(1.2)
        b = p(["status"]).stdout
        ga = re.search(r"remaining (-?\d+)m(\d+)s", a)
        gb = re.search(r"remaining (-?\d+)m(\d+)s", b)
        moved = bool(ga and gb and (int(ga.group(1)) * 60 + int(ga.group(2))) >
                     (int(gb.group(1)) * 60 + int(gb.group(2))))
        chk("the clock is LIVE (remaining actually decreases)", moved,
            f"first={ga.group(0) if ga else None} second={gb.group(0) if gb else None}")

        # THE FINISHING ALLOWANCE (T161, user instruction 2026-08-22). Asking for
        # 30m must PLAN 35m, and must SAY SO. Both halves are checked: a silent
        # extension would be a tool quietly changing the number you gave it.
        _r = run(["--dry-run", "start", "30m"], cwd=str(root))
        chk("a 30m request PLANS 35m (the finishing allowance is applied)",
            "35m00s" in _r.stdout, f"planned {_r.stdout.strip()[:80]}")
        chk("the allowance is DISCLOSED, not silent",
            "30m00s" in _r.stdout and "allowance" in _r.stdout.lower(),
            "the extension does not name itself in the output")

        # THE RULE THAT BINDS: status must restate time as CHECKPOINTS, because
        # minutes are what invited "the big item does not fit, so stop".
        # DISCRIMINATING PAIR: it must say so with plenty of time AND must say
        # the opposite with almost none -- a message that always appears is not
        # information.
        _st = json.loads((root / "docs" / ".session-state.json").read_text())
        _st["deadline"] = time.time() + 1800
        (root / "docs" / ".session-state.json").write_text(json.dumps(_st))
        chk("status counts REMAINING CHECKPOINTS, not just minutes (T161)",
            "checkpoint(s)" in p(["status"]).stdout, "only minutes are shown")
        _st["deadline"] = time.time() + 40
        (root / "docs" / ".session-state.json").write_text(json.dumps(_st))
        chk("and says the OPPOSITE when under one checkpoint remains",
            "finishing up is right" in p(["status"]).stdout,
            "it nags to roll again even with 40 seconds left")
        _st["deadline"] = time.time() + 1800
        (root / "docs" / ".session-state.json").write_text(json.dumps(_st))

        chk("end REFUSES with no summary", p(["end"]).returncode == 2, "ended silently")
        chk("end REFUSES a jargon summary",
            p(["end", "merged 0x800F91B0 per A197 in funcs_128.c"]).returncode == 2,
            "accepted an unreadable summary")

        # DRIFT: an entry added with no roll citation and no user-direction note.
        (root / "docs" / "findings-ledger.md").write_text(
            "| # | status | finding | evidence |\n|---|---|---|---|\n"
            "| A1 | MEASURED | x | y |\n"
            "| A2 | MEASURED | something nobody rolled for | z |\n")
        r = p(["end", "we looked at the thing and it still does not work"])
        chk("end DETECTS an entry that cites neither a roll nor user direction",
            r.returncode == 0 and "DRIFT" in r.stdout, "drift went unreported")
        chk("end writes the session log", (root / "docs" / "session-log.md").exists(),
            "no durable record")
        chk("end closes the session", p(["status"]).returncode == 1, "session still open")

    print()
    print(f"{n - fails}/{n} controls pass")
    return 1 if fails else 0


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--self-check":
        return self_check()
    dry = False
    if argv[0] == "--dry-run":
        dry = True
        argv = argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "start":
        return cmd_start(rest, dry=dry)
    if cmd == "status":
        return cmd_status()
    if cmd == "shelve":
        return _add("shelf", rest, "SHELVED")
    if cmd == "block":
        return _add("blocks", rest, "HARD BLOCK")
    if cmd == "end":
        return cmd_end(rest)
    print(f"[session] unknown command '{cmd}'. See --help.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
