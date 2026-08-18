#!/usr/bin/env python3
"""Level-1 discipline audit: every ~10 routing rolls, check the recent work.

WHY
---
On 2026-08-18, 26 of 170 ledger entries were withdrawn. Almost none of those
errors were caught by discipline in the moment. They were caught by:

  * the user noticing two of them (route.py claiming a cost ranking it never
    computed; a run-length figure generalised from one slow run),
  * random EXPLORE rolls landing on stale items (a splat config that is not in
    this repo; a citation to an entry that was never written),
  * one audit the user asked for (routing rolls being skipped).

So periodic review is the mechanism that works here, and it needs to be cheap
enough to actually happen.

WHAT THIS IS NOT
----------------
It does not re-verify findings. Re-checking a claim costs what producing it
cost, so an audit that does that will simply be skipped. It checks LEADING
INDICATORS that leave machine-readable traces -- each one below maps to a
failure that really happened:

  1. single-run claims          -> T22, variance misattributed three times
  2. probes with no control     -> I1, I13, and a negative nearly trusted blind
  3. churn (created+withdrawn)  -> I14 lasted about an hour
  4. explore ratio below eps    -> T14, rolls skipped in unattended stretches
  5. entries with no evidence   -> the A24/B35 dangling-citation class
  6. contaminated runs          -> T23, input can silently wreck a run
  7. the 18:30 cron push        -> its log almost always says "nothing to
                                   commit", so a real failure looks the same

It reads STRUCTURED data only: the ledger table, docs/run-log.tsv,
docs/route-log.md, git. It never opens the journal. Cost is a couple of
seconds and ~15 lines of output, and it stays flat as history grows because
the window is bounded by the last audit.

Findings are prompts for judgement, not errors. The daily (L2) review reads
THIS script's output rather than the raw data -- that is where the compression
lives.

KILL CRITERION
--------------
If three consecutive audits find nothing actionable, halve the frequency. An
audit that never fires is a cost, not a control.

Usage:
    scripts/audit.py                # audit since the last one, record it
    scripts/audit.py --dry-run      # print, do not record
    scripts/audit.py --since <rev>  # audit since an explicit git revision
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LEDGER = DOCS / "findings-ledger.md"
RUNLOG = DOCS / "run-log.tsv"
ROUTELOG = DOCS / "route-log.md"
STATE = DOCS / ".audit-state.json"
OUT = DOCS / "audit-log.md"
EPS = 0.20

ROW = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]*?)\s*\|\s*(.*?)\s*\|\s*([^|]*?)\s*\|?\s*$")


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args],
                              capture_output=True, text=True, check=True).stdout
    except Exception:
        return ""


def parse_rows(text):
    """id -> (status, body, evidence)."""
    out = {}
    for line in text.split("\n"):
        m = ROW.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = (m.group(2), m.group(3), m.group(4))
    return out


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"audits": 0, "last_rev": "", "last_roll": 0, "quiet_streak": 0}


def main():
    dry = "--dry-run" in sys.argv
    st = load_state()

    since = st.get("last_rev") or ""
    if "--since" in sys.argv:
        since = sys.argv[sys.argv.index("--since") + 1]

    now_text = LEDGER.read_text()
    now = parse_rows(now_text)
    then = parse_rows(git("show", f"{since}:docs/findings-ledger.md")) if since else {}

    added = {k: v for k, v in now.items() if k not in then}
    findings = []

    # 1. MEASURED/INTERVENED claims whose evidence names exactly one log file.
    # One run is not a measurement of a build (T22).
    for eid, (status, body, ev) in added.items():
        if not re.search(r"MEASURED|INTERVENED", status):
            continue
        logs = re.findall(r"[\w.-]+\.log", ev + " " + body)
        if len(set(logs)) == 1 and not re.search(r"\b(\d+|two|three|both)\s+runs?\b", ev + " " + body, re.I):
            findings.append(f"{eid}: rests on ONE run ({logs[0]}). Repeat it or say why one is enough.")

    # 2. entries that describe a probe but never mention a control
    for eid, (status, body, ev) in added.items():
        if re.search(r"\bprobe|hook\b", body, re.I) and not re.search(
                r"control|ARM |heartbeat|positive", body + ev, re.I):
            findings.append(f"{eid}: describes a probe with no control mentioned. A dead probe reads as a clean negative.")

    # 3. churn: created AND withdrawn inside this window
    for eid, (status, body, ev) in added.items():
        if "WD" in status:
            findings.append(f"{eid}: created and withdrawn within one audit window. What made it look right?")

    # 4. explore ratio
    rolls = re.findall(r"^- roll #(\d+): \*\*(EXPLORE|EXPLOIT)\*\*", ROUTELOG.read_text(), re.M) \
        if ROUTELOG.exists() else []
    window = [r for r in rolls if int(r[0]) > st.get("last_roll", 0)]
    if window:
        expl = sum(1 for _, v in window if v == "EXPLORE")
        exp_n = EPS * len(window)
        if len(window) >= 8 and expl < exp_n / 2:
            findings.append(f"explore: {expl}/{len(window)} rolls (expected ~{exp_n:.1f}). Under-exploring.")

    # 5. entries with an empty evidence cell
    for eid, (status, body, ev) in added.items():
        if "OPEN" not in status and "WD" not in status and not ev.strip():
            findings.append(f"{eid}: no evidence recorded. Say what was observed and when.")

    # 6. contaminated or invalid runs in the window
    runs = []
    if RUNLOG.exists():
        for line in RUNLOG.read_text().split("\n")[1:]:
            f = line.split("\t")
            if len(f) >= 9:
                runs.append(f)
    n_new = len(runs) - st.get("last_runs", 0)
    recent = runs[-n_new:] if n_new > 0 else []
    dirty = [r for r in recent if r[4] not in ("0", "")]
    crashed = [r for r in recent if r[3] not in ("0", "")]
    if dirty:
        findings.append(f"runs: {len(dirty)}/{len(recent)} had controller input -- not comparable to clean runs (T23).")

    # 7. the 18:30 cron push. Because every checkpoint pushes manually, this
    # almost always logs "nothing to commit" -- so its log is a monotonous
    # success message that nobody reads, and a real failure (drive unmounted,
    # key expired, a refusal triggered) would look much the same at a glance.
    # That is the same shape as the defects this whole session was spent fixing:
    # a signal with no reader. Cheap to check here, where there IS a reader.
    import datetime as _dt
    push_log = ROOT / "scripts" / "daily_push.log"
    _now_dt = _dt.datetime.now()
    if not push_log.exists():
        findings.append("cron: scripts/daily_push.log missing — the 18:30 push has never run.")
    else:
        age_days = (_now_dt - _dt.datetime.fromtimestamp(push_log.stat().st_mtime)).days
        last = [l for l in push_log.read_text().strip().split("\n") if l.strip()]
        last = last[-1] if last else ""
        # Before 18:30 the freshest possible log is yesterday's, so only a log
        # older than that is evidence of a miss.
        stale_limit = 0 if _now_dt.hour > 18 or (_now_dt.hour == 18 and _now_dt.minute >= 35) else 1
        if age_days > stale_limit:
            findings.append(f"cron: daily_push.log is {age_days}d old — the 18:30 push may not be running.")
        if "REFUSING" in last or "error" in last.lower() or "fatal" in last.lower():
            findings.append(f"cron: last push ended in a refusal/error — {last[:90]}")

    lines = [f"## Audit #{st['audits'] + 1} — since {since[:8] or 'start'}",
             f"- ledger: {len(now)} entries (+{len(added)} this window), "
             f"{sum(1 for s, _, _ in now.values() if 'WD' in s)} withdrawn",
             f"- rolls: {len(window)} this window; runs: {len(recent)} "
             f"({len(crashed)} exited early, {len(dirty)} contaminated)"]
    if findings:
        lines.append(f"- **{len(findings)} thing(s) to look at:**")
        lines += [f"  - {f}" for f in findings]
    else:
        lines.append("- nothing flagged "
                     f"(quiet streak {st.get('quiet_streak', 0) + 1}; at 3, halve the frequency)")

    print("\n".join(lines))

    if not dry:
        st["audits"] += 1
        st["last_rev"] = git("rev-parse", "HEAD").strip()
        st["last_roll"] = int(rolls[-1][0]) if rolls else st.get("last_roll", 0)
        st["last_runs"] = len(runs)
        st["quiet_streak"] = 0 if findings else st.get("quiet_streak", 0) + 1
        STATE.write_text(json.dumps(st, indent=1))
        if not OUT.exists():
            OUT.write_text("# Audit log\n\nLevel-1 discipline audits. The daily "
                           "review reads THIS file, not the raw data.\n\n")
        with OUT.open("a") as f:
            f.write("\n".join(lines) + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
