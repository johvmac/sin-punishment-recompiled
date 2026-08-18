#!/usr/bin/env python3
"""Pre-flight lint for the scratch debug hooks in sinpunishment.toml.

WHY
---
Three of the eleven instrument defects recorded in the ledger were the SAME
mistake -- a hook's `static` state being process-global rather than per-thread
(I4, I5, I8). One was byte access to RDRAM without the `^3` swap, which printed
byte-reversed values that read as exactly the bug being hunted (I7). One was a
probe with no positive control, where a dead probe and a clean negative look
identical (I1).

All five were caught AFTER a ~3 minute recompile, a build, and a run -- and in
two cases only after a wrong conclusion had been drawn and written down. Every
one is a text pattern visible in the hook body before any of that is spent.

This runs before the build, so the cost of the mistake drops from a full
cycle plus a retraction to a few seconds.

It cannot check whether a probe measures the right thing. It checks the five
mistakes that have actually been made more than once.

Usage:
    scripts/lint_hooks.py            # warn, exit 0
    scripts/lint_hooks.py --strict   # exit 1 on any error-level finding
"""
import re
import sys
from pathlib import Path

TOML = Path(__file__).resolve().parent.parent / "sinpunishment.toml"
BEGIN = "# ===== BEGIN SCRATCH DEBUG HOOKS ====="
END = "# ===== END SCRATCH DEBUG HOOKS ====="


def hooks(text):
    """Yield (vram, func, body) for each scratch hook."""
    try:
        block = text[text.index(BEGIN):text.index(END)]
    except ValueError:
        return
    cur = {}
    for line in block.split("\n"):
        m = re.match(r'\s*func\s*=\s*"([^"]+)"', line)
        if m:
            cur["func"] = m.group(1)
        m = re.match(r"\s*before_vram\s*=\s*(0x[0-9A-Fa-f]+)", line)
        if m:
            cur["vram"] = m.group(1)
        m = re.match(r'\s*text\s*=\s*"(.*)"\s*$', line)
        if m:
            cur["body"] = m.group(1)
            yield cur.get("vram", "?"), cur.get("func", "?"), cur["body"]
            cur = {}


def main():
    if not TOML.exists():
        return 0
    text = TOML.read_text()
    errors, warns = [], []

    for vram, func, body in hooks(text):
        where = f"{func} @{vram}"

        # I4/I5/I8 -- three defects of one class. A hook's `static` is
        # process-global, and both thread 3 and thread 4 run this code.
        for m in re.finditer(r"static\s+(?!_Thread_local)", body):
            errors.append(f"{where}: `static` without `_Thread_local`. "
                          f"Hook statics are shared across threads (I4/I5/I8).")
            break

        # I7 -- byte access needs the endianness swap; word access does not.
        if re.search(r"rdram\s*\[", body) and "^3" not in body:
            errors.append(f"{where}: indexes `rdram[...]` with no `^3` swap. "
                          f"Byte reads come out reversed (I7).")

        # I1 -- a silent probe and a dead probe are indistinguishable.
        if "fprintf" in body and not re.search(r"ARM|first|control|HB ", body):
            warns.append(f"{where}: prints but has no arm/heartbeat line. "
                         f"Silence will be unreadable (I1, T16).")

        # I13 -- a per-call RDRAM read on the walk path cost ~15x and
        # suppressed the bug outright. Flag the read on known-hot functions.
        if re.search(r"\*\(unsigned\s*\*\)\s*\(\s*rdram", body) and \
                re.search(r"80033758|80026A54", func + vram):
            warns.append(f"{where}: per-call RDRAM read on a hot path. "
                         f"That is what I13 measured at ~15x slowdown.")

        # A hook that neither prints nor calls out is doing nothing observable.
        if "fprintf" not in body and "recomp_" not in body:
            warns.append(f"{where}: no fprintf and no runtime call -- "
                         f"is this hook doing anything?")

    for e in errors:
        print(f"[hooks] ERROR {e}")
    for w in warns:
        print(f"[hooks] warn  {w}")
    if not errors and not warns:
        n = sum(1 for _ in hooks(text))
        print(f"[hooks] OK — {n} scratch hook(s), nothing flagged.")
    return 1 if (errors and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(main())
