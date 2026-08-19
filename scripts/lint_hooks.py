#!/usr/bin/env python3
"""Pre-flight lint for the scratch debug hooks in sinpunishment.toml.

WHY
---
Three of the eleven instrument defects recorded in the ledger were the SAME
mistake -- a hook's `static` state being process-global rather than per-thread
(I4, I5, I8). One was byte access to RDRAM without the `^3` swap, which printed
byte-reversed values that read as exactly the bug being hunted (I7). One was a
probe with no positive control, where a dead probe and a clean negative look
identical (I1). One passed a 32-bit UNSIGNED value to `MEM_*`, which needs the
sign-extended `ctx->rN`; it wrote to a wild address and produced a clean,
convincing, entirely FALSE experimental result (I17).

All five were caught AFTER a ~3 minute recompile, a build, and a run -- and in
two cases only after a wrong conclusion had been drawn and written down. Every
one is a text pattern visible in the hook body before any of that is spent.

This runs before the build, so the cost of the mistake drops from a full
cycle plus a retraction to a few seconds.

It cannot check whether a probe measures the right thing. It checks the six
mistakes that have actually been made -- most of them more than once.

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


def _mem_args(body):
    """Yield (arg1, arg2) for every MEM_*(...) call in `body`.

    BOTH args, not just one: the macro computes `(reg) + (offset)`, and addition
    is commutative, so N64Recomp emits both orders and both are correct --
    `MEM_W(0X18, ctx->r29)` for `sw $ra,0x18($sp)` but `MEM_BU(ctx->r20, 0X0)`
    for `lbu $a0,0x0($s4)`. A check that assumed the register was always the
    second argument flagged the second form, which is valid generated code.

    Paren-balanced on purpose: an argument is legitimately allowed to be another
    MEM_* call, so a plain `MEM_\\w+\\([^,]+,([^)]+)\\)` splits in the wrong
    place and reports nonsense for exactly the nested form that is CORRECT.
    """
    for m in re.finditer(r"\bMEM_[A-Z]{1,2}\s*\(", body):
        i, depth, arg_start, first_arg_end = m.end(), 1, m.end(), None
        while i < len(body) and depth:
            c = body[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            elif c == "," and depth == 1 and first_arg_end is None:
                first_arg_end = i
            i += 1
        if first_arg_end is not None and depth == 0:
            yield body[arg_start:first_arg_end], body[first_arg_end + 1:i]


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
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

        # I17 -- MEM_* takes the SIGN-EXTENDED register. The macro is
        #     *(int32_t*)(rdram + (((reg) + (offset)) - 0xFFFFFFFF80000000))
        # so `reg` must sign-extend: `ctx->rN` (int64_t) or a nested MEM_* whose
        # int32_t result sign-extends on promotion. Hand it a 32-bit UNSIGNED
        # value and it zero-extends, the subtraction wraps, and the access lands
        # at a wild host address.
        #
        # This is flagged as an ERROR rather than a warning because of how it
        # fails: on 2026-08-19 it did not crash the probe visibly, it produced a
        # clean, plausible, entirely FALSE result (a 3s-vs-158s difference that
        # read exactly like the hypothesis under test). Caught only by asking
        # where the fault was -- gdb put frame #0 inside the hook's own function.
        for a1, a2 in _mem_args(body):
            args = [a1.strip(), a2.strip()]
            shown = f"{args[0]}, {args[1]}"
            if any("unsigned" in a for a in args):
                errors.append(f"{where}: `MEM_*({shown})` narrows an operand to "
                              f"unsigned, so it zero-extends and the access "
                              f"lands at a wild address. Pass `ctx->rN` and put "
                              f"the displacement in the other argument (I17).")
            elif not any("ctx->r" in a or a.startswith("MEM_") for a in args):
                errors.append(f"{where}: `MEM_*({shown})` has no sign-extending "
                              f"operand — neither argument is a `ctx->rN` or a "
                              f"nested MEM_*. A narrowed copy wraps (I17).")

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

        # A probe that fires near a crash MUST flush. A process killed by SIGSEGV
        # loses buffered stderr, so the most important line -- the one printed
        # microseconds before the fault -- is exactly the one that vanishes. On
        # 2026-08-18 that made a correct probe read as a clean negative and sent
        # the investigation off for two extra build cycles (A101).
        if "fprintf" in body and "fflush" not in body:
            warns.append(f"{where}: prints without fflush(stderr). If this fires "
                         f"near a crash the last line is LOST (A101).")

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
