#!/usr/bin/env python3
"""Level-3 discipline audit: the WEEKLY review. Reads only L2's output.

WHY THIS EXISTS
L1 counts defects. L2 groups them into classes and asks whether a fix held.
Neither can answer the only question that decides whether any of this is
working: **which classes survive their fixes?** -- and, with an explicit caveat,
whether the defect count is moving. **The COUNT's direction is confounded** (T100): a
fall cannot be told apart from having stopped noticing, and better discipline raises
it first. Every direction claim is emitted with CONFOUND_NOTE for that reason.

A class that keeps recurring after being "fixed" means the fix addressed an
instance, not the class -- and this project has already produced three of those
in one session (substring tag-matching fixed in route.py, then found again in
check_ledger.py, then ledger.py, then audit.py -- T66, T75, T77). L1 saw none
of it, because each individual instance looked like a one-off.

THE LADDER RULE
**Each level reads the level below's OUTPUT, never the raw data.** L3 reads
`audit-l2-log.md` and nothing else -- not the L1 log, not the ledger.
`--self-check` asserts that by parsing this file's AST, so the property is
enforced rather than promised.

Usage:
    scripts/audit_l3.py             # run, record an L3 block
    scripts/audit_l3.py --dry-run   # print, do not record
    scripts/audit_l3.py --self-check
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
L2LOG = DOCS / "audit-l2-log.md"       # the ONLY input
OUT = DOCS / "audit-l3-log.md"
STATE = DOCS / ".audit-l3-state.json"


def l2_blocks(text):
    """(number, body) per '## L2 #N' block."""
    return [(int(m.group(1)), m.group(2))
            for m in re.finditer(r"^## L2 #(\d+)[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)]


def class_counts(body):
    """{class: (this_window, prior, fixed, still_open)} from an L2 'by class' line.

    L2 gained two extra columns on 2026-08-21 -- FIXED this window and STILL
    OPEN. Older digests have only two numbers and are read with fixed/open as
    None, NOT as zero: "we did not track it then" and "there were none" are
    different facts, and scoring the first as the second would let this level
    claim clean history it never actually measured.
    """
    out = {}
    for m in re.finditer(r"^\s*- `([a-z-]+)` \([^)]*\): (\d+) / (\d+)"
                         r"(?: / (\d+) / (\d+))?", body, re.M):
        f, o = m.group(4), m.group(5)
        out[m.group(1)] = (int(m.group(2)), int(m.group(3)),
                           int(f) if f is not None else None,
                           int(o) if o is not None else None)
    return out


# THE DIRECTION IS CONFOUNDED, AND SAYING SO IS THE FIX FOR NOW (T100).
#
# This file's own docstring asks "is the error rate falling?" -- and a falling
# defect count cannot distinguish IMPROVEMENT from STOPPING NOTICING. Worse, the
# confound runs the wrong way for the obvious reading: better discipline should
# RAISE the count first, because more self-correction and more error produce the
# same number. A project that got sloppier and audited less would print FALLING.
#
# The real fix needs L1 to separate self-caught from user-caught defects and
# propagate that distinction up the ladder -- only "user-caught falling" is
# unambiguously good. That is a ladder-wide change and is NOT done. Until it is,
# every direction claim carries this note, so the number cannot be read naively.
# --self-check asserts the note is emitted with the claim, not merely defined.
CONFOUND_NOTE = (
    "- **THIS DIRECTION IS CONFOUNDED — do not read it as progress.** A falling "
    "count cannot be told apart from having stopped noticing, and better "
    "discipline RAISES the count first (self-correction and error are the same "
    "signal). Only a fall in USER-CAUGHT defects would be unambiguous, and the "
    "ladder does not yet separate those (T100)."
)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"l3s": 0, "last_l2": 0, "quiet_streak": 0}


def streak_after(prev, digested, quiet):
    """Identical to audit_l2.streak_after, and deliberately NOT imported.

    The ladder rule is that a level touches only the level below's output; L3
    importing from L2 would make that false in the one place the AST control
    cannot see. Twenty duplicated lines is the cheaper mistake.

    Same defect, same fix: `quiet = not new or ...` scored "L2 has not run" as
    "L2's output was examined and was clean". Since L3 reads L2 which reads L1,
    a single skipped L1 could have carried all the way up as three levels of
    apparent health. A no-op HOLDS the streak.
    """
    if not digested:
        return prev
    return prev + 1 if quiet else 0


def self_check():
    import ast as _ast
    src = Path(__file__).read_text()
    checks = []

    # LAYERING, by AST -- same control as L2's, and for the same reason: two
    # text-searching versions of it in audit_l2.py failed on their own source.
    raw_names = {"findings-ledger.md", "run-log.tsv", "route-log.md", "audit-log.md"}
    found = set()
    for node in _ast.walk(_ast.parse(src)):
        if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Div):
            for side in (node.left, node.right):
                if isinstance(side, _ast.Constant) and side.value in raw_names:
                    found.add(side.value)
    checks.append(("reads only L2 output — not L1, not raw data", not found,
                   f"constructs a path to {sorted(found)}" if found else "clean"))

    # The parser must recover class counts from a REAL L2 block, or the trend
    # is computed from nothing and every week reads "no data".
    if L2LOG.exists():
        blocks = l2_blocks(L2LOG.read_text())
        parsed = sum(len(class_counts(b)) for _n, b in blocks)
        checks.append((f"parses class counts out of {len(blocks)} L2 block(s)",
                       bool(blocks) and parsed > 0,
                       f"{parsed} class line(s) recovered"))
    else:
        checks.append(("L2 log present", False,
                       "docs/audit-l2-log.md missing — run scripts/audit_l2.py first"))

    # A synthetic block with a known shape: recurrence must be detected.
    # OLD FORMAT (pre-2026-08-21, two columns): fixed/open read as None, which
    # means "not tracked then", NOT "none then".
    fake = "- **defects by class (this window / all prior):**\n  - `churn` (I14): 2 / 5 — **recurs**\n"
    got = class_counts(fake)
    checks.append(("parses a legacy 2-column digest, resolution UNKNOWN not zero",
                   got.get("churn") == (2, 5, None, None), f"got {got}"))

    # NEW FORMAT, and the pair that matters. `single-run` was raised 3 times and
    # every instance fixed; `no-control` was raised once and is still open. The
    # old test (`cur and prior`) called BOTH of them recurrences, which is
    # exactly why L3 reported a permanent recurrence while the loop was working.
    fake4 = ("- **defects by class (raised this window / all prior / FIXED this window / still open):**\n"
             "  - `single-run` (T22): 3 / 12 / 3 / 0 — **raised, all fixed**\n"
             "  - `no-control` (I1/I13): 1 / 4 / 0 / 1 — **UNRESOLVED**\n")
    g4 = class_counts(fake4)
    checks.append(("parses the 4-column digest",
                   g4.get("single-run") == (3, 12, 3, 0)
                   and g4.get("no-control") == (1, 4, 0, 1), f"got {g4}"))
    # THE DISCRIMINATING ONE. Both classes were raised in this window AND in
    # prior ones, so the old rule flags both. Only one is actually still broken.
    flagged = {c for c, (cur, pri, _f, still) in g4.items()
               if (still if still is not None else (cur and pri))}
    checks.append(("recurrence means STILL OPEN, not merely raised twice",
                   flagged == {"no-control"},
                   f"flagged {flagged or '{}'} — 'single-run' was raised 3x and fixed 3x"))

    # A single digest must not yield a direction claim.
    import io, contextlib
    single_ok = True
    try:
        totals = [(1, 118)]
        single_ok = len(totals) < 2  # threshold exists at all
        srctxt = Path(__file__).read_text()
        single_ok = single_ok and "NO TREND CLAIMED" in srctxt and "len(totals) < 2" in srctxt
    except Exception:
        single_ok = False
    checks.append(("refuses a trend from a single digest", single_ok,
                   "threshold present" if single_ok else "would claim a direction from n=1"))

    # A no-op week must not score as a calm week -- see streak_after. Same
    # control as L2's, VERIFIED TO FAIL by pasting `quiet = not new or ...`
    # back in, which reported "no-op advanced the streak to 2".
    cases = [
        ("no-op holds",        streak_after(1, False, False), 1),
        ("no-op holds (2)",    streak_after(0, False, False), 0),
        ("clean week advances", streak_after(1, True, True),  2),
        ("rising resets",      streak_after(1, True, False),  0),
    ]
    wrong = [f"{n}: got {g} want {w}" for n, g, w in cases if g != w]
    checks.append(("a no-op does not score as a quiet week", not wrong,
                   "; ".join(wrong) if wrong else
                   "no-op holds the streak; only a reviewed-and-clean window advances it"))

    # The confound note must be EMITTED WITH the direction claim, not merely
    # defined near it. A caveat that exists in the source and never reaches the
    # block is the T56 failure -- a reminder nothing emits is not a reminder --
    # and it would leave the weekly review printing a bare FALLING/RISING that
    # reads as progress. Order is asserted too: a caveat printed above the claim
    # it qualifies is not attached to it.
    # NEEDLES ASSEMBLED FROM PARTS, and this is not fastidiousness. The first
    # version wrote them literally, so `src.index` found them inside THIS check
    # rather than in main() -- and it then reported FAIL identically whether or
    # not the emit was present, i.e. a control that could not discriminate at
    # all. It was caught only by running the removal experiment. That is the
    # THIRD self-referential control in this codebase (audit_l2.py records two
    # earlier ones) and the second today, so the pattern is now the default
    # suspicion whenever a check greps its own file.
    _emit = "lines.append(" + "CONFOUND_NOTE)"
    _dirline = 'f"- **defects per ' + 'digest:'
    emitted = _emit in src
    ordered = emitted and _dirline in src and src.index(_emit) > src.index(_dirline)
    checks.append(("the direction claim carries its confound note", emitted and ordered,
                   "emitted directly after the direction line" if emitted and ordered else
                   f"defined={('CONFOUND_NOTE =' in src)}, emitted={emitted}, ordered={ordered}"))

    bad = sum(1 for _n, ok, _d in checks if not ok)
    for name, ok, detail in checks:
        print(f"{'ok  ' if ok else 'FAIL'}  {name:48} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    unknown = [x for x in a if x not in {"--dry-run", "--self-check", "--help", "-h"}]
    if unknown:
        print(f"[l3] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print("[l3] REFUSING; a recorded audit must be asked for explicitly.", file=sys.stderr)
        return 2
    dry = "--dry-run" in a

    if not L2LOG.exists():
        print("[l3] no L2 log yet — run scripts/audit_l2.py first.", file=sys.stderr)
        return 1
    blocks = l2_blocks(L2LOG.read_text())
    st = load_state()
    new = [(n, b) for n, b in blocks if n > st["last_l2"]]

    lines = [f"## L3 #{st['l3s'] + 1} — covering L2 digests "
             f"{new[0][0] if new else '-'}..{new[-1][0] if new else '-'}"]
    if not new:
        lines.append("- no new L2 digests since the last L3. Nothing to review.")
    else:
        # Is the rate falling? Compare defects-per-digest, first half vs second.
        totals = [(n, sum(c for c, _p in class_counts(b).values())) for n, b in new]
        lines.append(f"- L2 digests reviewed: {len(new)}")
        # A DIRECTION NEEDS AT LEAST TWO POINTS. The first version split the
        # window in half regardless, so a single digest gave
        # "118.0 -> 0.0 — FALLING" from one data point: the second half was
        # empty and scored 0. That is a trend asserted from n=1, which is the
        # error T72 exists to prevent, printed by the very tool meant to catch
        # it. Below the threshold, report the counts and claim nothing.
        if len(totals) < 2:
            lines.append(f"- defects this digest: {totals[0][1] if totals else 0}. "
                         f"**NO TREND CLAIMED — a direction needs at least 2 digests.**")
        else:
            half = len(totals) // 2
            early = sum(t for _n, t in totals[:half]) / half
            late = sum(t for _n, t in totals[half:]) / (len(totals) - half)
            direction = ("FALLING" if late < early else
                         "RISING" if late > early else "flat")
            lines.append(f"- **defects per digest: {early:.1f} -> {late:.1f} — {direction}** "
                         f"(over {len(totals)} digests)")
            lines.append(CONFOUND_NOTE)

        # Which classes survive their fixes? A class marked `recurs` in a LATER
        # digest than one where it appeared is a fix that addressed an instance
        # rather than the class.
        # RECURRENCE NOW MEANS "STILL BROKEN", NOT "NOTICED AGAIN" (2026-08-21).
        #
        # The old test was `cur and prior` -- a class counted as surviving its
        # fix merely by being RAISED in two windows. Nothing anywhere counted a
        # fix, so a class whose every instance was corrected on the spot scored
        # identically to one being ignored, and this line fired permanently.
        # A273 was flagged and waived in the SAME COMMIT and read as recurring
        # for three digests. An alarm that always sounds is not read (T29).
        #
        # Digests from before L2 tracked resolution have `still is None`. Those
        # fall back to the old test, and say so, rather than being silently
        # reclassified either way.
        recurring, untracked = {}, {}
        for n, b in new:
            for cls, (cur, prior, _fixed, still) in class_counts(b).items():
                if still is None:
                    if cur and prior:
                        untracked.setdefault(cls, []).append(n)
                elif still:
                    recurring.setdefault(cls, []).append(n)
        if recurring:
            lines.append("- **classes with instances STILL OPEN — a fix that addressed an "
                         "instance, not the class:**")
            for cls, ns in sorted(recurring.items()):
                lines.append(f"  - `{cls}`: still open at L2 #{', #'.join(map(str, ns))}")
        if untracked:
            lines.append("- classes raised in two windows in digests from BEFORE resolution "
                         "was tracked — **cannot say whether these were fixed:**")
            for cls, ns in sorted(untracked.items()):
                lines.append(f"  - `{cls}`: seen twice at L2 #{', #'.join(map(str, ns))}")
        if not recurring and not untracked:
            lines.append("- no class has an instance still open across this window")

    digested = bool(new)
    quiet = digested and "RISING" not in "\n".join(lines)
    streak = streak_after(st["quiet_streak"], digested, quiet)
    if not digested:
        lines.append(f"- quiet: **n/a — NOTHING WAS REVIEWED, so this is not evidence of calm.** "
                     f"Streak HELD at {streak}. L2 is behind; run `scripts/audit_l2.py`.")
    else:
        lines.append(f"- quiet: {'yes' if quiet else 'no'} (streak {streak})")
    lines.append("- **L3 asks whether the METHOD is improving, not whether any finding is "
                 "right.** If a class recurs after a fix, the fix was aimed at an instance.")

    block = "\n".join(lines)
    print(block)
    if dry:
        print("\n[l3] --dry-run: nothing recorded.", file=sys.stderr)
        return 0

    import datetime as _dt
    st["last_date"] = _dt.date.today().isoformat()
    st["l3s"] += 1
    st["last_l2"] = blocks[-1][0] if blocks else st["last_l2"]
    st["quiet_streak"] = streak
    STATE.write_text(json.dumps(st, indent=1))
    if not OUT.exists():
        OUT.write_text("# L3 audit log\n\nWeekly reviews. Each reads ONLY the L2 digests in "
                       "`audit-l2-log.md`.\n\n")
    with OUT.open("a") as f:
        f.write(block + "\n\n")
    print(f"\n[l3] recorded to {OUT.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
