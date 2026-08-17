#!/usr/bin/env python3
"""Inject `#include <stdio.h>` into generated funcs that need it.

The generated `RecompiledFuncs/funcs_N.c` files include only "recomp.h" and
"funcs.h", neither of which pulls in <stdio.h>. Any scratch debug hook using
fprintf/stderr therefore fails to compile with `'stderr' undeclared` -- every
single time, because RecompiledFuncs/ is regenerated from scratch on each
recompile.sh run.

This used to trigger only on the literal string "[flag]" (an early debug-print
convention) and was not wired into recompile.sh at all, so it silently missed
every later probe convention -- "[probe]" hooks broke the build again on
2026-08-15. Now it detects actual stdio usage rather than one magic tag, and
recompile.sh calls it automatically.
"""
import glob
import re

# Any of these identifiers appearing in a generated file means it needs stdio.
NEEDS_STDIO = re.compile(r'\b(fprintf|printf|stderr|stdout|fputs|putchar|snprintf)\b')
INCLUDE = '#include <stdio.h>'

added = 0
for path in sorted(glob.glob('RecompiledFuncs/funcs_*.c')):
    with open(path) as fh:
        src = fh.read()
    if INCLUDE in src:
        continue
    if not NEEDS_STDIO.search(src):
        continue
    with open(path, 'w') as fh:
        fh.write(INCLUDE + '\n' + src)
    print(f'  include added: {path}')
    added += 1

print(f'ensure_stdio: {added} file(s) patched')
