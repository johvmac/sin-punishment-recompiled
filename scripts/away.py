#!/usr/bin/env python3
"""The user is away: stop asking for their eyes, and START ASKING AGAIN BY ITSELF.

WHY THIS EXISTS
---------------
Two checks on this project spend the USER'S time rather than mine: the
observed-run gate (T101), which `route.py` cannot clear without them, and the
user-queue reminder (T131), which nags until the queue is swept. Both are worth
having. Neither is worth anything while the user is not at the machine.

The user asked for them to be cut until Monday, 2026-08-22. This is that, built
so it CANNOT become permanent.

THE THREE RULES IT IS BUILT AROUND, all of them already paid for here
---------------------------------------------------------------------
* **AN EXPIRY IS MANDATORY.** There is no open-ended away. A silencing with no
  end date is a deleted safeguard with extra steps, and it would be discovered
  months later by its absence. `set` REFUSES without a return date.

* **IT HIDES CONTENT, NEVER EXISTENCE (T76).** While away, both channels still
  print one line saying something is suppressed and when it returns. The rule
  quiet mode lives by is the rule here: you may withhold what a note SAYS, never
  the fact that it exists.

* **IT CREATES NO DEBT (T151, the user's own rule).** Monday asks for ONE
  observed run, not three. The gate was already activity-gated and this does not
  touch that -- it supplies the DEFERRAL REASON the gate already accepts, rather
  than bypassing the gate. Every skipped day still gets a dated, reasoned record
  in `observed-runs.md`, written on the day. **Nothing is silently skipped, which
  is the whole discipline (T101); only the ASKING stops.**

FAIL-SAFE DIRECTION, AND IT IS THE POINT OF CONTROLS 9 AND 10
-------------------------------------------------------------
A missing file, an unreadable file, a corrupt file or a malformed date all mean
**NOT AWAY** -- the flags fire. A bug in this tool must fail towards nagging the
user, never towards silence, because silence is invisible and nagging is not.

Usage:
    scripts/away.py                          # status: away or not, until when
    scripts/away.py set 2026-08-24 "at a conference"
    scripts/away.py clear
    scripts/away.py --dry-run set ...        # print what it would write
    scripts/away.py --self-check
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AWAY = ROOT / "docs" / ".away.json"

# The suppression covers days STRICTLY BEFORE `until`; on `until` itself the
# flags are back. "Away until Monday" in English means Monday is a working day,
# and the failure mode of the other reading -- one extra silent day -- is the
# one that cannot be noticed.
RETURN_IS_INCLUSIVE = True


def _read():
    """The record, or None. NEVER raises: every failure means NOT AWAY."""
    try:
        if not AWAY.exists():
            return None
        d = json.loads(AWAY.read_text())
        u = date.fromisoformat(d["until"])
        r = str(d.get("reason", "")).strip()
        if not r:
            return None
        return {"until": u, "reason": r, "set_on": d.get("set_on", "")}
    except Exception:
        # Deliberately swallowed and reported by the caller as NOT away. A
        # corrupt file that silenced the user's own safeguards would be
        # undetectable; one that nags is merely annoying.
        return None


def status(today=None):
    """(away: bool, until: date|None, reason: str|None). Never raises."""
    t = today or date.today()
    rec = _read()
    if rec is None:
        return False, None, None
    if t >= rec["until"]:
        return False, rec["until"], rec["reason"]
    return True, rec["until"], rec["reason"]


def is_away(today=None):
    return status(today)[0]


def banner(today=None):
    """The ONE line the suppressing tools print. Existence is never hidden."""
    away, until, reason = status(today)
    if not away:
        return None
    days = (until - (today or date.today())).days
    return (f"user AWAY ({reason}) — eyes-needed flags suppressed until "
            f"{until.isoformat()}, {days} day(s). Nothing is accumulating (T151).")


def cmd_set(until_s, reason, dry):
    reason = (reason or "").strip()
    if not until_s:
        print("[away] REFUSING: a RETURN DATE is mandatory. There is no open-ended "
              "away — a silencing with no expiry is a deleted safeguard.", file=sys.stderr)
        return 2
    if len(reason) < 3:
        print("[away] REFUSING: say why, briefly. It goes into the deferral record "
              "that `observed-runs.md` keeps for each skipped day.", file=sys.stderr)
        return 2
    try:
        u = date.fromisoformat(until_s)
    except ValueError:
        print(f"[away] REFUSING: {until_s!r} is not a YYYY-MM-DD date.", file=sys.stderr)
        return 2
    today = date.today()
    if u <= today:
        print(f"[away] REFUSING: {u} is not in the future — that would suppress "
              f"nothing and read as though it had.", file=sys.stderr)
        return 2
    rec = {"until": u.isoformat(), "reason": reason, "set_on": today.isoformat()}
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(f"would write {AWAY}:")
        print(json.dumps(rec, indent=2))
        return 0
    AWAY.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"[away] set — flags suppressed until {u} ({(u - today).days} day(s)).")
    print(f"[away] the observed-run gate will record a dated DEFERRAL each day it "
          f"fires, so nothing is silently skipped.")
    return 0


def cmd_clear():
    if not AWAY.exists():
        print("[away] not set — nothing to clear.")
        return 0
    AWAY.unlink()
    print("[away] cleared — all flags are live again.")
    return 0


def cmd_status():
    away, until, reason = status()
    if until is None:
        print("[away] not set — all flags live.")
        return 0
    if away:
        print(f"[away] AWAY ({reason}) until {until} — flags suppressed.")
    else:
        print(f"[away] EXPIRED on {until} ({reason}) — flags are live again. "
              f"Run `clear` to tidy the file away.")
    return 0


def self_check():
    import tempfile
    global AWAY
    n = bad = 0

    def chk(name, ok, why):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    with tempfile.TemporaryDirectory() as td:
        AWAY = Path(td) / ".away.json"

        # 9. FAIL-SAFE: no file at all means the flags FIRE.
        chk("no record -> NOT away (flags fire)", not is_away(date(2026, 8, 22)),
            "absent file read as away — a missing file would silence the safeguards")

        AWAY.write_text(json.dumps({"until": "2026-08-24", "reason": "away from PC",
                                    "set_on": "2026-08-22"}) + "\n")

        # THE DISCRIMINATING TRIPLE. A stub that always returned True would pass
        # the first of these and fail both others; one that always returned
        # False would pass both others and fail the first. Neither can pass all.
        chk("away on a day BEFORE the return date", is_away(date(2026, 8, 22)),
            "does not suppress during the away window, so it does nothing")
        chk("NOT away ON the return date", not is_away(date(2026, 8, 24)),
            "still suppressing on the day the user is back — the expiry does not fire")
        chk("NOT away AFTER the return date", not is_away(date(2026, 9, 1)),
            "suppression outlives its expiry, which is the failure this is built against")

        chk("banner names the return date while away",
            "2026-08-24" in (banner(date(2026, 8, 22)) or ""),
            "existence hidden as well as content, against T76")
        chk("banner is silent once expired", banner(date(2026, 8, 24)) is None,
            "prints a suppression notice when nothing is suppressed")

        # 10. FAIL-SAFE: corruption means the flags FIRE.
        AWAY.write_text("{ this is not json")
        chk("CORRUPT record -> NOT away (flags fire)", not is_away(date(2026, 8, 22)),
            "a corrupt file silenced the user's safeguards invisibly")
        AWAY.write_text(json.dumps({"until": "not-a-date", "reason": "x"}))
        chk("MALFORMED date -> NOT away (flags fire)", not is_away(date(2026, 8, 22)),
            "an unparseable date read as away")
        AWAY.write_text(json.dumps({"until": "2026-08-24", "reason": "  "}))
        chk("EMPTY reason -> NOT away (flags fire)", not is_away(date(2026, 8, 22)),
            "suppression with no stated reason accepted")

        AWAY.unlink()
        chk("set REFUSES with no return date", cmd_set("", "away", False) == 2,
            "open-ended away accepted — the one thing this must not allow")
        chk("set REFUSES a past return date",
            cmd_set("2020-01-01", "away", False) == 2, "expired-on-arrival away accepted")
        chk("set REFUSES an unparseable date",
            cmd_set("next monday", "away", False) == 2, "free text accepted as a date")
        chk("set REFUSES an empty reason",
            cmd_set((date.today().replace(year=date.today().year + 1)).isoformat(), "", False) == 2,
            "no reason accepted, so the deferral record would have none either")
        future = date.today().replace(year=date.today().year + 1).isoformat()
        chk("--dry-run writes NOTHING",
            cmd_set(future, "a real reason", True) == 0 and not AWAY.exists(),
            "dry run created the file")
        chk("set ACCEPTS a future date with a reason",
            cmd_set(future, "a real reason", False) == 0 and AWAY.exists(),
            "cannot record a legitimate absence")
        chk("clear removes it", cmd_clear() == 0 and not AWAY.exists(),
            "cleared away is still suppressing")

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
    if not a:
        return cmd_status()
    if a[0] == "set":
        return cmd_set(a[1] if len(a) > 1 else "", a[2] if len(a) > 2 else "", dry)
    if a[0] == "clear":
        return cmd_clear()
    print(f"[away] unknown command {a[0]!r} — see --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
