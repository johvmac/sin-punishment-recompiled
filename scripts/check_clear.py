#!/usr/bin/env python3
"""P7's checker, BUILT — it was designed 2026-08-26, run by hand, and left
unbuilt. It fired correctly by hand on the real staleness it was designed for,
and on 2026-08-28 the SAME staleness was back: the seed named
HANDOFF-2026-08-26.md while the live handoff was 2026-08-28, and its blocker
named A463, which had been SOLVED for a day. A check that has to be remembered
is a check that gets skipped.

THE THREE ASSERTIONS, and each is a file test rather than a judgement:

  1. The handoff named inside START-HERE.md's fenced block EXISTS, and is the
     NEWEST-DATED HANDOFF-*.md present. Not "exactly one is unsuperseded" --
     supersession is prose and unworkable; newest-dated-and-named is crisp.
  2. EXACTLY TWO «...» slots, counted ONLY INSIDE THE FENCE. The first draft
     counted file-wide and found four, because the marks appear in the prose
     that explains them. A check that counts its own documentation is measuring
     the wrong file.
  3. `ledger.py --open` is non-empty. A clear with an empty frontier leaves the
     router nothing to draw and the next session no way to start.

IT DELIBERATELY DOES NOT ASSERT that the handoff is accurate or that nothing is
mid-flight. Those are judgements, and T209 is this project's evidence that
dressing a judgement as a check yields a detector that fires on everything or
on nothing.

    scripts/check_clear.py              # run the three assertions
    scripts/check_clear.py --self-check # prove each can FAIL
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "docs" / "START-HERE.md"
FENCE = re.compile(r"^```\s*$", re.M)


def fenced_block(text):
    """The pasted message is the FIRST ``` ... ``` block. Everything outside it
    is documentation and must not be measured."""
    parts = FENCE.split(text)
    return parts[1] if len(parts) > 1 else ""


def check(seed_text, handoffs, open_rows):
    out, ok = [], True

    block = fenced_block(seed_text)
    if not block:
        return False, ["FAIL  no fenced block in START-HERE.md — nothing to paste"]

    # 1 — the named handoff exists and is the newest dated one
    m = re.search(r"«?(HANDOFF-\d{4}-\d{2}-\d{2}\.md)»?", block)
    if not m:
        out.append("FAIL  the seed names no HANDOFF-*.md at all")
        ok = False
    else:
        named = m.group(1)
        newest = max(handoffs) if handoffs else None
        exists = named in handoffs
        current = (named == newest)
        if exists and current:
            out.append(f"ok    seed names {named}, which exists and is newest")
        else:
            out.append(f"FAIL  seed names {named} — exists={exists} "
                       f"newest-on-disk={newest}")
            ok = False

    # 2 — exactly two slots, INSIDE the fence only
    n = len(re.findall("«", block))
    nc = len(re.findall("»", block))
    if n == 2 and nc == 2:
        out.append("ok    exactly two «…» slots inside the fenced block")
    else:
        out.append(f"FAIL  {n} opening and {nc} closing marks inside the fence, "
                   f"expected 2 and 2")
        ok = False

    # 3 — the frontier is not empty
    if open_rows > 0:
        out.append(f"ok    frontier has {open_rows} open row(s) for the router")
    else:
        out.append("FAIL  frontier is EMPTY — the next session cannot roll")
        ok = False

    return ok, out


def live():
    handoffs = {p.name for p in ROOT.glob("HANDOFF-*.md")}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "ledger.py"), "--open"],
                       capture_output=True, text=True)
    rows = [l for l in r.stdout.splitlines()
            if l.strip() and not l.startswith("#")]
    return SEED.read_text(), handoffs, len(rows)


def self_check():
    """Each assertion must FAIL on a broken input, not merely pass on a good
    one (T65). A control that cannot fail is not a control."""
    good_seed = "intro «…» prose\n\n```\nread «HANDOFF-2026-08-28.md» then «do the thing»\n```\n\ntail «…»\n"
    good = {"HANDOFF-2026-08-26.md", "HANDOFF-2026-08-28.md"}
    cases = [
        ("baseline passes", good_seed, good, 7, True),
        ("names a handoff that does NOT exist",
         good_seed.replace("2026-08-28", "2026-08-27"), good, 7, False),
        ("names a handoff that exists but is NOT newest",
         good_seed.replace("2026-08-28", "2026-08-26"), good, 7, False),
        ("only one slot inside the fence",
         good_seed.replace("«do the thing»", "do the thing"), good, 7, False),
        ("three slots inside the fence",
         good_seed.replace("```\nread", "```\n«extra» read"), good, 7, False),
        ("marks present only in the PROSE, none in the fence — must FAIL",
         "«a» «b»\n\n```\nread HANDOFF-2026-08-28.md\n```\n", good, 7, False),
        ("empty frontier", good_seed, good, 0, False),
    ]
    bad = 0
    for name, seed, hs, rows, expect in cases:
        got, _ = check(seed, hs, rows)
        hit = (got == expect)
        bad += not hit
        print(f"{'ok  ' if hit else 'FAIL'}  {name:52} — expected "
              f"{'PASS' if expect else 'FAIL'}, got {'PASS' if got else 'FAIL'}")
    print(f"\n{len(cases)-bad}/{len(cases)} self-check cases behave as specified")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(self_check())
    ok, lines = check(*live())
    for l in lines:
        print(l)
    print("\nP7 checker:", "PASS" if ok else "FAIL — do not clear yet")
    sys.exit(0 if ok else 1)
