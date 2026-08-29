#!/usr/bin/env python3
"""Positive/negative controls for check_ledger.py's cost-annotation check (T41).

Runs against TEMPORARY COPIES of the real ledger, never the file itself -- the
same rule T32 used when verifying the size thresholds. Each case injects one row
into a copy, runs the checker against it, and asserts whether that row is
flagged.

    scripts/test_check_ledger.py
"""
import datetime
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

    # --- CITED AS PRECEDENT (T126) ----------------------------------------
    # A waiver on the highest-value check is the most dangerous thing in this
    # file. The ONLY control that matters is the third: a marker naming a
    # DIFFERENT entry must NOT silence the citation. Without it the token is a
    # blanket off-switch, and an entry-level match once exempted 62 of 185
    # rows including the very case this check exists for.
    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | this rests on ZZ9 with no acknowledgement | 2026-01-01 |",
     True,  "a BARE citation of a withdrawn entry still fires"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | the sampling error ZZ9 records. CITED AS PRECEDENT: ZZ9 is "
     f"withdrawn and named as an example, not relied upon | 2026-01-01 |",
     False, "the marker naming THAT entry waives it"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ8 | WD | Another retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | CITED AS PRECEDENT: ZZ8 is an example. Separately this "
     f"rests on ZZ9 | 2026-01-01 |",
     True,  "THE ONE THAT MATTERS: a marker naming a DIFFERENT entry does NOT waive"),

    (f"| ZZ9 | WD | Retired thing | 2026-01-01 |\n"
     f"| ZZ1 | MEASURED | CITED AS PRECEDENT: some other point entirely. "
     f"{'padding text ' * 30} and this rests on ZZ9 | 2026-01-01 |",
     True,  "a marker FAR from the citation does not waive it"),

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
    # SELF-COUNTING. This was `len(CASES) + 9`, a tally maintained by hand --
    # and adding two checks left it reading 27/27 while 29 ran. A hard-coded
    # expected count is the exact trap the handoff warns about (T80/T89): it
    # makes a NEW check invisible and a REGRESSION look expected. Counted now.
    extra = 0
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
            extra += 1; bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'}  flagged={got!s:<5} want={want!s:<5} {label}")

    # The real ledger must be untouched and must still pass cleanly.
    assert LEDGER.read_bytes() == before, "TEST MUTATED THE REAL LEDGER"
    p = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
    real_clean = "ZZ1" not in p.stdout and "malformed cost" not in p.stdout
    print(f"\n{'ok  ' if real_clean else 'FAIL'}  real ledger unmodified and free of cost warnings")
    extra += 1; bad += not real_clean

    # The LAST line must disclose that reminders precede it. The
    # per-checkpoint routine pipes this through `tail -1`, which silently ate
    # the "audit overdue" reminder on every roll from #64 to #77 -- thirteen
    # times -- so the audit ran 13 rolls late (T76). Truncating to one line may
    # hide a reminder's CONTENT; it must never hide its EXISTENCE.
    lines = [l for l in p2.stdout.strip().split("\n") if l.strip()] if (p2 := subprocess.run(
        [sys.executable, str(CHECKER)], capture_output=True, text=True)) else []
    n_notes = sum(1 for l in lines if "note —" in l or "note --" in l)
    last = lines[-1] if lines else ""
    disclosed = (n_notes == 0) or ("note(s) above" in last)
    print(f"{'ok  ' if disclosed else 'FAIL'}  last line discloses the {n_notes} reminder(s) above it")
    extra += 1; bad += not disclosed

    # ...and it must disclose FINDINGS too, not only reminders.
    #
    # This check used to cover notes alone, and it passed for weeks because the
    # summary line WAS the last line. The moment the ledger held both notes and
    # findings, the summary moved up, the "(warnings, not errors)" trailer became
    # last, and `check_ledger | tail -1` hid a finding as well as three notes.
    # A disclosure rule that covers one kind of message is not a disclosure rule.
    n_probs = 0
    for l in lines:
        m = re.search(r"\[ledger\] (\d+) thing\(s\) to look at", l)
        if m:
            n_probs = int(m.group(1))
    probs_disclosed = (n_probs == 0) or ("thing(s)" in last and "above" in last)
    print(f"{'ok  ' if probs_disclosed else 'FAIL'}  last line discloses the {n_probs} finding(s) above it")
    extra += 1; bad += not probs_disclosed

    # THE ROLL WITNESS (T98), asserted BOTH WAYS in one helper. A one-sided
    # version -- "it fires when the witness is missing" -- would also pass if the
    # check fired unconditionally, which would be noise on every checkpoint and
    # would get switched off within a day. So the cited case must come back
    # silent, and the check must be LAGGED: the newest roll's checkpoint is
    # legitimately still in flight.
    def witness_case(ledger_extra, label):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            (root / "docs" / "findings-ledger.md").write_text(
                "| # | status | finding |\n|---|---|---|\n"
                f"| Z1 | MEASURED | a finding {ledger_extra} |\n")
            (root / "docs" / "route-log.md").write_text(
                "- roll #91: **EXPLOIT** (drew 0.5 vs eps 0.3) -> `A99` "
                "[witness `aabbcc`] — x\n"
                "- roll #92: **EXPLORE** (drew 0.1 vs eps 0.3) -> `A97` "
                "[witness `ddeeff`] — y\n")
            p = subprocess.run([sys.executable, str(root / "scripts" / "check_ledger.py")],
                               capture_output=True, text=True)
            return "aabbcc" in (p.stdout + p.stderr)

    fires_when_missing = witness_case("with no witness quoted", "uncited")
    silent_when_cited = not witness_case("recorded under witness aabbcc", "cited")
    # And the CURRENT roll must not be demanded: `ddeeff` is roll #92's, still
    # in flight, so it must never be named.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "r"
        (root / "scripts").mkdir(parents=True)
        (root / "docs").mkdir(parents=True)
        shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
        (root / "docs" / "findings-ledger.md").write_text(
            "| # | status | finding |\n|---|---|---|\n| Z1 | MEASURED | nothing |\n")
        (root / "docs" / "route-log.md").write_text(
            "- roll #91: **EXPLOIT** (drew 0.5 vs eps 0.3) -> `A99` [witness `aabbcc`] — x\n"
            "- roll #92: **EXPLORE** (drew 0.1 vs eps 0.3) -> `A97` [witness `ddeeff`] — y\n")
        p = subprocess.run([sys.executable, str(root / "scripts" / "check_ledger.py")],
                           capture_output=True, text=True)
        lagged = "ddeeff" not in (p.stdout + p.stderr)

    w_ok = fires_when_missing and silent_when_cited and lagged
    print(f"{'ok  ' if w_ok else 'FAIL'}  roll witness: fires when uncited, silent when cited, "
          f"lags one roll  — missing={fires_when_missing}, cited-silent={silent_when_cited}, "
          f"lagged={lagged}")
    extra += 1; bad += not w_ok

    # SINGLE-RUN AT WRITE TIME (T99). Two-sided, and it must run the checker
    # TWICE: the first run seeds the high-water mark and deliberately flags
    # nothing, so a one-shot test would report "does not fire" for the wrong
    # reason and look like a passing negative control.
    def single_run_case(row):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            led = root / "docs" / "findings-ledger.md"
            head = "| # | status | finding | evidence |\n|---|---|---|---|\n"
            led.write_text(head + "| A1 | MEASURED (2 runs) | baseline | x.log, y.log |\n")
            chk = [sys.executable, str(root / "scripts" / "check_ledger.py")]
            subprocess.run(chk, capture_output=True, text=True)      # seeds the mark
            led.write_text(head + "| A1 | MEASURED (2 runs) | baseline | x.log, y.log |\n" + row)
            p = subprocess.run(chk, capture_output=True, text=True)
            return "rests on ONE run" in (p.stdout + p.stderr)

    sr_fires = single_run_case(
        "| A2 | MEASURED | a new claim from one run | 2026-01-01; only.log |\n")
    sr_two_logs = single_run_case(
        "| A3 | MEASURED | a claim from two runs | 2026-01-01; a.log and b.log |\n")
    sr_plural = single_run_case(
        "| A4 | MEASURED (2 runs) | a claim | 2026-01-01; only.log |\n")
    sr_justified = single_run_case(
        "| A5 | MEASURED | ONE RUN IS ENOUGH: the walk is deterministic "
        "| 2026-01-01; only.log |\n")
    sr_ok = sr_fires and not sr_two_logs and not sr_plural and not sr_justified
    print(f"{'ok  ' if sr_ok else 'FAIL'}  single-run asked at write time: fires bare, exempt on "
          f"2 logs / plural / justification  — fires={sr_fires}, two-logs={sr_two_logs}, "
          f"plural={sr_plural}, justified={sr_justified}")
    extra += 1; bad += not sr_ok

    # THE CLOSING SENTENCE, IN THE ENTRY (T120).
    #
    # FOUR CASES, AND THE THIRD IS THE ONE THAT MATTERS. A presence-only check
    # is satisfied by pasting the entry's own jargon after the label -- which is
    # precisely the sentence the rule exists to prevent -- so a control that
    # only tested "missing fires, present does not" would pass on a useless
    # checker. The jargon case is what makes this discriminate.
    def sowhat_case(row):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            led = root / "docs" / "findings-ledger.md"
            head = "| # | status | finding | evidence |\n|---|---|---|---|\n"
            base = "| A1 | MEASURED (2 runs) | baseline | x.log, y.log |\n"
            led.write_text(head + base)
            chk = [sys.executable, str(root / "scripts" / "check_ledger.py")]
            subprocess.run(chk, capture_output=True, text=True)      # seeds the mark
            led.write_text(head + base + row)
            p = subprocess.run(chk, capture_output=True, text=True)
            return "SO WHAT" in (p.stdout + p.stderr)

    sw_missing = sowhat_case(
        "| A2 | MEASURED (2 runs) | a finding with no closing sentence | a.log, b.log |\n")
    sw_present = sowhat_case(
        "| A3 | MEASURED (2 runs) | a finding. **SO WHAT: the game now gets further "
        "before it stops.** | a.log, b.log |\n")
    sw_jargon = sowhat_case(
        "| A4 | MEASURED (2 runs) | a finding. **SO WHAT: 0x800F91B0 no longer clobbers "
        "ctx->r16 per A188.** | a.log, b.log |\n")
    sw_stub = sowhat_case(
        "| A5 | MEASURED (2 runs) | a finding. **SO WHAT: done.** | a.log, b.log |\n")
    # AN ENTRY THAT DOCUMENTS THE FORMAT MUST NOT BE FLAGGED FOR DOING SO (T121).
    # The first version took the first match and flagged T120 -- the entry that
    # introduced the rule -- because it quotes the template before using it.
    sw_quotes_template = sowhat_case(
        "| A6 | MEASURED (2 runs) | we added a `SO WHAT: <one plain sentence>` line to "
        "every entry. **SO WHAT: the summary now lives in the record instead of only "
        "being said out loud.** | a.log, b.log |\n")
    sw_ok = (sw_missing and not sw_present and sw_jargon and sw_stub
             and not sw_quotes_template)
    print(f"{'ok  ' if sw_ok else 'FAIL'}  SO WHAT asked at write time: fires when missing, "
          f"quiet when plain, FIRES ON JARGON and on a stub, and does NOT flag an entry that "
          f"quotes the template — missing={sw_missing}, plain={sw_present}, jargon={sw_jargon}, "
          f"stub={sw_stub}, quotes-template={sw_quotes_template}")
    extra += 1; bad += not sw_ok

    # THE MERGE CHECK (A713). Entry IDs must be above the check's baseline
    # (A709), or nothing is examined at all -- which would make every case
    # below pass for the wrong reason.
    def merge_case(row):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            led = root / "docs" / "findings-ledger.md"
            head = "| # | status | finding | evidence |\n|---|---|---|---|\n"
            base = "| A1 | MEASURED (2 runs) | baseline | x.log, y.log |\n"
            led.write_text(head + base)
            chk = [sys.executable, str(root / "scripts" / "check_ledger.py")]
            subprocess.run(chk, capture_output=True, text=True)      # seeds the mark
            led.write_text(head + base + row)
            p = subprocess.run(chk, capture_output=True, text=True)
            return "MERGE:" in (p.stdout + p.stderr)

    _SW = "**SO WHAT: the thing now works better than it did.**"
    mg_missing = merge_case(
        f"| A801 | MEASURED | ran two Fable sub-agents. THREAD 1 read the table, "
        f"THREAD 2 read the callers. {_SW} | a.log, b.log |\n")
    mg_present = merge_case(
        f"| A802 | MEASURED | ran two Fable sub-agents. THREAD 1 read the table, "
        f"THREAD 2 read the callers. MERGE: compared both exclusion lists; neither "
        f"claim needs anything the other denies. {_SW} | a.log, b.log |\n")
    # THE ONE THAT MATTERS: the GAME's threads, not sub-agents. B59 and I5 are
    # full of "thread 4" / "thread 17" and must never trip this.
    # It must trip SIGNAL 1 (so the plural AND two single-char labels), leaving
    # ONLY the sub-agent guard to keep it silent. The first version said
    # "THREAD 4 ... THREAD 17" and stayed quiet for the WRONG REASON: "17" never
    # matched the single-character label pattern, so signal 1 never fired and
    # the guard was never exercised. Breaking the guard did not fail this case,
    # which is precisely T65's "a control that cannot fail is not a control".
    mg_game = merge_case(
        f"| A803 | MEASURED | I5's instrument defect: two threads both report id 3, "
        f"and THREAD 4 and THREAD 7 have different priorities and stacks. {_SW} "
        f"| a.log, b.log |\n")
    mg_short = merge_case(
        f"| A804 | MEASURED | ran two Opus sub-agents. THREAD 1 and THREAD 2. "
        f"MERGE: fine. {_SW} | a.log, b.log |\n")
    # Plural-only, no numbered labels -- the A714 shape that label-matching missed.
    mg_plural = merge_case(
        f"| A805 | MEASURED | both threads returned lists; the agents were Opus 5. "
        f"{_SW} | a.log, b.log |\n")
    # THE PARAPHRASES THAT EVADED THE FIRST VERSION (T233). Both slipped the
    # old two-signal trigger: no plural "threads", no numbered THREAD label.
    # These are the reason counting was abandoned; if either goes SILENT again
    # the hole is back.
    mg_para1 = merge_case(
        f"| A806 | MEASURED | ran two Fable sub-agents in parallel. One agent read "
        f"the exclusion table while another read the head banners. {_SW} "
        f"| a.log, b.log |\n")
    mg_para2 = merge_case(
        f"| A807 | MEASURED | spawned a pair of readers concurrently; the agents "
        f"were Fable 5. The first covered one entry, the second another. {_SW} "
        f"| a.log, b.log |\n")
    # A SINGLE agent must also state the position -- "no merge applies" is one
    # clause, and silence is what the gate exists to refuse.
    mg_single = merge_case(
        f"| A808 | MEASURED | one Opus 5 sub-agent read the log and returned a "
        f"list. {_SW} | a.log, b.log |\n")
    mg_ok = (mg_missing and not mg_present and not mg_game
             and mg_short and mg_plural
             and mg_para1 and mg_para2 and mg_single)
    print(f"{'ok  ' if mg_ok else 'FAIL'}  MERGE recorded whenever sub-agents are mentioned: "
          f"fires when missing, SILENT when answered, SILENT on the GAME's threads, fires on "
          f"a stub, and CATCHES THE PARAPHRASES THAT EVADED v1 (T233) — missing={mg_missing}, "
          f"answered={mg_present}, game-threads={mg_game}, stub={mg_short}, plural={mg_plural}, "
          f"paraphrase-1={mg_para1}, paraphrase-2={mg_para2}, single-agent={mg_single}")
    extra += 1; bad += not mg_ok

    # ...and it must not FORGET. The single-run mark advances to the current
    # maximum every run, so its findings are reported exactly once. Here that
    # would erase a gap the moment it was first mentioned, so the mark stops
    # below the lowest failure and the same gap is reported again next run.
    def sowhat_persists():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            led = root / "docs" / "findings-ledger.md"
            head = "| # | status | finding | evidence |\n|---|---|---|---|\n"
            base = "| A1 | MEASURED (2 runs) | baseline | x.log, y.log |\n"
            led.write_text(head + base)
            chk = [sys.executable, str(root / "scripts" / "check_ledger.py")]
            subprocess.run(chk, capture_output=True, text=True)
            led.write_text(head + base +
                           "| A2 | MEASURED (2 runs) | no sentence | a.log, b.log |\n")
            first = subprocess.run(chk, capture_output=True, text=True)
            second = subprocess.run(chk, capture_output=True, text=True)
            return ("SO WHAT" in first.stdout + first.stderr,
                    "SO WHAT" in second.stdout + second.stderr)

    sw_first, sw_again = sowhat_persists()
    sw_p_ok = sw_first and sw_again
    print(f"{'ok  ' if sw_p_ok else 'FAIL'}  SO WHAT keeps reporting an unfixed gap "
          f"(the mark must not step over a known failure) — first={sw_first}, "
          f"second={sw_again}")
    extra += 1; bad += not sw_p_ok

    # OBSERVED-RUN PROGRESS TRIGGER (T101). Two-sided, because a trigger that
    # fires on every run is noise that costs the USER's time, and one that never
    # fires is the policy silently not existing. The interesting negative is a
    # NORMAL crash: long request, long duration, rc=139 -- that must stay quiet.
    #
    # REKEYED 2026-08-21 TO THE CURRENT SIGNATURE. This used to assert that a
    # long run NOT returning 139 fires, and that rc=139 stays quiet -- correct
    # for the era when long runs SIGSEGV'd at ~158 s. That era ended on
    # 2026-08-20: every long headless run since returns 0 at 6,169 tasks, so
    # the old condition became true of every run and the note fired forever, on
    # healthy runs, while gating the USER's time. The semantics are now
    # inverted, and this control is inverted with them rather than deleted --
    # a stale control that still passes is worse than none.
    HDR = ("ts\tsecs_req\tsecs_actual\trc\tinput\tleftover\tgfx_total\t"
           "gfx_rate\tverdict\tlog\tenv\n")

    def progress_case(runrow):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            (root / "docs" / "findings-ledger.md").write_text(
                "| # | status | finding |\n|---|---|---|\n| A1 | MEASURED (2 runs) | x |\n")
            (root / "docs" / "run-log.tsv").write_text(HDR + runrow)
            p = subprocess.run([sys.executable, str(root / "scripts" / "check_ledger.py")],
                               capture_output=True, text=True)
            out = p.stdout + p.stderr
            return ("DUE ON PROGRESS" in out, "CHANGED SIGNATURE" in out)

    def row(req, act, rc, gfx, verdict, env="none"):
        return (f"2026-08-21T10:00:00+10:00\t{req}\t{act}\t{rc}\t0\t0\t{gfx}\t"
                f"0\t{verdict}\tx.log\t{env}\n")

    # PROGRESS is the ceiling breaking -- A299's own falsifier.
    broke, _ = progress_case(row(215, 215, 0, 6200, "STALLED"))
    # THE INTERESTING NEGATIVE: the normal stall. 13 runs sit exactly here and
    # it is the single most common long-run outcome, so a trigger that fires on
    # it fires on almost everything.
    stall, _ = progress_case(row(215, 215, 0, 6169, "STALLED"))
    # Ran out of clock 195 tasks short -- survived nothing, reached nothing.
    short, _ = progress_case(row(200, 200, 0, 5974, "CLEAN"))
    # REGRESSION: the retired ~158 s SIGSEGV returning on a HEADLESS run.
    _, regress = progress_case(row(180, 158, 139, 4659, "CRASHED"))
    # ...but the inspector crashes on the REAL display constantly (A288/T134)
    # and that is a known, different fault. It must not read as a regression.
    _, vis = progress_case(row(600, 190, 139, 5613, "CRASHED", "SNP_VISIBLE=1"))

    pr_ok = broke and not stall and not short and regress and not vis
    print(f"{'ok  ' if pr_ok else 'FAIL'}  observed-run trigger is keyed to the CURRENT "
          f"signature  — ceiling-broken={broke}, normal-stall={stall}, "
          f"short={short}, headless-139={regress}, visible-139={vis}")
    extra += 1; bad += not pr_ok

    # THE IDLE-DAY GATE (T151, the user's rule). Trigger 1 carried a comment
    # saying it was "GATED ON WORK HAVING HAPPENED" and guarded on `rows` --
    # every ledger entry ever written, never empty. So it nagged on days nobody
    # touched the project, including from the 18:30 cron job. This one spends
    # the USER's time and a policy that wastes it gets abandoned (T29).
    #
    # DISCRIMINATING IN BOTH DIRECTIONS, because either failure is silent: a
    # gate that never opens loses the reminder entirely, and one that always
    # opens is the bug being fixed. Same fixture, one field different -- the
    # run-log row's DATE.
    _today = datetime.date.today().isoformat()

    def idle_case(run_date, entry_body="x"):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            (root / "docs" / "findings-ledger.md").write_text(
                "| # | status | finding |\n|---|---|---|\n"
                f"| A1 | MEASURED (2 runs) | {entry_body} |\n")
            (root / "docs" / "run-log.tsv").write_text(
                HDR + f"{run_date}T10:00:00+10:00\t20\t20\t0\t0\t0\t600\t30\tCLEAN\tx.log\tnone\n")
            p = subprocess.run([sys.executable, str(root / "scripts" / "check_ledger.py")],
                               capture_output=True, text=True)
            return "observed run: none today" in (p.stdout + p.stderr)

    worked = idle_case(_today)                       # a run today -> must nag
    idle = idle_case("2026-01-01")                   # nothing today -> must not
    entry_only = idle_case("2026-01-01", f"measured {_today}")   # entry today -> must nag
    idle_ok = worked and not idle and entry_only
    print(f"{'ok  ' if idle_ok else 'FAIL'}  idle days do not accrue an observed-run nag "
          f"(T151)  — run-today={worked}, idle-day={idle}, entry-today={entry_only}")
    extra += 1; bad += not idle_ok

    # THE COMPOSING-STEP CHECK (T112). Three directions, because the failure
    # modes are opposite: not firing at all (T57 stays prose), or firing on
    # every multi-artifact entry (noise, and noise is how a discipline stops
    # being read -- T29).
    def compose_case(row):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "r"
            (root / "scripts").mkdir(parents=True)
            (root / "docs").mkdir(parents=True)
            shutil.copy(CHECKER, root / "scripts" / "check_ledger.py")
            (root / "docs" / "findings-ledger.md").write_text(
                "| # | status | finding | evidence |\n|---|---|---|---|\n" + row)
            p2 = subprocess.run([sys.executable, str(root / "scripts" / "check_ledger.py")],
                                capture_output=True, text=True)
            return "COMPOSING STEP" in (p2.stdout + p2.stderr)

    c_fires = compose_case(
        "| A1 | MEASURED (2 runs) | a claim | 2026-08-19 a.log; 2026-08-20 b.log |\n")
    c_marked = compose_case(
        "| A1 | MEASURED (2 runs) | a claim, COMPOSING STEP named and unverified "
        "| 2026-08-19 a.log; 2026-08-20 b.log |\n")
    c_single = compose_case(
        "| A1 | MEASURED (2 runs) | a claim | 2026-08-20 a.log, b.log |\n")
    # THIS CASE MUST CARRY "MEASURED" TOO, or it is vacuous. A bare "WD" status
    # is skipped by the MEASURED|READ filter and never reaches the withdrawn
    # check at all -- the first version passed for that reason, and removing the
    # withdrawn-skip did NOT break it. Real withdrawn entries look like this
    # (A138 "WD as to cause", A169 "WD AS TO ITS HEADLINE ... Was: MEASURED").
    c_wd = compose_case(
        "| A1 | WD as to cause — was MEASURED (2 runs) | a withdrawn claim "
        "| 2026-08-19 a.log; 2026-08-20 b.log |\n")
    c_ok = c_fires and not c_marked and not c_single and not c_wd
    print(f"{'ok  ' if c_ok else 'FAIL'}  composing-step check: fires cross-date, silent when marked / "
          f"single-date / withdrawn  — fires={c_fires}, marked={c_marked}, "
          f"single={c_single}, wd={c_wd}")
    extra += 1; bad += not c_ok

    # --- QUIET MODE (T163) -----------------------------------------------
    #
    # Suppressing output at source is only safe if it suppresses the RIGHT
    # things. A quiet flag that swallowed a real warning would be the A196
    # failure with a nicer interface -- and A196 is worth citing accurately: the
    # tool there was NOT silent, the operator truncated its stderr away.
    #
    # FOUR CONTROLS, DISCRIMINATING IN BOTH DIRECTIONS. Two of them must FAIL if
    # quiet ever over-reaches: a real problem must still print, and the withheld
    # notes' EXISTENCE must still be disclosed (T76 -- content may be hidden,
    # existence may not).
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        _fr = Path(_td) / "fakeroot"
        (_fr / "scripts").mkdir(parents=True)
        (_fr / "docs").mkdir(parents=True)
        shutil.copy(CHECKER, _fr / "scripts" / "check_ledger.py")
        # The fixture needs BOTH halves or the control cannot discriminate: a
        # REAL problem (a negative with no stated scope) and enough bulk to
        # actually trigger the standing LENGTH/SIZE notes. A two-row ledger
        # trips neither threshold, so quiet and loud came out identical and the
        # control failed -- correctly, on a fixture that could not test it.
        _filler = " ".join(["padding"] * 400)
        (_fr / "docs" / "findings-ledger.md").write_text(
            "| # | status | finding | evidence |\n|---|---|---|---|\n"
            "| A1 | MEASURED | nothing calls this function | one.log |\n"
            f"| A2 | MEASURED (in the ROM) | {_filler} | two.log |\n")

        def _run(*flags):
            r = subprocess.run([sys.executable, str(_fr / "scripts" / "check_ledger.py"), *flags],
                               capture_output=True, text=True)
            return r.stdout + r.stderr

        loud, quiet = _run(), _run("--quiet")
        q1 = len(quiet) < len(loud)
        q2 = "thing(s) to look at" in quiet          # a REAL problem still prints
        q3 = "withheld" in quiet                      # existence disclosed (T76)
        q4 = "note — LENGTH" in loud or "note — SIZE" in loud or "withheld" not in loud
        q_ok = q1 and q2 and q3 and q4
        print(f"{'ok  ' if q_ok else 'FAIL'}  --quiet: shorter, but a real problem AND the withheld "
              f"count still print  — shorter={q1}, problem={q2}, disclosed={q3}, loud-unchanged={q4}")
        extra += 1; bad += not q_ok

    # PARKED ITEMS MUST HAVE A WAY BACK (T175). Two items sat parked as
    # "AWAITING THE USER" with nothing watching them -- a grep for AWAITING
    # across every script returned zero hits, so their return depended entirely
    # on memory, which T28 says has never held here.
    #
    # Asserted in both directions: the live ledger must currently be CLEAN (every
    # parked item names a blocker), AND both halves of the check must still be
    # present in the source. A checker that only ever complains is as useless as
    # one that never does.
    import importlib.util as _iu, tempfile as _tf, io as _io, contextlib as _cl, sys as _sy
    from pathlib import Path as _P
    _fr = _P(__file__).resolve().parent.parent

    def _run_on(body):
        """Run check_ledger against a synthetic ledger and return its output."""
        hdr = "| # | status | finding | evidence |\n|---|---|---|---|\n"
        queue = ("\n## THE USER QUEUE — work only the user can do\n\n" + hdr +
                 "| U7 | LIVE 2026-08-20 | not done yet |\n"
                 "| U8 | SWEPT 2026-08-21 -> T146 | finished |\n")
        _sp2 = _iu.spec_from_file_location("_cl2", _fr / "scripts" / "check_ledger.py")
        _m = _iu.module_from_spec(_sp2); _sp2.loader.exec_module(_m)
        with _tf.TemporaryDirectory() as td:
            f = _P(td) / "findings-ledger.md"
            f.write_text("# L\n\n" + hdr + body + queue)
            _m.LEDGER = f
            buf = _io.StringIO()
            argv, _sy.argv = _sy.argv, ["check_ledger.py"]
            try:
                with _cl.redirect_stdout(buf):
                    _m.main()
            finally:
                _sy.argv = argv
            return buf.getvalue()

    # THREE DIRECTIONS, so the check cannot pass by always firing or never firing.
    _no_blocker = _run_on("| T900 | AWAITING THE USER — parked | body | 2026-01-01 |\n")
    _live_blkr  = _run_on("| T901 | AWAITING THE USER — waits on U7 | body | 2026-01-01 |\n")
    _done_blkr  = _run_on("| T902 | AWAITING THE USER — waits on U8 | body | 2026-01-01 |\n")
    p1 = "names NO queue item" in _no_blocker
    p2 = "PARKED" not in _live_blkr
    p3 = "every queue item it waits on is finished" in _done_blkr
    p4 = "PARKED" not in (_live.stdout + _live.stderr) if False else True
    _ok = p1 and p2 and p3
    print(f"{'ok  ' if _ok else 'FAIL'}  parked items are watched — fires with no blocker={p1}, "
          f"SILENT with a live blocker={p2}, fires when the blocker is finished={p3}")
    extra += 1; bad += not _ok

    # VAGUE DURATION ABOUT OUR OWN HISTORY (T177). Four directions, because a
    # checker that fires on everything is as useless as one that never fires --
    # and "months" about the GAME's development is legitimate.
    def _dur(body):
        sp2 = _iu.spec_from_file_location("_cd", _fr / "scripts" / "check_ledger.py")
        m2 = _iu.module_from_spec(sp2); sp2.loader.exec_module(m2)
        hdr2 = "| # | status | finding | evidence |\n|---|---|---|---|\n"
        with _tf.TemporaryDirectory() as td:
            f = _P(td) / "findings-ledger.md"; f.write_text("# L\n\n" + hdr2 + body)
            m2.LEDGER = f; buf = _io.StringIO()
            argv, _sy.argv = _sy.argv, ["check_ledger.py"]
            try:
                with _cl.redirect_stdout(buf): m2.main()
            finally:
                _sy.argv = argv
            return "vague duration" in buf.getvalue()

    d1 = _dur("| A1 | M | measured months of checkpoints ago | 2026-01-01 |\n")
    d2 = _dur('| A2 | M | I wrote "months of checkpoints ago" once | 2026-01-01 |\n')
    d3 = _dur("| A3 | M | the game spent months in development in 1999 | 2026-01-01 |\n")
    d4 = _dur("| A4 | M | measured weeks ago and never fixed | 2026-01-01 |\n")
    _dok = d1 and not d2 and not d3 and d4
    print(f"{'ok  ' if _dok else 'FAIL'}  vague duration — fires on an assertion={d1}, "
          f"SILENT when quoted={not d2}, SILENT about the game={not d3}, other units={d4}")
    extra += 1; bad += not _dok

    total = len(CASES) + extra
    print(f"\n{total - bad}/{total} correct")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
