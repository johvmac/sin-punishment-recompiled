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
import tempfile
import xml.etree.ElementTree as ET
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


def eaf_parses(path):
    """(ok, detail) — does this actually parse as an ELAN project?

    A742's NEXT: statting the file is not enough. A truncated or half-written
    `.eaf` satisfies `exists()` and is useless, and that is exactly the state a
    crashed `eaf_make.py` would leave behind — the failure this check is for.
    Annotation COUNT is deliberately not a criterion: an empty project is the
    normal state until the user annotates, and firing on it would nag about the
    user's homework rather than about the mechanism (T29/T118).
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        return False, f"does not parse: {e}"
    tiers = root.findall(".//TIER")
    if not tiers:
        return False, "parses, but declares no TIER — not an annotation project"
    n = len(root.findall(".//ALIGNABLE_ANNOTATION"))
    return True, f"{len(tiers)} tier(s), {n} annotation(s)"


def check(text, exists=Path.exists, parses=None):
    """-> (problems, pre_wiring, complete). Each problem is (stamp, why)."""
    if parses is None:
        parses = eaf_parses
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
            ok, detail = parses(Path(val))
            if not ok:
                problems.append((stamp, f"{val!r} is on disk but {detail}"))
            else:
                done.append(stamp)
    return problems, pre, done


def self_check():
    """Both directions, or it is not a control (T65/T231).

    THE FIXTURES ARE REAL FILES AND THE REAL PARSER RUNS ON THEM. Injecting a
    fake `parses` would test the plumbing and not the parse, which is the half
    that can actually be wrong.
    """
    d = Path(tempfile.mkdtemp(prefix="eafcheck-"))
    good = d / "run_game-000004.eaf"
    good.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ANNOTATION_DOCUMENT><TIME_ORDER/>'
        '<TIER TIER_ID="faults"><ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a1">'
        '<ANNOTATION_VALUE>x</ANNOTATION_VALUE></ALIGNABLE_ANNOTATION></ANNOTATION>'
        '</TIER></ANNOTATION_DOCUMENT>')
    empty = d / "run_game-000005.eaf"
    empty.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<ANNOTATION_DOCUMENT><TIER TIER_ID="faults"/></ANNOTATION_DOCUMENT>')
    corrupt = d / "run_game-000006.eaf"
    corrupt.write_text('<?xml version="1.0"?>\n<ANNOTATION_DOCUMENT><TIER truncated')
    notproj = d / "run_game-000007.eaf"
    notproj.write_text('<?xml version="1.0"?>\n<something_else/>')

    def stanza(name, annot=None):
        s = f"\n## {name} — build `x`, 220s requested, rc=0 (STALLED)\n- run log: `x.log`\n"
        if annot is not None:
            s += f"- **annotate:** {annot}\n"
        return s + "- **CONTRADICTS MY CLAIMS:** no\n"

    FIXTURE = (stanza("PREWIRE")
               + stanza("FAILED", "(none — eaf_make did not run)")
               + stanza("GHOST", str(d / "does-not-exist.eaf"))
               + stanza("GOOD", str(good))
               + stanza("EMPTY", str(empty))
               + stanza("CORRUPT", str(corrupt))
               + stanza("NOTPROJ", str(notproj)))

    problems, pre, done = check(FIXTURE)
    got = {s for s, _ in problems}
    checks = [
        ("C1 POSITIVE  eaf_make FAILED must FIRE", "FAILED" in got),
        ("C2 POSITIVE  named file not on disk must FIRE", "GHOST" in got),
        ("C3 NEGATIVE  pre-wiring stanza must stay SILENT",
         pre == ["PREWIRE"] and "PREWIRE" not in got),
        ("C4 NEGATIVE  a complete project must stay SILENT",
         "GOOD" in done and "GOOD" not in got),
        ("C5 partition: nothing lost",
         len(problems) + len(pre) + len(done) == 7),
        ("C6 POSITIVE  a CORRUPT project must FIRE (A742's NEXT)",
         "CORRUPT" in got),
        ("C7 POSITIVE  valid XML that is not a project must FIRE",
         "NOTPROJ" in got),
        ("C8 NEGATIVE  an EMPTY but valid project must stay SILENT",
         "EMPTY" in done and "EMPTY" not in got),
    ]
    ok = True
    for label, passed in checks:
        print(f"  {label:<62} {'PASS' if passed else 'FAIL'}")
        ok &= passed
    for f in (good, empty, corrupt, notproj):
        f.unlink()
    d.rmdir()
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
