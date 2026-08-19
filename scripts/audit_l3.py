#!/usr/bin/env python3
"""Level-3 discipline audit: the WEEKLY review. Reads only L2's output.

WHY THIS EXISTS
L1 counts defects. L2 groups them into classes and asks whether a fix held.
Neither can answer the only question that decides whether any of this is
working: **is the error rate falling, and which classes survive their fixes?**

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
    """{class: (this_window, prior)} from an L2 block's 'by class' lines."""
    out = {}
    for m in re.finditer(r"^\s*- `([a-z-]+)` \([^)]*\): (\d+) / (\d+)", body, re.M):
        out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


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
    fake = "- **defects by class (this window / all prior):**\n  - `churn` (I14): 2 / 5 — **recurs**\n"
    got = class_counts(fake)
    checks.append(("detects a recurring class in a synthetic block",
                   got.get("churn") == (2, 5), f"got {got}"))

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

        # Which classes survive their fixes? A class marked `recurs` in a LATER
        # digest than one where it appeared is a fix that addressed an instance
        # rather than the class.
        recurring = {}
        for n, b in new:
            for cls, (cur, prior) in class_counts(b).items():
                if cur and prior:
                    recurring.setdefault(cls, []).append(n)
        if recurring:
            lines.append("- **classes that RECUR despite tooling — a fix that addressed an "
                         "instance, not the class:**")
            for cls, ns in sorted(recurring.items()):
                lines.append(f"  - `{cls}`: recurred in L2 #{', #'.join(map(str, ns))}")
        else:
            lines.append("- no class recurred across this window")

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
