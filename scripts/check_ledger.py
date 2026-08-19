#!/usr/bin/env python3
"""Structural checks on docs/findings-ledger.md.

WHY
---
About a dozen ledger entries were wrong in a single session on 2026-08-18. None
failed for lack of evidence -- every one cited real evidence, correctly
gathered. They failed because the CLAIM WAS BROADER THAN THE EVIDENCE.

This script cannot check that. No script can: a required field forces presence,
never truth, and "falsifier: none obvious" passes any validator. What it CAN do
is catch the STRUCTURAL half, which was a real chunk of the damage and needs no
judgement at all:

  1. Negatives with no stated scope.  "nothing calls this" was true of splat's
     asm and false of the ROM. Four failures, including a day spent believing a
     working probe was broken.
  2. Load-bearing claims missing a field.  Observed / Falsifier / Checked.
  3. Entries resting on a WITHDRAWN entry.  The highest-value check and the one
     that is not about discipline at all: B46 rested on B41, B41 was withdrawn,
     and B46 stayed standing as fact until someone happened to notice. Twice.
  4. Duplicate IDs.  Incremental edits produced six of them in one session.

Findings are WARNINGS, not gates. This is an attention-director; the judgement
stays with the reader. Exit 1 only with --strict.

Usage:
    scripts/check_ledger.py                 # check, print, exit 0
    scripts/check_ledger.py --strict        # exit 1 if anything is flagged
    scripts/check_ledger.py --hook          # read a Claude Code hook payload on
                                            # stdin; run only if the edited file
                                            # was the ledger. Exits 2 with the
                                            # report on stderr so it is surfaced.
"""
import json
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "docs" / "findings-ledger.md"

# A claim asserting an absence. These are the phrasings that actually burned us.
NEGATIVE = re.compile(
    r"\b(nothing|never|no other|zero (?:callers|hits|writes|gaps|matches)|"
    r"unreferenced|not called|does not exist|no such|none of)\b", re.I)

# A scope marker: says WHERE the search looked. Deliberately generous -- the aim
# is to catch claims with NO scope at all, not to police wording.
SCOPE = re.compile(
    r"(\bin\b|\bacross\b|\bwithin\b|\bthroughout\b|ROM-wide|`[^`]+`|"
    r"between t=|scope:)", re.I)

TAG_RE = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|(.*)$")
LB_RE = re.compile(r"^### (L\d+)\s+—\s+(.*)$")
REQUIRED_LB = ("Claim", "Observed", "Falsifier", "Checked")


def parse(text):
    """Return (rows, load_bearing). rows: id -> (tag, body, line). lb: id -> (fields, line)."""
    rows, lb = {}, {}
    dupes = []
    cur_lb = None
    for n, line in enumerate(text.split("\n"), 1):
        m = LB_RE.match(line)
        if m:
            cur_lb = m.group(1)
            lb[cur_lb] = {"fields": set(), "body": [], "line": n, "title": m.group(2)}
            continue
        if cur_lb and line.startswith("- **"):
            f = re.match(r"- \*\*(\w+)", line)
            if f:
                lb[cur_lb]["fields"].add(f.group(1))
            lb[cur_lb]["body"].append(line)
            continue
        if line.startswith("###") or line.startswith("## "):
            cur_lb = None
        m = TAG_RE.match(line)
        if m:
            eid, tag, body = m.group(1), m.group(2), m.group(3)
            if eid in rows:
                dupes.append((eid, n, rows[eid][2]))
            else:
                rows[eid] = (tag, body, n)
    return rows, lb, dupes


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    hook = "--hook" in sys.argv
    if hook:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return 0
        path = (payload.get("tool_input") or {}).get("file_path", "")
        if "findings-ledger" not in str(path):
            return 0

    if not LEDGER.exists():
        return 0
    text = LEDGER.read_text()
    rows, lb, dupes = parse(text)

    withdrawn = {i for i, (tag, _, _) in rows.items() if "WD" in tag}
    problems = []

    # 1. negatives without a scope
    for eid, (tag, body, n) in rows.items():
        if "WD" in tag or "OPEN" in tag:
            continue
        if NEGATIVE.search(body) and not SCOPE.search(body):
            problems.append(
                (n, f"{eid}: asserts an absence with no stated scope. "
                    f"Say WHERE you looked, inside the claim."))

    # 2. load-bearing completeness
    for lid, d in lb.items():
        missing = [f for f in REQUIRED_LB if f not in d["fields"]]
        if missing:
            problems.append(
                (d["line"], f"{lid}: load-bearing claim missing {', '.join(missing)}."))

    # 3. resting on a withdrawn entry.
    # An entry that IS the replacement legitimately names what it replaced, so
    # a correction-word excuses the citation it sits beside.
    #
    # T48: that exemption used to be tested against the WHOLE ROW. Rows here run
    # to thousands of characters, so one "refuted" anywhere -- or a `~~` used as
    # plain strikethrough -- switched the check off for every citation in the
    # row, permanently. 62 of 185 rows were exempt, including the B46 case this
    # check's own docstring cites as its reason for existing. Found the same way
    # as T40: an honest annotation on T17 silenced the alarm, and the words that
    # did it were prose, not a claim the checker understood.
    #
    # So the word must sit NEAR the citation it excuses. Same fix as T40's --
    # narrow the scope of the predicate to the thing it describes. The window is
    # deliberately generous (a long sentence) but is a small fraction of a row.
    supersedes = re.compile(
        r"(supersed|replaces|corrects|refut|retract|too coarse|withdr|~~)", re.I)
    NEAR = 150
    for eid, (tag, body, n) in rows.items():
        if "WD" in tag:
            continue
        for w in sorted(withdrawn):
            for m in re.finditer(rf"(?<![\w./]){w}(?![\w./])", body):
                window = body[max(0, m.start() - NEAR):m.end() + NEAR]
                if supersedes.search(window):
                    continue
                problems.append(
                    (n, f"{eid}: cites {w}, which is WITHDRAWN. "
                        f"Re-check whether {eid} still stands on its own."))
                break
    for lid, d in lb.items():
        joined = "\n".join(d["body"])
        for w in sorted(withdrawn):
            if re.search(rf"(?<![\w./]){w}(?![\w./])", joined):
                problems.append(
                    (d["line"], f"{lid}: load-bearing claim cites WITHDRAWN {w}."))

    # 3b. citing an entry that DOES NOT EXIST.
    # B36 rested on "B35's derived unpack addresses" for its whole life; the only
    # occurrence of B35 in the ledger was that citation. A dangling reference is
    # worse than a withdrawn one -- a withdrawn entry at least records what was
    # believed and why it fell, whereas this looks like support and is nothing.
    # Bare IDs only (A12, B7, T3, I9, L2); anything with other text around it,
    # like a hex address, is left alone.
    # ROADMAP.md defines its own IDs (A26, B31, T11 ...) and the ledger legitimately
    # cross-references them, so those are not dangling.
    known = set(rows) | set(lb)
    roadmap = LEDGER.parent / "ROADMAP.md"
    if roadmap.exists():
        known |= set(re.findall(r"^\*\*([ABTIL]\d{1,3}[a-z]?)\s+—",
                                roadmap.read_text(), re.M))
    # Archived entries still exist -- they just live elsewhere. Counting them as
    # known is what makes archiving safe; without this the first archive pass
    # would manufacture dozens of dangling citations (T21).
    for arch in LEDGER.parent.glob("findings-archive-*.md"):
        known |= set(re.findall(r"^\|\s*([ABTIL]\d{1,3}[a-z]?)\s*\|",
                                arch.read_text(), re.M))
    ref_re = re.compile(r"(?<![\w./])([ABTIL]\d{1,3}[a-z]?)(?![\w./])")
    # An entry that RECORDS a dangling reference has to name it; don't flag that.
    names_gap = re.compile(r"(does not exist|never existed|has never existed|dangling)", re.I)
    for eid, (tag, body, n) in rows.items():
        if names_gap.search(body):
            continue
        for ref in set(ref_re.findall(body)):
            if ref != eid and ref not in known:
                problems.append(
                    (n, f"{eid}: cites {ref}, which DOES NOT EXIST in this ledger. "
                        f"Either the entry was never written or the ID is wrong."))

    # 3c. malformed cost annotation in the STATUS column.
    #
    # scripts/route.py ranks open work by parsing exactly `[cost=N]`. Anything
    # else silently drops the row OUT of the ranking. On 2026-08-19 a re-cost was
    # written `[cost=3, was 4]` -- readable to a human, invisible to the parser --
    # and T11 vanished from the cost ranking while THIS script still said "OK".
    # route.py noticed and said UNPRICED; the automatic gate did not. That is the
    # wrong way round: the hook fires on every ledger edit, route.py only when
    # someone runs it.
    #
    # Only the status column is inspected, never the body -- prose legitimately
    # says "cost days" or "re-costed", and policing that would be noise.
    cost_ok = re.compile(r"\[cost=\d+\]")
    mentions_cost = re.compile(r"cost", re.I)
    for eid, (tag, body, n) in rows.items():
        if mentions_cost.search(tag) and not cost_ok.search(tag):
            problems.append(
                (n, f"{eid}: malformed cost in the status column -> '{tag.strip()}'. "
                    f"route.py parses exactly [cost=N] (digits only); anything else "
                    f"drops this row out of the ranking as UNPRICED, silently. "
                    f"Use [cost=N] and put any history in the finding text."))
        elif "OPEN" in tag and not cost_ok.search(tag):
            problems.append(
                (n, f"{eid}: OPEN but carries no [cost=N], so route.py cannot rank "
                    f"it and sorts it last. Price it, or the ordering is not a ranking."))

    # 4. routing decision overdue. This is what makes the explore/exploit roll
    # actually happen: findings accumulate constantly, so the nag surfaces on
    # its own rather than depending on remembering to roll.
    # Kept OUT of `problems`: this is a reminder, not a structural defect, and
    # --strict is used by daily_push.sh as a publish gate. A nag must never
    # block a push -- that conflates "you owe a routing roll" with "the ledger
    # is malformed", and the fix for the former is not to edit the ledger.
    reminders = []

    # 3d. entry LENGTH. This is the one that actually controls the file's size,
    # and it went unmeasured for two days while the size threshold pointed at
    # archiving instead.
    #
    # Measured 2026-08-19 (T51): the 2026-08-18 entries average 112 words and
    # top out at 324. The 2026-08-19 entries average 398 and top out at 846 --
    # 3.6x, for the same kind of content. 43 entries were 25% of the ledger by
    # count and 55% by words. Archiving 26 rows of genuine history recovered
    # 1,037 words; compressing one session's prose was worth ~12,000.
    #
    # So the file does not grow because findings accumulate. It grows because
    # entries get written long, and that is visible AT WRITE TIME with no
    # hindsight at all -- unlike archiving, which needs to know what turned out
    # to matter (T46).
    #
    # A warning, never a gate. Some entries have earned their length: a
    # correction that must stop a resurrection, or a load-bearing claim with its
    # controls. The check exists so that length is a DECISION rather than an
    # accident, which is all it was on 2026-08-19.
    LONG = 250
    long_rows = sorted(((len(b.split()), e) for e, (t, b, n) in rows.items()
                        if len(b.split()) > LONG), reverse=True)
    if long_rows:
        worst = ", ".join(f"{e} ({w}w)" for w, e in long_rows[:5])
        reminders.append(
            f"LENGTH: {len(long_rows)} entr{'y' if len(long_rows)==1 else 'ies'} "
            f"over {LONG} words ({sum(w for w, _ in long_rows):,} words total). "
            f"Longest: {worst}. Median entry is ~124w and carries claim, status, "
            f"evidence and falsifier fine. Trim, or decide the length is earned.")

    # Ledger size. The file is meant to be read IN FULL at session start, so its
    # cost is paid every time; past ~30k words that starts crowding out the work
    # it exists to serve. Measured 2026-08-18 at 194 entries / 18.9k words, with
    # the A-series (a now-resolved investigation, closed by L7) accounting for
    # 62% of it -- so the first archive pass is cheap and obvious.
    # NOT a structural problem, so it stays out of `problems` and cannot block
    # daily_push.sh: "the ledger is long" is not "the ledger is malformed".
    words = len(text.split())
    if words >= 35000:
        reminders.append(f"SIZE: {words:,} words — well past the 30k archive "
                         f"threshold. Archive a resolved investigation now.")
    elif words >= 30000:
        reminders.append(f"SIZE: {words:,} words — past the 30k threshold. "
                         f"Archive the supporting entries of a CLOSED investigation "
                         f"to docs/findings-archive-<topic>.md, leaving one index "
                         f"line. Never archive WITHDRAWN, I-series or T-series rows.")
    try:
        state = json.loads((LEDGER.parent / ".route-state.json").read_text())
        since = len(rows) - state.get("last_entry_count", 0)
        if since >= 6:
            reminders.append(f"routing: {since} entries added since roll "
                             f"#{state.get('roll', 0)} — run scripts/route.py.")
    except Exception:
        reminders.append("routing: no roll recorded yet — run scripts/route.py.")

    # 4b. the L1 audit had NO trigger at all -- it fired only when someone
    # remembered, which is precisely the failure mode the audit exists to catch.
    # Every discipline left to memory on this project has failed at least once
    # (T26), so hang it off the one hook that always runs.
    try:
        ast_ = json.loads((LEDGER.parent / ".audit-state.json").read_text())
        st_ = json.loads((LEDGER.parent / ".route-state.json").read_text())
        due = st_.get("roll", 0) - ast_.get("last_roll", 0)
        if due >= 10:
            reminders.append(f"audit: {due} rolls since audit #{ast_.get('audits', 0)} "
                             f"— run scripts/audit.py (due every ~10).")
    except Exception:
        reminders.append("audit: no audit recorded yet — run scripts/audit.py.")

    # 5. duplicate ids
    for eid, n, first in dupes:
        problems.append((n, f"{eid}: duplicate ID (first seen line {first}). "
                            f"Merge; one ID, one current status."))

    out = sys.stderr if hook else sys.stdout
    for r in reminders:
        print(f"[ledger] note — {r}", file=out)
    if not problems:
        print(f"[ledger] OK — {len(rows)} entries, {len(lb)} load-bearing, "
              f"{len(withdrawn)} withdrawn.", file=out)
        return 0

    print(f"[ledger] {len(problems)} thing(s) to look at "
          f"({len(rows)} entries, {len(lb)} load-bearing):", file=out)
    for n, msg in sorted(problems):
        print(f"  {LEDGER.name}:{n}: {msg}", file=out)
    print("  (warnings, not errors — judgement stays with the reader)", file=out)

    if hook:
        return 2      # surfaces the report back to Claude
    return 1 if "--strict" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
