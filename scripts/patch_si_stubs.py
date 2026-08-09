#!/usr/bin/env python3
"""Post-processes N64Recomp output so SI-manager stubs return 0 in r2.

N64Recomp [patches] stubs emit an empty function body; the game's SI command
senders check the return value (0 = success -> controller present). This script
injects `ctx->r2 = 0;` into the stub bodies listed in SI_STUB_FUNCS.
Idempotent: skips functions that already contain the injected statement.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCS_DIR = ROOT / "RecompiledFuncs"

SI_STUB_FUNCS = {
    "boot_func_8004EA68",  # SI command sender
    "boot_func_8004EAD0",  # SI manager thread entry
    "boot_func_8004B800",  # PIF executor
    "boot_func_8004B610",  # PIF executor
    "boot_func_80046FE0",  # __osSiRawStartDma
}

INJECT = "    ctx->r2 = 0;"

def patch_file(path: Path) -> int:
    text = path.read_text()
    count = 0
    for name in SI_STUB_FUNCS:
        marker = f"RECOMP_FUNC void {name}("
        start = text.find(marker)
        if start == -1:
            continue
        # End of the stub body: find the next ";" + "}" closing (emit_function_end -> ";}")
        end_marker = ";}"
        end = text.find(end_marker, start)
        if end == -1:
            print(f"WARN: no body end found for {name} in {path.name}", file=sys.stderr)
            continue
        body = text[start:end]
        if INJECT in body:
            continue  # already patched
        # Insert right after the local variable declarations ("int c1cs = 0;")
        anchor = "int c1cs = 0;"
        ai = body.find(anchor)
        if ai == -1:
            print(f"WARN: anchor not found for {name} in {path.name}", file=sys.stderr)
            continue
        insert_at = start + ai + len(anchor)
        text = text[:insert_at] + "\n" + INJECT + text[insert_at:]
        count += 1
    if count:
        path.write_text(text)
    return count

total = 0
for p in sorted(FUNCS_DIR.glob("funcs_*.c")):
    total += patch_file(p)
print(f"Patched {total} SI stub(s) in RecompiledFuncs/")
