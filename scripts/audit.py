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
    """id -> (status, body, evidence).

    ROWS UNDER A NON-ENTRY HEADING ARE SKIPPED, using check_ledger's OWN
    definition rather than a second copy. Fixed 2026-08-22 (T171): this counted
    the 9 user-queue rows as ledger entries, so every audit header reported 548
    where check_ledger reported 539. check_ledger's comment names this exact
    failure -- "two definitions would let a row be an entry for one tool and not
    for another and nobody could say which was authoritative" (T121) -- and
    audit.py already imports SUPERSEDES_RE from there. This closes the gap.
    """
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_cl_rows", Path(__file__).resolve().parent / "check_ledger.py")
    _cl = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_cl)

    out = {}
    skipping = False
    for line in text.split("\n"):
        if line.startswith("## "):
            skipping = _cl.is_non_entry_section(line)
            continue
        if skipping:
            continue
        m = ROW.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = (m.group(2), m.group(3), m.group(4))
    return out


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"audits": 0, "last_rev": "", "last_roll": 0, "quiet_streak": 0,
            "open": {}}


# ---------------------------------------------------------------------------
# RESOLUTION TRACKING (2026-08-21, user-directed)
#
# THE PROBLEM THIS FIXES. L1 examines only entries ADDED since the last audit,
# so a finding is emitted exactly once and never mentioned again -- whether it
# was fixed in the next commit or ignored for a week. L2 groups those emissions
# into classes and L3 reports which classes "recur". **Nothing anywhere counted
# a fix.** So a class whose every instance was corrected on the spot looks
# identical to one being ignored, and L3's "this class recurs despite tooling"
# fires permanently. An alarm that always sounds stops being heard (T29).
#
# The concrete case: audit #14 flagged A273 as resting on one run, and the SAME
# COMMIT added its "ONE RUN IS ENOUGH" waiver. Fixed immediately, counted as a
# recurrence three digests running.
#
# WHICH FINDINGS CAN BE CARRIED, and this distinction is the whole design:
#
#   * RESOLVABLE -- a property of an entry's CURRENT text, so re-reading the
#     row answers whether it still holds. single-run, no-control, no-evidence.
#     These are carried until they stop being true.
#   * HISTORICAL -- a fact about something that already happened, which no edit
#     can undo. `churn` is "created AND withdrawn inside one window"; the entry
#     stays withdrawn forever. Carrying it would manufacture an eternal finding,
#     which is the exact failure being fixed.
#   * TRANSIENT -- a property of a window or of the world right now: explore
#     ratio, contaminated runs, the cron state. Next audit measures its own
#     window; carrying last window's is meaningless.
#
# Only RESOLVABLE findings are carried. The other two are reported and dropped,
# and this comment exists so that is a decision rather than an oversight.
# ---------------------------------------------------------------------------

def is_single_run(status, body, ev):
    """The predicate behind the single-run finding, minus supersession.

    Factored out so it can be re-applied to an entry that is no longer in the
    audit window -- which is what "was it fixed?" requires.
    """
    if not re.search(r"MEASURED|INTERVENED", status):
        return False
    logs = re.findall(r"[\w.-]+\.log", ev + " " + body)
    if len(set(logs)) != 1:
        return False
    if re.search(r"\b(\d+|two|three|both)\s+runs?\b", ev + " " + body, re.I):
        return False
    if re.search(r"ONE RUN[,:]?\s*(IS ENOUGH|and (the )?reason)", ev + " " + body, re.I):
        return False
    return True


def is_no_evidence(status, body, ev):
    return (not OPEN_RE.match(status) and not WD_RE.match(status)
            and not ev.strip())


# Set by main() once the module-level regexes for the control check exist.
# Kept as a hook rather than duplicating those patterns: two definitions of
# "mentions a control" would let an entry be flagged by one and cleared by the
# other, which is the failure the single-run comment already warns about.
_no_control_pred = None


def is_no_control(status, body, ev):
    return bool(_no_control_pred and _no_control_pred(status, body, ev))


RESOLVABLE = {
    "single-run": is_single_run,
    "no-evidence": is_no_evidence,
    "no-control": is_no_control,
}


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
    opened = []          # (class, entry-id) raised THIS window; carried forward

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
            opened.append(("single-run", eid))

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
    # ONE definition, shared with the resolution re-check above (T121). Bound
    # here because the patterns are local to this function.
    global _no_control_pred

    def _nc(status, body, ev):
        if ZERO_RUNS.search(status + body + ev) or POINTER.match(status.strip()):
            return False
        return bool(DEPLOYED.search(body) and not CONTROL.search(body + ev))
    _no_control_pred = _nc

    for eid, (status, body, ev) in added.items():
        if _nc(status, body, ev):
            findings.append(f"{eid}: describes a probe with no control mentioned. A dead probe reads as a clean negative.")
            opened.append(("no-control", eid))

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
        if is_no_evidence(status, body, ev):
            findings.append(f"{eid}: no evidence recorded. Say what was observed and when.")
            opened.append(("no-evidence", eid))

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
        # MEASURE THE STATE, NOT THE LOG'S LAST LINE (T196).
        #
        # This used to fire on "REFUSING" in the last line alone. That line
        # reflects the last CRON run, and the cron is the only writer -- so a
        # refusal FIXED BY HAND kept alarming until 18:30 the next day, and an
        # alarm that cannot clear cannot distinguish "fixed" from "still
        # broken". It is the same cry-wolf shape as the status-page marker
        # (T195) and the exclusion list (T194): a signal derived from a record
        # rather than from the thing itself.
        #
        # The thing itself is: are there commits the remote does not have?
        try:
            _unpushed = int(subprocess.run(
                ["git", "rev-list", "--count", "fork/main..HEAD"], cwd=ROOT,
                capture_output=True, text=True, check=True).stdout.strip())
        except Exception:
            _unpushed = -1          # unknown; fall back to the log-only signal
        _refused = ("REFUSING" in last or "error" in last.lower()
                    or "fatal" in last.lower())
        # REPORT THE FACTS; DO NOT DIAGNOSE FROM A STALE LOG.
        #
        # A first version of this said "push is STUCK" whenever the last line
        # refused and anything was unpushed. That over-claims in exactly the way
        # this fix exists to stop: the refusal may have been repaired by hand
        # hours ago, and unpushed commits are NORMAL between nightly runs. The
        # audit cannot tell a live failure from a repaired one without running
        # the gate, and running the gate stages files -- a side effect an audit
        # must not have. So it states both facts and names the command that
        # settles it.
        if _refused:
            if _unpushed == 0:
                findings.append(
                    "cron: the push log's last line is a refusal, but NOTHING is "
                    "unpushed — repaired since; the log clears at the next 18:30 run.")
            else:
                findings.append(
                    f"cron: last logged run refused ({last[:60]}) and {_unpushed} "
                    f"commit(s) are unpushed. **This may be history** — commits "
                    f"accumulate normally between nightly runs. Settle it with "
                    f"`scripts/daily_push.sh --dry-run`.")

    # THE SECOND CRON JOB, added 2026-08-21 when the Drive backup was scheduled
    # at 18:45. Same reasoning as the block above and it must not be left out:
    # the backup carries the ONLY off-machine copy of the probe patches, which
    # cannot go to GitHub at all (T36/T38). A nightly job whose log nobody reads
    # is a signal with no reader, and this one fails silently in the ways that
    # matter most -- an expired OAuth token, the archive drive unmounted, or a
    # probe patch failing its reverse-apply check and aborting the run.
    #
    # THIS LIST IS DECLARED, NOT DISCOVERED, and that is a known weakness rather
    # than an oversight: reading the crontab would break this script's own rule
    # that it touches only structured PROJECT data (see the docstring). So a
    # THIRD scheduled job would go unwatched until someone adds it here.
    bkp_log = ROOT / "scripts" / "backup_drive.log"
    if bkp_log.exists():
        b_age = (_now_dt - _dt.datetime.fromtimestamp(bkp_log.stat().st_mtime)).days
        b_lines = [l for l in bkp_log.read_text().strip().split("\n") if l.strip()]
        b_last = b_lines[-1] if b_lines else ""
        b_stale = 0 if _now_dt.hour > 18 or (_now_dt.hour == 18 and _now_dt.minute >= 50) else 1
        if b_age > b_stale:
            findings.append(f"cron: backup_drive.log is {b_age}d old — the 18:45 Drive "
                            f"backup may not be running. It holds the only off-machine "
                            f"copy of the probe patches.")
        if "REFUSING" in b_last or "FAILED" in b_last or "NOTHING SENT" in b_last:
            findings.append(f"cron: last Drive backup did not complete — {b_last[:90]}")
        elif b_lines and not any("done --" in l for l in b_lines[-6:]):
            findings.append("cron: the last Drive backup did not print its completion "
                            "line. It may have died partway; check scripts/backup_drive.log.")

    # --- resolution pass -----------------------------------------------------
    # Re-apply each carried finding's predicate to the entry's CURRENT row. This
    # is the step that lets a fix be counted, and it deliberately ignores the
    # audit window: the whole point is to look at entries that left it.
    #
    # An entry that has VANISHED from the ledger is NOT resolved -- it is
    # unreadable, and calling that a fix would let deletion clear the record.
    # It is reported separately so it cannot be mistaken for either.
    carried = st.get("open", {})
    resolved, still_open, vanished = [], [], []
    for key, meta in sorted(carried.items()):
        cls, eid = meta["cls"], meta["eid"]
        pred = RESOLVABLE.get(cls)
        row = now.get(eid)
        if row is None:
            vanished.append(f"{eid} ({cls}, raised #{meta['since']})")
        elif pred is None or not pred(*row):
            resolved.append(f"{eid} ({cls}, open since #{meta['since']})")
        else:
            still_open.append(f"{eid} ({cls}, open since #{meta['since']}, "
                              f"{st['audits'] + 1 - meta['since']} audit(s))")

    new_open = {k: v for k, v in carried.items()
                if any(s.startswith(v["eid"] + " ") for s in still_open)}
    for cls, eid in opened:
        new_open[f"{cls}:{eid}"] = {"cls": cls, "eid": eid, "since": st["audits"] + 1}

    lines = [f"## Audit #{st['audits'] + 1} — since {since[:8] or 'start'}",
             f"- ledger: {len(now)} entries (+{len(added)} this window), "
             f"{sum(1 for s, _, _ in now.values() if WD_RE.match(s))} withdrawn",
             f"- rolls: {len(window)} this window; runs: {len(recent)} "
             f"({len(crashed)} exited early, {len(dirty)} contaminated)"]
    if findings:
        lines.append(f"- **{len(findings)} thing(s) to look at:**")
        lines += [f"  - {f}" for f in findings]
    # RESOLUTIONS ARE REPORTED EVEN WHEN NOTHING ELSE IS. A level that only ever
    # prints problems teaches its reader that the number can only go up, which
    # is precisely how L3 came to report a permanent recurrence.
    if resolved:
        lines.append(f"- **resolved since last audit ({len(resolved)}):** " + "; ".join(resolved))
    if still_open:
        lines.append(f"- **STILL OPEN from earlier audits ({len(still_open)}):** " + "; ".join(still_open))
    if vanished:
        lines.append(f"- gone from the ledger, NOT counted as fixed ({len(vanished)}): "
                     + "; ".join(vanished))
    if suppressed:
        # NAMED, NEVER SILENT. A suppression rule that hides its own work is
        # indistinguishable from a broken check, and "the audit found nothing"
        # would then be unfalsifiable. Same reason lint_tools.py prints its
        # known debt every run.
        lines.append(f"- suppressed as superseded ({len(suppressed)}): "
                     + "; ".join(suppressed))
    # THIS `else` WAS ATTACHED TO `suppressed`, NOT `findings` (fixed
    # 2026-08-21). An audit with findings but no suppressions printed BOTH
    # "1 thing(s) to look at" AND "nothing flagged", one line apart. The
    # quiet-streak COUNTER was always computed from `findings` and so was
    # right; only the sentence a human reads was wrong -- which is the worse
    # half, because L2 reads this file and a reader who sees a level contradict
    # itself stops trusting the level (T29).
    if not findings:
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
        st["open"] = new_open
        STATE.write_text(json.dumps(st, indent=1))
        if not OUT.exists():
            OUT.write_text("# Audit log\n\nLevel-1 discipline audits. The daily "
                           "review reads THIS file, not the raw data.\n\n")
        with OUT.open("a") as f:
            f.write("\n".join(lines) + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
