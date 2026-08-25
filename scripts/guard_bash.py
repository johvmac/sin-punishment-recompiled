#!/usr/bin/env python3
"""PreToolUse guard: refuse shell commands that bypass a mechanised discipline.

WHY
---
Wiring a rule into a script only helps if the script is actually the path taken.
Every guarded rule below already has a tool that does it correctly, and every one
was still violated by hand at least once -- including on the day the tooling was
written:

  * `pkill -f <binary>` matches the command line of the shell running it, so it
    kills its own shell and fails silently and misleadingly. `run_game.sh` kills
    by PID for exactly this reason. It was still typed by hand on 2026-08-18 to
    kill a log tail; it happened not to self-match, which was luck.

  * `cmake --build build` directly skips `scripts/build.sh`, which lints the
    probes first and snapshots the binary it is about to overwrite. Losing those
    snapshots is T25 -- it cost the only available control for A86.

  * Launching the binary directly skips `run_game.sh`, which owns the detached
    watchdog (a run once orphaned for 2h36m), the early-exit/SIGSEGV report, the
    input-contamination check, and the run log.

This is a guard, not a policy: it explains and points at the right tool. Exit 2
blocks the call and returns the message to the model.
"""
import json
import re
import sys
from pathlib import Path

# (pattern, why it is refused, what to do instead)
RULES = [
    (re.compile(r"\bpkill\s+-f\b"),
     "`pkill -f` matches the command line of the shell running it -- it can kill "
     "its own shell, silently and misleadingly.",
     "Kill by PID (`kill -9 <pid>`), or let scripts/run_game.sh own the lifetime. "
     "To match the game by name use `comm` = 'SinPunishmentRe' (15-char truncation). "
     "THE SAME TRAP HAS A READ-ONLY FORM, AND IT IS DELIBERATELY NOT A RULE "
     "(2026-08-25): a wait-loop like `until ... ! pgrep -f X` self-matches the "
     "shell running it, so it never exits -- and unlike the kill case it fails "
     "SILENTLY, which is worse. It is not guarded because pgrep is a legitimate "
     "read used constantly and blocking it would fire on correct uses; T118 "
     "measured that class of noise at 6-of-7 and T29 is why that matters. Use "
     "`comm`, or a pattern that cannot appear in your own command line."),

    (re.compile(r"cmake\s+--build\s+build(?![\w-])"),
     "Building directly skips scripts/build.sh, which lints the probes BEFORE "
     "spending the cycle and snapshots the binary it is about to overwrite (T25/T26).",
     "Use `scripts/build.sh` (add --no-recomp for C++-only changes)."),

    (re.compile(r"(?<!\w)\.?/?build/SinPunishmentRecompiled(?!\w)"),
     "Launching the binary directly skips scripts/run_game.sh, which owns the "
     "detached watchdog, the early-exit/SIGSEGV report, the input-contamination "
     "check and the run log.",
     "Use `scripts/run_game.sh <secs> <log> [ENV=v...]`."),
]

# Inspecting the binary is fine -- it is only *running* it unsupervised that
# bypasses the watchdog. A debugger session is deliberate and supervised, so
# gdb is allowed through: blocking it would push debugging outside the tooling
# rather than into it, which is the opposite of the point.
#
# The project's own supervised runners are listed explicitly. `\bgdb\b` does NOT
# match `gdb_watch.sh` -- `_` is a word character, so the boundary fails -- and
# on 2026-08-19 that blocked `scripts/gdb_watch.sh <addr> ... build/Sin...`,
# whose entire job is to run the binary under a debugger with its own deadline
# thread. Those scripts each own a watchdog, which is the property this rule is
# protecting; refusing them pushes debugging OUT of the tooling, which the
# comment above says is the opposite of the point. Per-statement evaluation
# (T40) keeps the exemption from vouching for a launch sitting beside it.
SAFE = re.compile(r"\b(strings|ls|stat|cmp|md5sum|sha\d*sum|file|cp|nm|objdump|readelf|du|gdb)\b"
                  r"|scripts/(gdb_watch|gdb_threads|gdb_fault|run_game)\.sh")

# Rules are evaluated PER STATEMENT, not against the whole command (T40).
#
# The exemption above used to be `SAFE.search(cmd)` over the entire command
# string, so a single safe-listed word ANYWHERE disabled the binary-launch
# refusal for everything else in that command:
#
#     echo build/SinPunishmentRecompiled              -> REFUSED (correct)
#     ls >/dev/null; echo build/SinPunishmentRecompiled -> ALLOWED (wrong)
#
# Ordinary compound commands trip this constantly -- `sha256sum`, `ls`, `stat`
# and `cp` are exactly what a checkpoint command contains -- so the guard was
# silently inert for much of a session while still passing its own liveness
# control, as long as that control was bundled with anything else. Splitting
# first means a SAFE token only ever exempts the statement it appears in.
SPLIT = re.compile(r"\|\||&&|\$\(|[;\n|&()`]")


# PIPELINE-LEVEL RULE: merging stderr into a pipe and then TRUNCATING it (A198).
#
# WHY IT IS NOT IN `RULES`: the rules above are evaluated per STATEMENT, and
# `SPLIT` breaks on `|`. So `scripts/foo.py 2>&1 | tail -25` arrives as two
# separate segments and no per-statement pattern can see the shape at all. This
# hazard IS the pipe, so it has to be matched across one.
#
# WHAT IT COST: on 2026-08-20 `rom_disasm.py` printed a warning naming 15
# candidate overlays -- correct, complete, on stderr -- and `2>&1 | tail -25`
# dropped it. 25 lines of confident, wrong disassembly were read as the answer
# and written into the ledger as a finding about the wrong overlay (A196). The
# lesson already existed as T76/T84 ("check what a pipe DROPS") and did not
# prevent it, which is why this is a guard and not another note.
#
# SCOPE, stated inside the rule: `head`/`tail` only, and only when a project
# script is in the pipeline. `grep` drops output too, and deliberately -- but it
# drops by CONTENT, which is a choice you make, whereas head/tail drop by
# POSITION, which is a choice you did not know you were making. Refusing every
# `2>&1 | grep` would be constant friction for a smaller hazard. That is a
# judgement, and it means THIS GUARD DOES NOT COVER `2>&1 | grep`.
PIPE_SPLIT = re.compile(r"\|\||&&|\$\(|[;\n()`]")
MERGES_STDERR = re.compile(r"2>&1")
TRUNCATES = re.compile(r"\|\s*(head|tail)\b")
PROJECT_SCRIPT = re.compile(r"scripts/[\w.-]+\.(py|sh)\b")


def pipelines(cmd):
    """Split into PIPELINES -- like statements(), but `|` is kept intact."""
    return [s for s in PIPE_SPLIT.split(cmd) if s and s.strip()]


def truncated_stderr(cmd):
    """The first pipeline that merges stderr into a truncating pipe, or None."""
    for p in pipelines(cmd):
        if MERGES_STDERR.search(p) and TRUNCATES.search(p) and PROJECT_SCRIPT.search(p):
            return p
    return None


def statements(cmd):
    """Split a shell command into rough simple-command segments.

    Deliberately crude: separators, command substitution and backticks. It only
    has to be fine-grained enough that a safe command cannot vouch for an
    unrelated one sitting beside it.
    """
    return [s for s in SPLIT.split(cmd) if s and s.strip()]


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def exempt_build(full_cmd):
    """True when a direct build targets something OUTSIDE this repository.

    WHY THIS EXISTS (2026-08-25). The build rule is pure text with no notion of
    WHERE it is building, so it fired on a third-party tree -- `ares-64`, whose
    build directory is also called `build` -- where nothing of ours was at
    stake. **That is worse than a nuisance: it taught me to route around a
    guard, and a guard that trains evasion is worse than no guard.** The rule's
    whole purpose is protecting OUR binary and OUR probe lint (T25/T26), and
    neither is involved in someone else's tree.

    The guard is handed only the command text -- never a cwd -- and rules match
    per STATEMENT, so `cd /elsewhere` and the build land in different segments
    and the rule never saw the cd. Hence: read the cd out of the FULL command.

    DELIBERATELY CONSERVATIVE. No cd at all means the project's own tree, so the
    rule still fires -- the common case is unchanged. Only an explicit cd to a
    path outside the repo exempts, and a relative cd resolves against the repo.
    """
    for m in re.finditer(r"(?:^|[;&|]|\bthen\b|\bdo\b)\s*cd\s+([^\s;&|]+)", full_cmd):
        raw = m.group(1).strip().strip('"').strip("'")
        try:
            target = Path(raw).expanduser()
            if not target.is_absolute():
                target = PROJECT_ROOT / target
            target = target.resolve()
        except Exception:
            continue
        if target != PROJECT_ROOT and PROJECT_ROOT not in target.parents:
            return True
    return False


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not cmd:
        return 0

    bad_pipe = truncated_stderr(cmd)
    if bad_pipe:
        print("[guard] REFUSED: this merges a project script's stderr into a pipe and "
              "then truncates by POSITION -- `head`/`tail` will silently drop whatever "
              "the script warned about. That is exactly how A196 happened: a REFUSING/"
              "NOTE line naming 15 candidate overlays was dropped, and the wrong "
              "overlay's disassembly was read as the answer.", file=sys.stderr)
        print(f"[guard] The pipeline: {bad_pipe.strip()}", file=sys.stderr)
        print("[guard] Instead: capture the streams separately and read BOTH --\n"
              "[guard]   scripts/foo.py ARGS >\"$O\" 2>\"$E\"; echo \"rc=$?\"; "
              "tail -20 \"$O\"; echo '--- stderr ---'; cat \"$E\"\n"
              "[guard] (stderr is usually short -- print it whole, and print it LAST.)",
              file=sys.stderr)
        return 2

    segments = statements(cmd)
    for pat, why, instead in RULES:
        # Scope the build rule to this repo (see exempt_build). Keyed on the
        # rule's own pattern text rather than its index, so reordering RULES
        # cannot silently attach the exemption to the wrong rule.
        if "--build" in pat.pattern and exempt_build(cmd):
            continue
        for seg in segments:
            if not pat.search(seg):
                continue
            if pat is RULES[2][0] and SAFE.search(seg):
                continue          # inspecting the binary in THIS statement, not running it
            print(f"[guard] REFUSED: {why}\n[guard] Instead: {instead}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
