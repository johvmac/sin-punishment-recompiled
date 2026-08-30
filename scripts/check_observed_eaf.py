#!/usr/bin/env python3
"""T150's last checker: did the ELAN annotation project actually get written?

WHY IT READS THE STANZA AND NOT THE FILESYSTEM (A741, roll #449).

A717 specified this as "enumerate directories containing observed-*.log, flag
any whose .eaf is missing".  Built that way it would be WRONG TWICE:

 1. WRONG FILENAME, PERMANENTLY.  `observed_run.sh` writes
    `EAF="${VIDEO%.*}.eaf"` -- the project sits beside the VIDEO, so it is
    named `run_game-<stamp>.eaf`.  A checker globbing for an `.eaf` beside
    `observed-<stamp>.log` would report MISSING on every correctly-wired run
    from now on.  The one .eaf on the archive is `observed-091444.eaf`, which
    LOOKS like it vindicates the filesystem design and does the opposite: it
    was made by hand at 09:59, and the wiring commit landed at 10:23.

 2. WRONG BOUND.  A734 proposed bounding by the wiring commit e5002ea
    (2026-08-29 10:23:30).  Every bundle on the archive predates it, so a
    date-bounded filesystem checker is silent on all eleven and has never once
    said yes -- T100's "a checker that finds nothing on its first run should be
    suspected", in its purest form.

THE STANZA SOLVES BOTH, because it is written BY the script and therefore
describes the script that wrote it:

  * no `annotate:` line at all   -> a PRE-WIRING stanza.  Silent.  The
    mechanism did not exist; there is nothing to have failed.  This is a
    self-describing high-water mark -- no date, no state file, nothing to
    maintain (contrast T238, where a mark hides later damage; here the thing
    being skipped could not have happened).
  * `annotate: (none ...)`       -> eaf_make RAN AND FAILED.  FIRE.
  * `annotate: <path>`           -> claimed.  Verify the file exists; if the
    stanza names a project that is not on disk, FIRE.

Usage:
  check_observed_eaf.py [--quiet]      check docs/observed-runs.md
  check_observed_eaf.py --self-check   run the controls
"""
import re
import sys
from pathlib import Path

LOG = Path("docs/observed-runs.md")
STANZA = re.compile(r"^## (\S+) —", re.M)
ANNOT = re.compile(r"^-\s*\*\*annotate:\*\*\s*(.+?)\s*$", re.M | re.I)


def split_stanzas(text):
    """[(header, body)] for each '## <stamp> —' stanza."""
    out, marks = [], list(STANZA.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.start():end]))
    return out


def check(text, exists=Path.exists):
    """-> (problems, pre_wiring, complete). Each problem is (stamp, why)."""
    problems, pre, done = [], [], []
    for stamp, body in split_stanzas(text):
        m = ANNOT.search(body)
        if not m:
            pre.append(stamp)
            continue
        val = m.group(1).strip()
        if val.startswith("(") or "did not run" in val or val.lower() == "none":
            problems.append((stamp, f"eaf_make RAN AND FAILED — stanza says {val!r}"))
        elif not exists(Path(val)):
            problems.append((stamp, f"stanza names {val!r} but that file is not on disk"))
        else:
            done.append(stamp)
    return problems, pre, done


def self_check():
    """Both directions, or it is not a control (T65/T231)."""
    here = Path(__file__).resolve()
    real = {here}                      # a path that certainly exists
    exists = lambda p: p in real       # noqa: E731  -- no filesystem in the fixtures

    FIXTURE = f"""
## PREWIRE — build `aaa`, 220s requested, rc=0 (STALLED)
- run log: `observed-000001.log`
- **video:** /x/run_game-000001.mp4
- **CONTRADICTS MY CLAIMS:** no

## FAILED — build `bbb`, 220s requested, rc=0 (STALLED)
- run log: `observed-000002.log`
- **video:** /x/run_game-000002.mp4
- **annotate:** (none — eaf_make did not run)
- **CONTRADICTS MY CLAIMS:** no

## GHOST — build `ccc`, 220s requested, rc=0 (STALLED)
- run log: `observed-000003.log`
- **annotate:** /x/run_game-000003.eaf
- **CONTRADICTS MY CLAIMS:** no

## GOOD — build `ddd`, 220s requested, rc=0 (STALLED)
- run log: `observed-000004.log`
- **annotate:** {here}
- **CONTRADICTS MY CLAIMS:** no
"""
    problems, pre, done = check(FIXTURE, exists)
    got_p = {s for s, _ in problems}
    checks = [
        ("C1 POSITIVE  a stanza whose eaf_make FAILED must FIRE",
         "FAILED" in got_p),
        ("C2 POSITIVE  a stanza naming an eaf not on disk must FIRE",
         "GHOST" in got_p),
        ("C3 NEGATIVE  a PRE-WIRING stanza (no annotate line) must stay SILENT",
         pre == ["PREWIRE"] and "PREWIRE" not in got_p),
        ("C4 NEGATIVE  a complete stanza must stay SILENT",
         done == ["GOOD"] and "GOOD" not in got_p),
        ("C5 the four fixtures must be partitioned, none lost",
         len(problems) + len(pre) + len(done) == 4),
    ]
    ok = True
    for label, passed in checks:
        print(f"  {label:<62} {'PASS' if passed else 'FAIL'}")
        ok &= passed
    print(f"\nSELF-CHECK {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    if "--self-check" in sys.argv:
        return self_check()
    quiet = "--quiet" in sys.argv
    if not LOG.exists():
        print(f"[eaf] {LOG} not found — nothing to check.")
        return 0
    problems, pre, done = check(LOG.read_text())
    for stamp, why in problems:
        print(f"[eaf] PROBLEM {stamp}: {why}")
    if not quiet:
        print(f"[eaf] {len(done)} annotated, {len(problems)} problem(s), "
              f"{len(pre)} pre-wiring stanza(s) skipped as self-describing.")
    if pre and not done and not problems:
        print(f"[eaf] NOTE: all {len(pre)} stanzas predate the wiring, so this "
              f"check has never once said yes. It is UNPROVEN on real data "
              f"until an observed run happens with the wiring live (T100).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
