#!/usr/bin/env python3
"""Post-processes N64Recomp output so SI-manager stubs return 0 in r2.

N64Recomp [patches] stubs emit an empty function body; the game's SI command
senders check the return value (0 = success -> controller present). This script
injects `ctx->r2 = 0;` into the stub bodies listed in SI_STUB_FUNCS.
Idempotent: skips functions that already contain the injected statement.
"""
import sys as _sys
if "--help" in _sys.argv or "-h" in _sys.argv:
    print(__doc__)
    _sys.exit(0)
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

# __osSiRawStartDma additionally needs to synthesise the SI-DMA-complete
# interrupt that real hardware fires when the transfer finishes.
#
# Why: the game's own controller-detection probe (boot_func_8003D5B0) is a
# request/reply pair -- `jal 0x80046FE0` (start the DMA) immediately followed
# by `osRecvMesg` on the queue it registered via osSetEventMesg(OS_EVENT_SI).
# Stubbing __osSiRawStartDma to a bare `return 0` means no DMA starts, so no
# completion interrupt ever fires, so that osRecvMesg blocks forever. That
# deadlocks the SI-manager thread ([Game] 6), which never replies to the main
# game thread ([Game] 3), which freezes the whole game. Confirmed by live gdb
# backtrace on 2026-08-14 (see docs/boot-debugging-2026-08-13.md).
#
# ultramodern::send_si_message() posts to exactly the queue the game
# registered for OS_EVENT_SI, which is the same notification real hardware
# would deliver. Declared extern locally so no generated header needs editing.
SI_EVENT_FUNCS = {"boot_func_80046FE0"}

INJECT_SI_EVENT = (
    "    { extern void recomp_trigger_si_event(uint8_t*, recomp_context*);\n"
    "      recomp_trigger_si_event(rdram, ctx); }"
)

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
        # Safety guard: only ever inject into an ACTUAL stub. A stubbed
        # function's body is just the local declarations -- no translated
        # instructions, so no "// 0x........:" disassembly comments. If a name
        # in SI_STUB_FUNCS gets un-stubbed in sinpunishment.toml (as
        # boot_func_8004EA68/8004EAD0 were on 2026-08-15) this list would
        # otherwise silently inject `ctx->r2 = 0;` into the top of the real
        # 300-line body, clobbering $v0 at entry. Caught in review; guard added
        # so the two lists can never drift apart again.
        if "// 0x" in body:
            print(f"SKIP: {name} is not stubbed (real body) in {path.name}", file=sys.stderr)
            continue
        # Insert right after the local variable declarations ("int c1cs = 0;")
        anchor = "int c1cs = 0;"
        ai = body.find(anchor)
        if ai == -1:
            print(f"WARN: anchor not found for {name} in {path.name}", file=sys.stderr)
            continue
        injection = INJECT
        if name in SI_EVENT_FUNCS:
            injection = INJECT + "\n" + INJECT_SI_EVENT
        insert_at = start + ai + len(anchor)
        text = text[:insert_at] + "\n" + injection + text[insert_at:]
        count += 1
    if count:
        path.write_text(text)
    return count

total = 0
for p in sorted(FUNCS_DIR.glob("funcs_*.c")):
    total += patch_file(p)
print(f"Patched {total} SI stub(s) in RecompiledFuncs/")
