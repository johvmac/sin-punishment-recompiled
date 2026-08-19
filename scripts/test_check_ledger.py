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

    # The real ledger must be untouched and must still pass cleanly.
    assert LEDGER.read_bytes() == before, "TEST MUTATED THE REAL LEDGER"
    p = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
    real_clean = "ZZ1" not in p.stdout and "malformed cost" not in p.stdout
    print(f"\n{'ok  ' if real_clean else 'FAIL'}  real ledger unmodified and free of cost warnings")
    bad += not real_clean

    print(f"\n{len(CASES) + 1 - bad}/{len(CASES) + 1} correct")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
