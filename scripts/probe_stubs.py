#!/usr/bin/env python3
"""Inject a first-call probe into every silently-stubbed recompiled function.

WHY THIS EXISTS
---------------
N64Recomp emits an EMPTY BODY for any function it cannot recompile, and it does
so without failing the build. Twice already a silently-stubbed function turned
out to sit on the game's live per-frame path (docs/boot-debugging-2026-08-13.md,
2026-08-13 evening). There are currently ~137 of them, mostly overlay code, and
nothing tells us which are ever actually reached at runtime.

This rewrites every stub body to call `recomp_stub_hit("<name>")`, which the
runtime (ultramodern/src/events.cpp) reports once per function, stamped with the
current gfx task count, when SNP_STUB_PROBE=1. A stub whose FIRST call lands at
the frame the game stops rendering is the suspect; one that fired at boot is not.

The `extern` declaration is written inline inside the body, so no generated
header needs changing and the injection is self-contained and idempotent.

DIAGNOSTIC TOOL, NOT A FIX. Re-running scripts/recompile.sh regenerates
RecompiledFuncs/ and wipes this; that is intentional. Run it directly against an
already-generated tree (no recompile needed) and rebuild:

    python3 scripts/probe_stubs.py
    cmake --build build
    scripts/run_game.sh 50 /tmp/stubs.log SNP_HEARTBEAT=1 SNP_STUB_PROBE=1

Pass --revert to strip the injection again.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCS_DIR = ROOT / "RecompiledFuncs"

# A stub is a body whose only contents are the boilerplate locals N64Recomp
# always emits, followed immediately by the terminating `;}`. Any real function
# has instruction lines (and `// 0x` address comments) in between.
STUB_RE = re.compile(
    r"(RECOMP_FUNC void (\w+)\(uint8_t\* rdram, recomp_context\* ctx\) \{\n"
    r"    uint64_t hi = 0, lo = 0, result = 0;\n"
    r"    int c1cs = 0;\n"
    r")(;\})"
)

PROBE = (
    '    { extern void recomp_stub_hit(const char*); recomp_stub_hit("%s"); }\n'
)
PROBE_RE = re.compile(
    r"^    \{ extern void recomp_stub_hit\(const char\*\); "
    r'recomp_stub_hit\("\w+"\); \}\n',
    re.M,
)


def inject(text):
    count = 0

    def repl(m):
        nonlocal count
        count += 1
        return m.group(1) + (PROBE % m.group(2)) + m.group(3)

    return STUB_RE.sub(repl, text), count


def revert(text):
    return PROBE_RE.subn("", text)


def main():
    reverting = "--revert" in sys.argv
    if not FUNCS_DIR.is_dir():
        sys.exit(f"[probe_stubs] ERROR: {FUNCS_DIR} not found -- run recompile.sh first")

    sources = sorted(FUNCS_DIR.glob("*.c"))
    if not sources:
        sys.exit(f"[probe_stubs] ERROR: no .c files in {FUNCS_DIR}")

    total = 0
    touched = 0
    for path in sources:
        text = path.read_text()
        new_text, n = revert(text) if reverting else inject(text)
        if n:
            path.write_text(new_text)
            touched += 1
            total += n

    verb = "removed from" if reverting else "injected into"
    print(f"[probe_stubs] {total} stub probes {verb} {touched}/{len(sources)} files")
    if not reverting and total == 0:
        print("[probe_stubs] WARNING: found no stubs -- has the emitted shape changed?",
              file=sys.stderr)


if __name__ == "__main__":
    main()
