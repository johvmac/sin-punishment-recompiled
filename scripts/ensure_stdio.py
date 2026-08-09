#!/usr/bin/env python3
"""Inject stdio include into patched funcs + flag write traces."""
import glob, os
for f in sorted(glob.glob('RecompiledFuncs/funcs_*.c')):
    s = open(f).read()
    if '[flag]' in s and '#include <stdio.h>' not in s:
        s = '#include <stdio.h>\n' + s
        open(f, 'w').write(s)
        print('include added', f)
print('done')
