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

    # --- the zero-run exemption on the probe check (audit #13) --------------
    # `\bSNP_[A-Z]` matches a probe's NAME, so a source survey saying "the probe
    # ACCEPTS a queue address" was read as a probe that had been RUN, and A241
    # and A243 were flagged for lacking a control over output they never
    # produced. The exemption is a fact (no runs, no output), not a judgement.
    DEPLOYED = re.compile(
        r"probe (?:at|on|in|fired|printed|logged|reported|caught|is live)|"
        r"(?:scratch |toml |a |new |walker-entry )hook on|hooks? fired|"
        r"instrumented|\bSNP_[A-Z]", re.I)
    CONTROL = re.compile(
        r"control|ARM |heartbeat|positive|independent(?:ly)? (?:confirm|verif|source)|"
        r"cross-check|OBSERVED, not assumed|exact match|two independent", re.I)
    ZERO = re.compile(r"zero (?:new )?runs|no new runs", re.I)

    POINTER = re.compile(r"^\**(?:ANSWERED by|CLOSED by|MERGED into)\b", re.I)

    def flags(body, status=""):
        if ZERO.search(status + body) or POINTER.match(status.strip()):
            return False
        return bool(DEPLOYED.search(body)) and not CONTROL.search(body)

    survey = "READ (RT64 source survey, zero runs) — `SNP_VI_PROBE` accepts a queue address"
    chk("a ZERO-RUN survey naming a probe is NOT flagged (the audit #13 noise)",
        not flags(survey), "A241/A243 were flagged for output they never produced")

    # THE DISCRIMINATING ONE. Without it the exemption is a blanket suppression:
    # a real deployed probe with no control must STILL fire, or the rule is gone.
    live = "MEASURED (3 runs) — `SNP_DL_CENSUS` probe fired on every task and reported 40 children"
    chk("a probe that WAS run with no control IS still flagged",
        flags(live), "the exemption must not disable the rule")
    chk("a probe that WAS run WITH a control is not flagged",
        not flags(live + "; 10/10 controls pass"), "a control must still clear it")

    # And the exemption must be keyed to the run count, not to the word "survey"
    # -- a survey that DID run something is not exempt.
    chk("'survey' alone does not exempt; only an explicit zero-run claim does",
        flags("READ (RT64 source survey) — `SNP_VI_PROBE` accepts a queue address"),
        "the exemption must key on runs, not on a genre word")

    # The run count is declared in the STATUS cell by convention, so searching
    # body-only missed A243, which says "zero runs" in exactly that place.
    chk("a zero-run claim in the STATUS cell exempts (where A243 declares it)",
        not flags("`SNP_VI_PROBE` accepts a queue address",
                  status="READ (RT64 source survey, zero runs)"),
        "the status cell must be searched too")

    # A POINTER entry defers its substance elsewhere; its controls live in the
    # entry it names. This is why A241 ("ANSWERED by A243") was flagged.
    chk("a POINTER entry is exempt — its evidence lives in the entry it names",
        not flags("survey what RT64 gives us; `SNP_VI_PROBE` accepts a queue address",
                  status="ANSWERED by A243 (roll #137)"),
        "asking a signpost for a control asks the wrong entry")

    # THE DISCRIMINATING ONE FOR THAT EXEMPTION. A244 CORRECTS A239 and carries
    # its own 5 runs, an A/B pair and a contamination control -- a correction is
    # a claim, not a pointer, and must NOT be waved through.
    chk("CORRECTS is NOT treated as a pointer (it carries its own evidence)",
        flags("`SNP_DL_CENSUS` probe fired and reported 40 children",
              status="CORRECTS A239 (5 runs)"),
        "a correction is a claim and must still show a control")

    print()
    print(f"{n - bad}/{n} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
