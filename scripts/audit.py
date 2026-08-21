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


def _tag_res():
    """OPEN/WD predicates, imported from route.py -- the single source (T75).

    audit.py was the FOURTH tool carrying its own `"WD" in status`, after
    route.py, check_ledger.py and ledger.py. It reported 36 withdrawn while
    check_ledger reported 35, and it flagged T72 as "created and withdrawn
    within one window" -- T72 being the entry whose status merely SAYS "A138 is
    the WD entry, not this one". A tag must OPEN the cell, never merely appear
    in it.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_route_tags", Path(__file__).resolve().parent / "route.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.OPEN_RE, m.WD_RE
    except Exception:
        return (re.compile(r"\s*\**OPEN\b", re.I), re.compile(r"\s*\**WD\b", re.I))


OPEN_RE, WD_RE = _tag_res()


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
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0

    # T37: audit.py appends to docs/audit-log.md, so an unrecognised flag must
    # not fall through to the default (writing) action.
    KNOWN = {"--dry-run", "--since", "--help", "-h"}
    unknown = [a for a in sys.argv[1:]
               if a.startswith("-") and a not in KNOWN]
    if unknown:
        print("[audit] unknown argument(s): " + " ".join(unknown), file=sys.stderr)
        print("[audit] known: " + ", ".join(sorted(KNOWN)), file=sys.stderr)
        print("[audit] REFUSING to run — this script writes docs/audit-log.md.",
              file=sys.stderr)
        return 2
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
    suppressed = []

    # Supersession is decided by check_ledger's vocabulary, adapted to this
    # script's row shape. Falls back to "nothing is superseded" if the import
    # fails, because an audit that silently suppresses everything is worse than
    # one that is noisy.
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "_cl", Path(__file__).resolve().parent / "check_ledger.py")
        _cl = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_cl)
        all_rows = {k: (v[0], v[1] + " " + v[2], 0) for k, v in now.items()}
        _superseded = _cl.superseded_by_later
    except Exception:
        all_rows = {}
        _superseded = lambda *_a: None

    # 1. MEASURED/INTERVENED claims whose evidence names exactly one log file.
    # One run is not a measurement of a build (T22).
    for eid, (status, body, ev) in added.items():
        if not re.search(r"MEASURED|INTERVENED", status):
            continue
        logs = re.findall(r"[\w.-]+\.log", ev + " " + body)
        if len(set(logs)) == 1 and not re.search(r"\b(\d+|two|three|both)\s+runs?\b", ev + " " + body, re.I):
            # DOES ANYTHING STILL DEPEND ON IT? (T123)
            #
            # L1 #9 fired seven findings and SIX were noise -- three of them
            # flagged entries the A99 fix had already superseded, so nothing
            # rested on their single run and nobody could act on the flag. A
            # 6-of-7 noise rate is how a ladder level stops being read (T29),
            # and the check had no way to tell a live entry from a dead one.
            #
            # The supersession vocabulary is IMPORTED, not restated: two
            # definitions of "corrected" would let an entry be live for one
            # checker and dead for the other.
            # HONOUR THE SAME WAIVER check_ledger ACCEPTS (T123). That checker
            # asks at WRITE time and takes "ONE RUN IS ENOUGH: <reason>" as an
            # answer; this one asked again at audit time and ignored the answer,
            # so an entry that had already justified itself was flagged anyway.
            # Two checkers, one rule, two verdicts -- the exact failure the
            # single-run comment warns about three lines further up.
            if re.search(r"ONE RUN[,:]?\s*(IS ENOUGH|and (the )?reason)", ev + " " + body, re.I):
                suppressed.append(f"{eid} (single-run, justified in the entry)")
                continue
            killer = _superseded(eid, all_rows)
            if killer:
                suppressed.append(f"{eid} (single-run, superseded by {killer})")
                continue
            findings.append(f"{eid}: rests on ONE run ({logs[0]}). Repeat it or say why one is enough.")

    # 2. entries that describe a probe THEY RAN but never mention a control.
    #
    # Narrowed 2026-08-19 after audit #5 flagged 6 entries in this category and
    # ALL SIX were false positives. The old test was `\bprobe|hook\b` against
    # the whole body, which fires on any entry that merely says the word:
    # T36 counting debug probes in a working tree, T47 listing filenames that
    # contain "probe", A118 describing what a hook "would have done", T39 naming
    # the script probe_stubs.py. Worse, A110 and A105 DID state their controls
    # -- as "Independent confirmation" and "OBSERVED, not assumed" -- and were
    # flagged because the detector only knew the literal word "control".
    #
    # Six of six wrong is not a strict check, it is noise, and noise is how a
    # discipline stops being read (T29). Same defect class as T40: a predicate
    # matched against a wider thing than the one it describes.
    #
    # So: require a phrase that indicates an instrument THIS entry deployed, and
    # recognise a control however it is worded.
    DEPLOYED = re.compile(
        r"probe (?:at|on|in|fired|printed|logged|reported|caught|is live)|"
        r"(?:scratch |toml |a |new |walker-entry )hook on|hooks? fired|"
        r"instrumented|\bSNP_[A-Z]", re.I)
    CONTROL = re.compile(
        r"control|ARM |heartbeat|positive|independent(?:ly)? (?:confirm|verif|source)|"
        r"cross-check|OBSERVED, not assumed|exact match|two independent", re.I)
    # AN ENTRY THAT RAN NOTHING DEPLOYED NOTHING (audit #13, 2026-08-21).
    # `\bSNP_[A-Z]` fires on a probe's NAME, so a source survey saying "the
    # probe ACCEPTS a queue address" was read as a probe that had been run.
    # A241 and A243 -- both zero-run RT64 source reads -- were flagged for
    # lacking a control over output they never produced.
    #
    # The exemption is a FACT, not a judgement: no runs, no probe output, so
    # there is nothing for a control to discriminate. That is what keeps it
    # from becoming the kind of blanket suppression that stops a rule working.
    # An entry re-analysing an EARLIER run's logs is still exempt here, and
    # correctly -- the control question belongs to the entry that ran it.
    # The run count is declared in the STATUS cell by convention -- "MEASURED
    # (2 x 240 s runs...)", "READ (RT64 source survey, zero runs)" -- so the
    # status must be searched too. Checking body+ev alone missed A243, which
    # says "zero runs" in exactly that place.
    ZERO_RUNS = re.compile(r"zero (?:new )?runs|no new runs", re.I)
    # A POINTER entry defers its substance to another entry: "ANSWERED by A243",
    # "CLOSED by A85/A90", "MERGED into <ID>". Its evidence and controls live in
    # the entry it names, so asking the signpost for a control is asking the
    # wrong entry -- which is why A241 was flagged. **`CORRECTS` is NOT here on
    # purpose**: A244 corrects A239 and carries its own 5 runs, an A/B pair and
    # a contamination control. A correction is a claim; a pointer is not.
    POINTER = re.compile(r"^\**(?:ANSWERED by|CLOSED by|MERGED into)\b", re.I)
    for eid, (status, body, ev) in added.items():
        if ZERO_RUNS.search(status + body + ev) or POINTER.match(status.strip()):
            continue
        if DEPLOYED.search(body) and not CONTROL.search(body + ev):
            findings.append(f"{eid}: describes a probe with no control mentioned. A dead probe reads as a clean negative.")

    # 3. churn: created AND withdrawn inside this window
    for eid, (status, body, ev) in added.items():
        if WD_RE.match(status):
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
        if not OPEN_RE.match(status) and not WD_RE.match(status) and not ev.strip():
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
             f"{sum(1 for s, _, _ in now.values() if WD_RE.match(s))} withdrawn",
             f"- rolls: {len(window)} this window; runs: {len(recent)} "
             f"({len(crashed)} exited early, {len(dirty)} contaminated)"]
    if findings:
        lines.append(f"- **{len(findings)} thing(s) to look at:**")
        lines += [f"  - {f}" for f in findings]
    if suppressed:
        # NAMED, NEVER SILENT. A suppression rule that hides its own work is
        # indistinguishable from a broken check, and "the audit found nothing"
        # would then be unfalsifiable. Same reason lint_tools.py prints its
        # known debt every run.
        lines.append(f"- suppressed as superseded ({len(suppressed)}): "
                     + "; ".join(suppressed))
    else:
        lines.append("- nothing flagged "
                     f"(quiet streak {st.get('quiet_streak', 0) + 1}; at 3, halve the frequency)")

    print("\n".join(lines))

    # An EMPTY window is not a quiet audit -- it is a non-event, and recording it
    # as quiet is actively harmful: three quiet audits halve the audit frequency
    # (see the streak line below), so re-running this script to test a change to
    # it would make audits RARER. That happened on 2026-08-19: audit #6 was
    # recorded two minutes after #5, +0 entries and 0 rolls, purely because the
    # script was invoked without --dry-run to check a fix to its own probe check.
    # Same shape as T37 -- a state-mutating script run without checking its flags
    # -- and the reason --dry-run exists. Refuse rather than rely on remembering.
    # `window` is the rolls INSIDE this window; `rolls` is the whole route log
    # and is never empty, so guarding on it does nothing. The first version of
    # this guard did exactly that and silently failed to fire -- caught only
    # because the state file was checked afterwards instead of assumed.
    if not dry and not added and not window:
        print("\n".join(lines))
        print("\n[audit] EMPTY WINDOW — no new entries and no rolls since the last "
              "audit. NOT recorded and state unchanged: an empty window is not a "
              "quiet audit, and counting it as one would push the audit frequency "
              "down. Use --dry-run when you are testing this script.", file=sys.stderr)
        return 0

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
