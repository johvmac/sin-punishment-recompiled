#!/usr/bin/env python3
"""Controls for lint_hooks.py's I17 check (MEM_* base must sign-extend).

Runs lint_hooks.py against TEMPORARY copies carrying one synthetic hook each,
never against the real sinpunishment.toml.

The cases that matter are the NEGATIVE ones. A checker that flags everything
would have "caught" I17 too, and would then be ignored within a day -- which is
the T29 argument for not over-mechanising. The nested `MEM_W(0, MEM_W(8, ...))`
form in particular is CORRECT (an int32_t result sign-extends on promotion) and
must not be flagged.

    scripts/test_lint_hooks.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "lint_hooks.py"

# (hook body, should_be_flagged_for_I17, label)
CASES = [
    ("unsigned int b = 1; MEM_W(i, b) = 0;",
     True,  "THE BUG: base is a 32-bit unsigned local"),
    ("MEM_W(0, (unsigned int)ctx->r2) = 0;",
     True,  "explicit narrowing cast on the base"),
    ("MEM_W(4, some_addr) = 0;",
     True,  "base is an unknown identifier, not ctx->rN"),

    ("MEM_W(0x84, ctx->r17);",
     False, "plain ctx->rN base"),
    ("MEM_W(i + 0x10, ctx->r2) = 0;",
     False, "displacement in the OFFSET arg, base still ctx->rN"),
    ("MEM_W(0x0, MEM_W(0x8, ctx->r4));",
     False, "NESTED MEM_* base — int32_t sign-extends, must NOT be flagged"),
    ("MEM_BU(ctx->r20, 0);",
     False, "two-arg form with ctx->rN as offset, base 0 is a literal"),
    ("fprintf(stderr, \"hi\\n\"); fflush(stderr);",
     False, "no MEM_* at all"),

    # The VERBATIM body that caused I17 on 2026-08-19, kept as a regression
    # case so the check can never silently stop catching the real thing.
    ("unsigned int b = (unsigned int)ctx->r2 + 0x10; unsigned int sz = 8; "
     "unsigned int i; for (i = 0; i + 3 < sz; i += 4) { MEM_W(i, b) = 0; }",
     True,  "VERBATIM I17 hook body from 2026-08-19"),
]

TOML_TMPL = """# ===== BEGIN SCRATCH DEBUG HOOKS =====
[[patches.hook]]
func = "boot_func_80026960"
before_vram = 0x80026978
text = "{body}"

# ===== END SCRATCH DEBUG HOOKS =====
"""


def run_case(body, tmp):
    root = Path(tmp) / "fake"
    shutil.rmtree(root, ignore_errors=True)
    (root / "scripts").mkdir(parents=True)
    shutil.copy(LINT, root / "scripts" / "lint_hooks.py")
    (root / "sinpunishment.toml").write_text(TOML_TMPL.format(body=body))
    p = subprocess.run([sys.executable, str(root / "scripts" / "lint_hooks.py")],
                       capture_output=True, text=True)
    return p.stdout + p.stderr


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    before = LINT.read_bytes()
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for body, want, label in CASES:
            out = run_case(body, tmp)
            got = "I17" in out
            ok = got == want
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'}  flagged={got!s:<5} want={want!s:<5} {label}")
    assert LINT.read_bytes() == before, "TEST MUTATED lint_hooks.py"

    # the real toml must stay clean
    p = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    real_ok = "I17" not in p.stdout
    print(f"\n{'ok  ' if real_ok else 'FAIL'}  real sinpunishment.toml raises no I17")
    bad += not real_ok

    print(f"\n{len(CASES) + 1 - bad}/{len(CASES) + 1} correct")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
