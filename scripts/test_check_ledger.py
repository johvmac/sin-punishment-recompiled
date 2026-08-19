#!/usr/bin/env python3
"""Positive/negative controls for check_ledger.py's cost-annotation check (T41).

Runs against TEMPORARY COPIES of the real ledger, never the file itself -- the
same rule T32 used when verifying the size thresholds. Each case injects one row
into a copy, runs the checker against it, and asserts whether that row is
flagged.

    scripts/test_check_ledger.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"
CHECKER = ROOT / "scripts" / "check_ledger.py"

# (row to inject, should_be_flagged, label)
CASES = [
    ("| ZZ1 | OPEN [cost=3, was 4] | Re-costed thing | 2026-01-01 |",
     True,  "THE BUG: trailing text inside the brackets"),
    ("| ZZ1 | OPEN [cost=?] | Unknown cost | 2026-01-01 |",
     True,  "non-numeric cost"),
    ("| ZZ1 | OPEN cost=3 | Missing brackets | 2026-01-01 |",
     True,  "cost without brackets"),
    ("| ZZ1 | OPEN [cost = 3] | Spaces inside | 2026-01-01 |",
     True,  "spaces break the parser"),
    ("| ZZ1 | OPEN | Unpriced open item | 2026-01-01 |",
     True,  "OPEN with no cost at all"),

    ("| ZZ1 | OPEN [cost=3] | Well formed | 2026-01-01 |",
     False, "valid cost"),
    ("| ZZ1 | OPEN [cost=12] — **THE FRONTIER** | Valid, decorated | 2026-01-01 |",
     False, "valid cost with trailing decoration outside the brackets"),
    ("| ZZ1 | MEASURED | A finding that cost days to reach | 2026-01-01 |",
     False, "the word 'cost' in the BODY must not trip it"),
    ("| ZZ1 | INTERVENED | Re-costed T11 from 4 to 3 | 2026-01-01 |",
     False, "'re-costed' in the body must not trip it"),

    # --- check 3: resting on a WITHDRAWN entry (T48) ---------------------
    # These inject TWO rows: ZZ9 is withdrawn, ZZ1 may or may not cite it.
    # The cases that matter are the FAR ones. Before T48 the exemption was
    # matched against the whole row, so a correction-word anywhere -- even
    # `~~` used as plain strikethrough -- silenced every citation in it.
    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | This rests on ZZ9 and says nothing about why | 2026-01-01 |",
     True,  "POSITIVE CONTROL: plain citation of a withdrawn entry"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | This supersedes ZZ9 | 2026-01-01 |",
     False, "the replacement legitimately names what it replaced"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | Something here was refuted. {'padding text ' * 20}"
     f"and separately this rests on ZZ9 | 2026-01-01 |",
     True,  "THE T48 BUG: 'refuted' far from the citation must NOT exempt it"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | ~~struck out note~~ {'padding text ' * 20}"
     f"and this rests on ZZ9 | 2026-01-01 |",
     True,  "THE T48 BUG: distant `~~` markup must NOT exempt a citation"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | A standalone finding whose text uses the word "
     f"refuted but cites no retired entry | 2026-01-01 |",
     False, "correction-word with no withdrawn citation must not flag"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | WD | This cites ZZ9 but is itself withdrawn | 2026-01-01 |",
     False, "a withdrawn row citing a withdrawn row is not a problem"),

    # --- MERGED stubs must point somewhere real (T53) ---------------------
    # A stub that names a missing target manufactures T21's dangling citation
    # out of our own housekeeping, which is why this is checked rather than
    # trusted. The must-NOT-flag case matters equally: merging is allowed.
    ("| ZZ1 | **MERGED into ZZ8 (2026-01-01)** | Folded away | 2026-01-01 |",
     True,  "THE RISK: stub names a target that does not exist"),

    ("| ZZ1 | **MERGED** | Folded away but says nothing about where | 2026-01-01 |",
     True,  "stub with no target named at all"),

    (f"| ZZ8 | MEASURED | class entry that absorbed ZZ1 | 2026-01-01 |\n"
     f"| ZZ1 | **MERGED into ZZ8 (2026-01-01)** | Folded away | 2026-01-01 |",
     False, "a stub naming an existing target is fine"),
]

ANCHOR = "## Tools and methods"


def run_case(row, tmpdir):
    """Inject `row` into a copy of the ledger; return the checker's output."""
    copy = Path(tmpdir) / "findings-ledger.md"
    text = LEDGER.read_text()
    assert ANCHOR in text, "anchor missing from ledger"
    text = text.replace(ANCHOR, f"{ANCHOR}\n\n| # | status | finding |\n|---|---|---|\n{row}\n", 1)
    docs = Path(tmpdir)
    copy.write_text(text)
    # check_ledger resolves the ledger relative to its own parent's parent, so
    # give the copy that same shape: <tmp>/scripts/check_ledger.py + <tmp>/docs/
    fake_root = Path(tmpdir).parent / "fakeroot"
    shutil.rmtree(fake_root, ignore_errors=True)
    (fake_root / "scripts").mkdir(parents=True)
    (fake_root / "docs").mkdir(parents=True)
    shutil.copy(CHECKER, fake_root / "scripts" / "check_ledger.py")
    (fake_root / "docs" / "findings-ledger.md").write_text(text)
    p = subprocess.run([sys.executable, str(fake_root / "scripts" / "check_ledger.py")],
                       capture_output=True, text=True)
    return p.stdout + p.stderr


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    if not LEDGER.exists():
        print("[test] no ledger", file=sys.stderr)
        return 1

    before = LEDGER.read_bytes()
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        for row, should_flag, label in CASES:
            out = run_case(row, td)
            flagged = bool(re.search(r"^\s*\S*findings-ledger\.md:\d+: ZZ1:", out, re.M))
            ok = flagged == should_flag
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'}  flagged={flagged!s:<5} want={should_flag!s:<5} {label}")

    # --- check 3d: entry length (T51) -------------------------------------
    # Not a CASES entry: the length finding is a REMINDER, so it carries no
    # "file:line: ID:" prefix and the flag regex above cannot see it. Asserting
    # both directions here is the point -- a checker that fired on every row
    # would be ignored within a day (T29), so the short case matters as much as
    # the long one.
    with tempfile.TemporaryDirectory() as td:
        long_row = "| ZZ2 | MEASURED | " + ("padding " * 300) + "| 2026-01-01 |"
        short_row = "| ZZ2 | MEASURED | " + ("padding " * 40) + "| 2026-01-01 |"
        # Assert on the COUNT, not on the name. The reminder only names the
        # five longest, so a 300-word probe row is invisible beside the real
        # ledger's 800-word entries -- the first version of this test asserted
        # on the name and failed for that reason, not because the check was
        # broken. Counting is what the check actually claims.
        def n_long(out):
            m = re.search(r"LENGTH: (\d+) entr", out)
            return int(m.group(1)) if m else 0
        base = n_long(run_case("| ZZ3 | MEASURED | tiny | 2026-01-01 |", td))
        long_flagged = n_long(run_case(long_row, td)) == base + 1
        short_flagged = n_long(run_case(short_row, td)) == base + 1
        for got, want, label in ((long_flagged, True, "a 300-word entry is COUNTED as long"),
                                 (short_flagged, False, "a 40-word entry is NOT counted")):
            ok = got == want
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'}  flagged={got!s:<5} want={want!s:<5} {label}")

    # The real ledger must be untouched and must still pass cleanly.
    assert LEDGER.read_bytes() == before, "TEST MUTATED THE REAL LEDGER"
    p = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
    real_clean = "ZZ1" not in p.stdout and "malformed cost" not in p.stdout
    print(f"\n{'ok  ' if real_clean else 'FAIL'}  real ledger unmodified and free of cost warnings")
    bad += not real_clean

    total = len(CASES) + 3
    print(f"\n{total - bad}/{total} correct")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
