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
    # skip when the citing text says so -- otherwise every correction we make
    # trips its own alarm.
    supersedes = re.compile(
        r"(supersed|replaces|corrects|refut|retract|too coarse|withdraw|~~)", re.I)
    for eid, (tag, body, n) in rows.items():
        if "WD" in tag or supersedes.search(body):
            continue
        for w in sorted(withdrawn):
            if re.search(rf"(?<![\w./]){w}(?![\w./])", body):
                problems.append(
                    (n, f"{eid}: cites {w}, which is WITHDRAWN. "
                        f"Re-check whether {eid} still stands on its own."))
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

    # 4. routing decision overdue. This is what makes the explore/exploit roll
    # actually happen: findings accumulate constantly, so the nag surfaces on
    # its own rather than depending on remembering to roll.
    # Kept OUT of `problems`: this is a reminder, not a structural defect, and
    # --strict is used by daily_push.sh as a publish gate. A nag must never
    # block a push -- that conflates "you owe a routing roll" with "the ledger
    # is malformed", and the fix for the former is not to edit the ledger.
    reminders = []
    try:
        state = json.loads((LEDGER.parent / ".route-state.json").read_text())
        since = len(rows) - state.get("last_entry_count", 0)
        if since >= 6:
            reminders.append(f"routing: {since} entries added since roll "
                             f"#{state.get('roll', 0)} — run scripts/route.py.")
    except Exception:
        reminders.append("routing: no roll recorded yet — run scripts/route.py.")

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
