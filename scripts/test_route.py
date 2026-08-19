#!/usr/bin/env python3
"""Tests for route.py's frontier parsing.

WHY THIS EXISTS
route.py was the only tool in the handoff's FIRST FIVE MINUTES with no
self-test, and on 2026-08-19 it was the one that produced a wrong answer: it
decided openness with `"OPEN" in status.upper()`, so **A124** -- status cell
"READ -- ... answers A99's *open* question" -- was reported as an open frontier
item, and as UNPRICED, and therefore as a reason to distrust the whole ranking.

The important property is not "does it find the open rows" (the buggy version
did that fine). It is **does it reject the near-miss** -- prose containing the
word. A test that only asserts the positives would have passed against the bug,
and a control that cannot fail is not a control (T65). So POSITIVES and
NEGATIVES are asserted separately and the runner says so.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location("route", Path(__file__).resolve().parent / "route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)

OPEN_RE = route.OPEN_RE

# Verbatim status cells. The A124 line is the exact text that fooled the old
# version -- keep it verbatim; a paraphrase would not be the same test.
POSITIVE = [
    ("OPEN [cost=2] — **THE FRONTIER**", "A99, the live frontier"),
    ("OPEN [cost=4]", "bare tag with a cost"),
    ("OPEN", "bare tag alone"),
    ("**OPEN** [cost=3]", "bolded tag"),
    (" OPEN [cost=2]", "leading whitespace"),
]

NEGATIVE = [
    ("READ — static, cross-validated against the ROM; **answers A99's open question: "
     "what sets the walker's `$s0`**", "A124 VERBATIM — the bug this test exists for"),
    ("MEASURED — closes the open question in A122", "'open question' mid-sentence"),
    ("WD — superseded; was OPEN until roll #40", "withdrawn row citing its own history"),
    ("INFERRED — leaves one thing open", "'open' as an adjective at the end"),
    ("NEGATIVE(splat asm) — nothing reopens it", "'reopens' must not match"),
]


def main():
    fails = []
    for text, why in POSITIVE:
        if not OPEN_RE.match(text):
            fails.append(f"FAIL (missed an open row) {why}: {text[:60]!r}")
    for text, why in NEGATIVE:
        if OPEN_RE.match(text):
            fails.append(f"FAIL (false frontier)    {why}: {text[:60]!r}")

    # The discrimination check, run against the REAL ledger: the fix must change
    # the answer. If old and new agree, either the ledger no longer contains the
    # A124-shaped row or the anchor is not doing anything -- and in both cases
    # this file has stopped being evidence. Say so rather than passing quietly.
    ledger = Path(__file__).resolve().parent.parent / "docs" / "findings-ledger.md"
    old_hits, new_hits = set(), set()
    for line in ledger.read_text().split("\n"):
        m = re.match(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        if "OPEN" in m.group(2).upper():
            old_hits.add(m.group(1))
        if OPEN_RE.match(m.group(2)):
            new_hits.add(m.group(1))
    dropped = old_hits - new_hits
    gained = new_hits - old_hits
    if gained:
        fails.append(f"FAIL: anchoring ADDED rows, which it cannot legitimately do: {sorted(gained)}")

    # The checkpoint-closing requirement must survive in the roll output. It is
    # a standing user instruction (2026-08-19), and the reason it lives in a
    # tool rather than in a note is that notes are applied by the same judgement
    # that forgets them. Asserted here so that deleting it fails the FIRST FIVE
    # MINUTES rather than going unnoticed for a dozen checkpoints.
    req = getattr(route, "CLOSING_REQUIREMENT", "")
    src = (Path(__file__).resolve().parent / "route.py").read_text()
    if "plain-language sentence" not in req.lower():
        fails.append("FAIL: route.CLOSING_REQUIREMENT missing or reworded past recognition")
    elif "print(CLOSING_REQUIREMENT)" not in src:
        fails.append("FAIL: CLOSING_REQUIREMENT is defined but never printed — "
                     "a reminder nothing emits is not a reminder (cf. T56)")

    total = len(POSITIVE) + len(NEGATIVE) + 2
    if dropped:
        print(f"discrimination: OK — anchoring drops {sorted(dropped)} "
              f"({len(old_hits)} -> {len(new_hits)} open rows)")
    else:
        print("discrimination: NOTE — old and new agree on the current ledger. "
              "The unit negatives above still hold, but this ledger no longer "
              "contains a row that distinguishes them.")

    for f in fails:
        print(f)
    print(f"\n{total - len(fails)}/{total} correct "
          f"({len(POSITIVE)} positive, {len(NEGATIVE)} negative, 1 discrimination, "
          f"1 closing-requirement)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
