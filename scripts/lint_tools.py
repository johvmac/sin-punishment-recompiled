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
3. **No script DEFAULTS an evidence path to /tmp** (T47, added after T95).
   T47 has been a standing constraint since 2026-08-19 and nothing ever checked
   it: `display_isolate.sh` grew the correct behaviour and nine scripts did not,
   and no tool compared them. Eleven cited filenames in the ledger are already
   unrecoverable this way. A constraint with no checker is a preference.

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
Most existing scripts predate the inventory rule, and nine predate the T47
check. Those counts are printed every run as context, and the T47 offenders are
printed BY NAME. They are deliberately NOT findings: nine permanent findings
would make `--strict` exit 1 forever, and an alarm that always fires is one
nobody reads. But they are not suppressed either -- a lint that quietly narrows
its own scope while printing a broad claim is the exact defect recorded in T90.

The debt set lives in the state file and is rewritten each run from what still
violates, so fixing a script drops it off with no list to maintain by hand --
and re-introducing the fault afterwards then counts as the regression it is.

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

# T47: evidence goes to the archive drive, never /tmp. Matches a path being used
# as a DEFAULT -- a shell positional default, or a literal assignment. It does
# NOT match /tmp appearing in prose, a comment, or a refusal message, because
# gdb_trace.sh's own T47 fix talks about /tmp at length and a checker that
# flagged the fix for describing the bug would be useless.
TMP_DEFAULT = re.compile(r"""\$\{[0-9]+:-/tmp/ | =\s*["']/tmp/ | \bor\s+["']/tmp/""", re.X)

# Genuine scratch is fine and must not be flagged: a temp file that is deleted
# in the same run is not evidence. These are the idioms that create one.
SCRATCH_IDIOMS = ("mktemp", "TemporaryDirectory", "NamedTemporaryFile", "tempfile")


def tmp_defaults(text):
    """Lines that default an OUTPUT path to /tmp. [] if clean.

    Comment lines are skipped entirely. Without that, the very comment
    explaining a T47 fix trips the check that the fix satisfies.
    """
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("#"):
            continue
        if any(idiom in line for idiom in SCRATCH_IDIOMS):
            continue
        if TMP_DEFAULT.search(line):
            out.append((i, line.strip()))
    return out


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


def findings(paths, playbook_text, known, tmp_known=()):
    """(new_undocumented, no_help, backlog, tmp_new, tmp_debt). Pure, so
    self_check can drive it against a synthetic tree.

    `tmp_known` is the set of scripts ALREADY known to default to /tmp when this
    check was added (T95 enumerated eight). Those are debt, reported by name but
    not counted -- eight permanent findings would make --strict always exit 1,
    and an alarm that always fires is one nobody reads. A script NOT in that set
    is a regression and IS counted. The set is stored in state, so fixing one
    drops it off automatically without anyone editing a list.
    """
    new_undoc, no_help, backlog, tmp_new, tmp_debt = [], [], [], [], []
    for p in paths:
        text = p.read_text(errors="replace")
        executable, reads_args, has_help = scan(text)
        is_new = p.name not in known
        if not documented(p.name, playbook_text):
            (new_undoc if is_new else backlog).append(p.name)
        if executable and reads_args and not has_help:
            no_help.append(p.name)
        hits = tmp_defaults(text)
        if hits:
            (tmp_debt if p.name in tmp_known else tmp_new).append((p.name, hits))
    return new_undoc, no_help, backlog, tmp_new, tmp_debt


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
        _nu, no_help, _bk, _tn, _td = findings(paths, "", [])
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
        nu_a, _h, bk_a, _tn, _td = findings(paths, "", [])
        nu_b, _h, bk_b, _tn, _td = findings(paths, "", [p.name for p in paths])
        checks.append(("baseline separates new findings from backlog",
                       bool(nu_a) and not nu_b and not bk_a and bool(bk_b),
                       f"unseeded new={len(nu_a)}/backlog={len(bk_a)}; "
                       f"seeded new={len(nu_b)}/backlog={len(bk_b)}"))

        # 4. Documented-ness must be read from the playbook text, not assumed.
        nu_doc, _h, bk_doc, _tn, _td = findings(paths, " ".join(p.name for p in paths), [])
        checks.append(("a named script is not reported as undocumented",
                       not nu_doc and not bk_doc,
                       f"new={nu_doc}, backlog={bk_doc}"))

    # 4b. T47 DISCRIMINATION, on a synthetic tree with one of each shape. This
    #     is the control that matters: a regex tuned to today's nine offenders
    #     would pass a "does it find them" test while being useless. Each
    #     negative below is a way the check could be wrong in the SAFE
    #     direction (missing a real one) or the NOISY direction (flagging a
    #     compliant script), and both are failures.
    # THE FIXTURES ARE ASSEMBLED, NOT WRITTEN LITERALLY, and that is not
    # fastidiousness: the first version spelled them out and this linter FLAGGED
    # ITSELF at the line holding its own test data. The honest fix is to keep
    # the pattern out of this file's source -- NOT to exempt this file, which
    # would be a self-exemption and exactly the hole a checker must not have.
    # audit_l2.py records two earlier controls that failed the same way.
    T = "/" + "tmp"
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "shell_default.sh").write_text('#!/bin/bash\nLOG="${2:-' + T + '/x.log}"\n')
        (d / "py_default.py").write_text('#!/usr/bin/env python3\nLOG = "' + T + '/x.log"\n')
        (d / "compliant.sh").write_text(
            '#!/bin/bash\nLOG="${2:-/media/joh/extra/archive/evidence/x.log}"\n')
        (d / "scratch_ok.sh").write_text('#!/bin/bash\nX=$(mktemp ' + T + '/scratch.XXXX)\n')
        (d / "talks_about_tmp.sh").write_text(
            '#!/bin/bash\n# T47: never write LOG="${2:-' + T + '/x.log}" -- that is the bug\n'
            'echo "refusing to fall back to ' + T + '" >&2\n')
        paths = sorted(p for p in d.iterdir() if p.suffix in SUFFIXES)
        _n, _h, _b, tmp_new, _td2 = findings(paths, "", [], tmp_known=())
        got = sorted(n for n, _hits in tmp_new)
        want = ["py_default.py", "shell_default.sh"]
        checks.append(("T47: flags shell+python /tmp defaults; exempts archive "
                       "path, mktemp, and prose", got == want, f"flagged {got}, want {want}"))

        # 4c. The debt/regression split, driven twice over identical input with
        #     only the known-set changed. Without this the eight enumerated
        #     violations would count as findings forever.
        _n, _h, _b, tn_a, td_a = findings(paths, "", [], tmp_known=())
        _n, _h, _b, tn_b, td_b = findings(paths, "", [], tmp_known=[p.name for p in paths])
        checks.append(("T47: a known violator is debt, an unknown one is a regression",
                       bool(tn_a) and not td_a and not tn_b and bool(td_b),
                       f"unseeded new={len(tn_a)}/debt={len(td_a)}; "
                       f"seeded new={len(tn_b)}/debt={len(td_b)}"))

    # 4d. REAL-TREE control, two-sided. The two scripts that actually obey T47
    #     must come back clean -- a detector that flags everything passes 4b by
    #     accident but fails here.
    compliant = []
    for name in ("display_isolate.sh", "gdb_trace.sh"):
        f = SCRIPTS / name
        if f.exists() and tmp_defaults(f.read_text(errors="replace")):
            compliant.append(name)
    checks.append(("T47: the two compliant scripts are not flagged", not compliant,
                   f"wrongly flagged {compliant}" if compliant else
                   "display_isolate.sh and gdb_trace.sh both clean"))

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
    tmp_seeding = "tmp_known" not in st
    new_undoc, no_help, backlog, tmp_new, tmp_debt = findings(
        paths, PLAYBOOK.read_text(), known, st.get("tmp_known", []))

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

    if tmp_seeding:
        allv = tmp_new + tmp_debt
        print(f"[tools] T47 first run: {len(allv)} script(s) default evidence to /tmp, "
              f"recorded as enumerated debt (T95). NOT counted as findings — eight permanent "
              f"findings would make --strict always exit 1. A script that acquires a /tmp "
              f"default LATER is a regression and WILL be counted:")
        for name, hits in sorted(allv):
            print(f"  - {name}:{hits[0][0]}  {hits[0][1][:70]}")
    else:
        if tmp_new:
            n += len(tmp_new)
            print(f"[tools] {len(tmp_new)} script(s) NEWLY default evidence to /tmp — T47 says "
                  f"evidence goes to the archive drive, never /tmp (11 cited files are already "
                  f"unrecoverable this way):")
            for name, hits in sorted(tmp_new):
                for ln, src in hits:
                    print(f"  - {name}:{ln}  {src[:70]}")
        if tmp_debt:
            print(f"[tools] context, NOT findings: {len(tmp_debt)} script(s) still carry the "
                  f"known T47 debt ({', '.join(sorted(nm for nm, _ in tmp_debt))}). Named every "
                  f"run so it is not silently narrowed away; pass an explicit archive path.")

    if backlog:
        print(f"[tools] context, NOT findings: {len(backlog)} pre-existing script(s) are "
              f"undocumented. This is a backlog, not a regression — it is printed every run "
              f"so it is not silently narrowed away.")

    if n == 0 and not seeding and not tmp_seeding:
        print("[tools] OK — every new script is documented, every argument-taking script has "
              "a help path, and nothing newly writes evidence to /tmp.")

    if not dry:
        st["known"] = [p.name for p in paths]
        # Only scripts that STILL violate stay in the debt set, so fixing one
        # drops it off with no list to edit by hand -- and re-introducing it
        # afterwards then counts as the regression it is.
        st["tmp_known"] = sorted(nm for nm, _ in (tmp_new + tmp_debt))
        st["runs"] = st.get("runs", 0) + 1
        STATE.write_text(json.dumps(st, indent=1))
    else:
        print("[tools] --dry-run: baseline not updated.", file=sys.stderr)

    return 1 if (n and "--strict" in a) else 0


if __name__ == "__main__":
    sys.exit(main())
