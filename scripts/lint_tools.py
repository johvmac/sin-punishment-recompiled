#!/usr/bin/env python3
"""Pre-flight lint for the SCRIPTS themselves: is a new tool documented, and
does anything that takes arguments say what they are?

WHY
---
Two failures, both from 2026-08-19/20, both mechanical and both missed:

  * **T89/T90 -- four tools were built in one session and NONE of them reached
    the Tool inventory** in `docs/diagnostic-playbook.md`. The rule that says to
    add them (T71's third gate) is prose, and prose describing a discipline is
    not the discipline. Nothing checked.
  * **T37/T90 -- two state-mutating scripts had no `--help`.** A script that
    takes arguments and cannot explain them gets invoked wrongly, and the
    specific way that bites here is a tool falling through to its default
    action on input it did not understand. `route.py` did exactly that once and
    silently consumed a routing roll.

Both leave a machine-readable trace, unlike the failure class that dominates
this project (a claim broader than its evidence). So they are worth automating
precisely because they are the cheap half.

WHAT IT CHECKS
--------------
1. **A NEW script is named somewhere in the playbook.** Bounded by a baseline,
   the same trick `audit.py` uses: it reports what appeared since the last run,
   not the whole world. Without that bound this tool would open with ~47
   findings and be ignored by its second run -- an alarm that always fires is
   not an alarm.
2. **A script that reads arguments has a help path.** Checked STATICALLY, by
   reading source. It must never be checked by executing `--help`, because a
   script that does not handle the flag would fall through and DO ITS JOB --
   which for `route.py` means consuming a roll, and for `run_game.sh` means
   launching the game. The check for "does it mishandle arguments" must not
   mishandle arguments.

WHAT IT DELIBERATELY DOES NOT FLAG
----------------------------------
* **Files with no shebang** -- `display_isolate.sh` is sourced, not executed.
  There is nothing to pass `--help` to. Exempt by shebang, not by name.
* **Scripts that read no arguments** -- the `test_*.py` runners take none, so
  they have nothing to document. Exempt by argv use, not by name.
* Anything that is not `.py` or `.sh`. Seven `.log` files live in `scripts/`.

Both exemptions are DERIVED, not allowlisted. An allowlist of names would have
to be maintained, and the first tool someone forgot to add to it would be
exempted silently -- the same failure this script exists to catch.

THE BACKLOG IS REPORTED, NOT HIDDEN
-----------------------------------
Most existing scripts predate the inventory rule. That count is printed every
run as context. It is deliberately NOT a finding: rolling it in would bury the
one new thing you actually did today. But it is not suppressed either -- a lint
that quietly narrows its own scope while printing a broad claim is the exact
defect recorded in T90.

Usage:
    scripts/lint_tools.py             # report, update the baseline, exit 0
    scripts/lint_tools.py --dry-run   # report, do NOT touch the baseline
    scripts/lint_tools.py --strict    # exit 1 if there are findings
    scripts/lint_tools.py --self-check
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PLAYBOOK = ROOT / "docs" / "diagnostic-playbook.md"
STATE = ROOT / "docs" / ".lint-tools-state.json"

SUFFIXES = {".py", ".sh"}


def scan(text):
    """(is_executable, reads_args, has_help) for one script's source.

    `reads_args` is deliberately generous -- argparse, sys.argv, a positional
    `$1`, or getopts. A false positive here costs one line of documentation; a
    false negative lets an undocumented interface through, which is the thing
    that actually cost us.
    """
    executable = text.startswith("#!")
    reads_args = bool(re.search(r"sys\.argv|\bargparse\b|\bgetopts\b|\$\{?[1-9]", text))
    has_help = bool(re.search(r"--help|\bargparse\b|-h\b", text))
    return executable, reads_args, has_help


def scripts():
    """Every real script, sorted. Not .log files, not directories, not dotfiles."""
    return sorted(p for p in SCRIPTS.iterdir()
                  if p.is_file() and p.suffix in SUFFIXES and not p.name.startswith("."))


def documented(name, playbook_text):
    """Is this script named anywhere in the playbook?

    Anywhere, not just the inventory table -- several tools are documented in
    the gate that uses them, and demanding a table row for those would push
    people to add a row rather than an explanation.
    """
    return name in playbook_text


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"known": [], "runs": 0}


def findings(paths, playbook_text, known):
    """(new_undocumented, no_help, backlog). Pure -- so self_check can drive it."""
    new_undoc, no_help, backlog = [], [], []
    for p in paths:
        text = p.read_text(errors="replace")
        executable, reads_args, has_help = scan(text)
        is_new = p.name not in known
        if not documented(p.name, playbook_text):
            (new_undoc if is_new else backlog).append(p.name)
        if executable and reads_args and not has_help:
            no_help.append(p.name)
    return new_undoc, no_help, backlog


def self_check():
    """Controls that DISCRIMINATE -- each must be able to fail (T65/T71)."""
    import tempfile
    checks = []

    # 1. The exemptions must be real discriminations, not name matches. A
    #    synthetic tree with one of each shape: only the bad one may be flagged.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "bad_tool.py").write_text("#!/usr/bin/env python3\nimport sys\nx=sys.argv[1]\n")
        (d / "sourced_lib.sh").write_text("# no shebang, sourced\nfoo() { echo \"$1\"; }\n")
        (d / "test_runner.py").write_text("#!/usr/bin/env python3\nprint('no args read')\n")
        (d / "good_tool.py").write_text("#!/usr/bin/env python3\nimport sys\n"
                                        "if '--help' in sys.argv: print(__doc__)\n")
        (d / "notes.log").write_text("#!/usr/bin/env python3\nimport sys\nsys.argv\n")
        paths = sorted(p for p in d.iterdir() if p.suffix in SUFFIXES)
        _nu, no_help, _bk = findings(paths, "", [])
        want = ["bad_tool.py"]
        checks.append(("flags a no-help tool; exempts lib / no-arg / documented",
                       no_help == want, f"flagged {no_help}, want {want}"))

        # 2. The .log files in scripts/ must be ignored -- notes.log above is
        #    deliberately written with a shebang and argv use, so a suffix
        #    filter that stopped working would flag it.
        checks.append(("ignores non-.py/.sh files even when they look like code",
                       "notes.log" not in no_help, f"no_help={no_help}"))

        # 3. NEW vs BACKLOG must actually separate. Same tree, same texts, only
        #    the baseline differs -- so this fails if the bound is ignored.
        nu_a, _h, bk_a = findings(paths, "", [])
        nu_b, _h, bk_b = findings(paths, "", [p.name for p in paths])
        checks.append(("baseline separates new findings from backlog",
                       bool(nu_a) and not nu_b and not bk_a and bool(bk_b),
                       f"unseeded new={len(nu_a)}/backlog={len(bk_a)}; "
                       f"seeded new={len(nu_b)}/backlog={len(bk_b)}"))

        # 4. Documented-ness must be read from the playbook text, not assumed.
        nu_doc, _h, bk_doc = findings(paths, " ".join(p.name for p in paths), [])
        checks.append(("a named script is not reported as undocumented",
                       not nu_doc and not bk_doc,
                       f"new={nu_doc}, backlog={bk_doc}"))

    # 5. This tool must satisfy its OWN rule. A linter that would flag itself
    #    has no standing to flag anything else.
    ex, ra, hh = scan(Path(__file__).read_text())
    checks.append(("this script passes its own --help rule", ex and ra and hh,
                   f"shebang={ex}, reads_args={ra}, has_help={hh}"))

    # 6. ...and must be documented in the playbook, by the same function that
    #    judges everything else.
    pb = PLAYBOOK.read_text() if PLAYBOOK.exists() else ""
    checks.append(("this script is named in the playbook", documented(Path(__file__).name, pb),
                   "present" if documented(Path(__file__).name, pb) else
                   "MISSING -- add its Tool inventory row (T71 gate 3)"))

    bad = sum(1 for _n, ok, _d in checks if not ok)
    for name, ok, detail in checks:
        print(f"{'ok  ' if ok else 'FAIL'}  {name:56} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    unknown = [x for x in a if x not in {"--dry-run", "--strict", "--self-check", "--help", "-h"}]
    if unknown:
        # Never fall through to the state-mutating default on input we did not
        # understand -- the T37 failure this script partly exists to prevent.
        print(f"[tools] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print("[tools] REFUSING rather than guessing.", file=sys.stderr)
        return 2
    dry = "--dry-run" in a

    if not PLAYBOOK.exists():
        print("[tools] docs/diagnostic-playbook.md missing — cannot judge documentation.",
              file=sys.stderr)
        return 1

    paths = scripts()
    st = load_state()
    known = st["known"]
    seeding = not known
    new_undoc, no_help, backlog = findings(paths, PLAYBOOK.read_text(), known)

    print(f"[tools] {len(paths)} script(s); baseline holds {len(known)}"
          f"{' (SEEDING — first run)' if seeding else ''}")

    n = 0
    if seeding:
        # On the first run everything is new, so calling it all a finding would
        # be a wall of noise that teaches you to ignore this tool on day two.
        # Seed quietly and say plainly that that is what happened.
        print(f"[tools] first run: baseline seeded with {len(paths)} script(s). "
              f"NOTHING is reported as new — by construction, not because it is clean.")
    elif new_undoc:
        n += len(new_undoc)
        print(f"[tools] {len(new_undoc)} NEW script(s) not named anywhere in the playbook "
              f"(T71 gate 3 — a tool's output is not evidence until it is written up):")
        for s in new_undoc:
            print(f"  - {s}")

    if no_help:
        n += len(no_help)
        print(f"[tools] {len(no_help)} script(s) read arguments but have no help path (T37):")
        for s in no_help:
            print(f"  - {s}")

    if backlog:
        print(f"[tools] context, NOT findings: {len(backlog)} pre-existing script(s) are "
              f"undocumented. This is a backlog, not a regression — it is printed every run "
              f"so it is not silently narrowed away.")

    if n == 0 and not seeding:
        print("[tools] OK — every new script is documented and every argument-taking "
              "script has a help path.")

    if not dry:
        st["known"] = [p.name for p in paths]
        st["runs"] = st.get("runs", 0) + 1
        STATE.write_text(json.dumps(st, indent=1))
    else:
        print("[tools] --dry-run: baseline not updated.", file=sys.stderr)

    return 1 if (n and "--strict" in a) else 0


if __name__ == "__main__":
    sys.exit(main())
