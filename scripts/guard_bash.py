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

# (pattern, why it is refused, what to do instead)
RULES = [
    (re.compile(r"\bpkill\s+-f\b"),
     "`pkill -f` matches the command line of the shell running it -- it can kill "
     "its own shell, silently and misleadingly.",
     "Kill by PID (`kill -9 <pid>`), or let scripts/run_game.sh own the lifetime. "
     "To match the game by name use `comm` = 'SinPunishmentRe' (15-char truncation)."),

    (re.compile(r"cmake\s+--build\s+build"),
     "Building directly skips scripts/build.sh, which lints the probes BEFORE "
     "spending the cycle and snapshots the binary it is about to overwrite (T25/T26).",
     "Use `scripts/build.sh` (add --no-recomp for C++-only changes)."),

    (re.compile(r"(?<!\w)\.?/?build/SinPunishmentRecompiled(?!\w)"),
     "Launching the binary directly skips scripts/run_game.sh, which owns the "
     "detached watchdog, the early-exit/SIGSEGV report, the input-contamination "
     "check and the run log.",
     "Use `scripts/run_game.sh <secs> <log> [ENV=v...]`."),
]

# Read-only inspection of the binary is fine -- it is only *running* it that
# bypasses the watchdog.
SAFE = re.compile(r"\b(strings|ls|stat|cmp|md5sum|sha\d*sum|file|cp|nm|objdump|readelf|du)\b")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not cmd:
        return 0

    for pat, why, instead in RULES:
        if pat.search(cmd):
            if pat is RULES[2][0] and SAFE.search(cmd):
                continue          # inspecting the binary, not running it
            print(f"[guard] REFUSED: {why}\n[guard] Instead: {instead}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
