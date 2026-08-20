#!/usr/bin/env python3
"""Controls for the supersession suppression (T123) and the degenerate-frontier
warning. Both were added because a checker that cannot tell live work from dead
work produces noise, and noise is how a check stops being read.

    scripts/test_supersede.py
"""
import importlib.util, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cl", ROOT / "scripts" / "check_ledger.py")
cl = importlib.util.module_from_spec(spec); spec.loader.exec_module(cl)


def main():
    bad = n = 0

    def chk(label, got, detail=""):
        nonlocal bad, n
        n += 1
        print(f"{'ok  ' if got else 'FAIL'}  {label}" + ("" if got else f" -- {detail}"))
        bad += not got

    # --- superseded_by_later ------------------------------------------------
    rows = {
        "A1": ("MEASURED", "a claim from one run", 0),
        "A2": ("MEASURED", "this supersedes A1 entirely", 0),
        "A3": ("MEASURED", "unrelated work that merely cites A1 in passing", 0),
        "B1": ("MEASURED", "a claim", 0),
        "B2": ("MEASURED", "corrects B1", 0),
    }
    chk("a later entry with a correction word supersedes",
        cl.superseded_by_later("A1", rows) == "A2",
        f"got {cl.superseded_by_later('A1', rows)}")

    # THE DISCRIMINATING ONE: a bare citation must NOT count. Without this the
    # rule suppresses any entry anyone ever mentions again, which would hide
    # real findings rather than noise -- strictly worse than the noise.
    rows_bare = {"A1": ("MEASURED", "a claim", 0),
                 "A3": ("MEASURED", "builds on A1 and extends it", 0)}
    chk("a BARE citation does NOT supersede",
        cl.superseded_by_later("A1", rows_bare) is None,
        f"got {cl.superseded_by_later('A1', rows_bare)}")

    # Direction matters: an EARLIER entry cannot supersede a later one.
    rows_back = {"A5": ("MEASURED", "corrects A9", 0), "A9": ("MEASURED", "a claim", 0)}
    chk("an EARLIER entry cannot supersede a later one",
        cl.superseded_by_later("A9", rows_back) is None,
        f"got {cl.superseded_by_later('A9', rows_back)}")

    # Prefixes must not cross.
    rows_x = {"A1": ("MEASURED", "a claim", 0), "T9": ("MEASURED", "supersedes A1", 0)}
    chk("supersession does not cross ID prefixes",
        cl.superseded_by_later("A1", rows_x) is None,
        f"got {cl.superseded_by_later('A1', rows_x)}")

    # --- the degenerate-frontier warning ------------------------------------
    src = (ROOT / "scripts" / "route.py").read_text()
    body = src.split("def main(", 1)[-1]
    chk("route warns when the frontier cannot support exploration",
        "THE FRONTIER HAS" in body and "len(items) <= 1" in body,
        "no degenerate-frontier warning in the executable body")
    chk("route warns when an EXPLORE draw had a single candidate",
        "ONE CANDIDATE" in body and "len(cands) == 1" in body,
        "a p=1.00 'choice' would pass silently")

    # --- the audit must NAME what it suppressed -----------------------------
    a = (ROOT / "scripts" / "audit.py").read_text()
    chk("the audit PRINTS what it suppressed, never silently",
        "suppressed as superseded" in a,
        "silent suppression is indistinguishable from a broken check")

    print()
    print(f"{n - bad}/{n} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
