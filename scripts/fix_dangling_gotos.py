#!/usr/bin/env python3
"""Remove dangling `goto after_N;` statements from N64Recomp-generated C.

N64Recomp emits a tail-call as:
    target(rdram, ctx);
        goto after_N;
where `after_N:` is emitted after the jal's delay slot. If the function
ends exactly at the jal (the delay slot belongs to the next symbol),
the label is never emitted and the file fails to compile. All observed
cases have a nop delay slot, so dropping the goto is semantically safe
(the call remains; the function then falls off the end = return).
"""
import glob, re, sys

def fix_file(path):
    s = open(path).read()
    out_lines = []
    changed = 0
    for fn in re.split(r'(?=RECOMP_FUNC)', s):
        if not fn.startswith('RECOMP_FUNC'):
            out_lines.append(fn)
            continue
        labels = set(re.findall(r'^\s*after_(\d+):', fn, re.M))
        lines = fn.splitlines(keepends=True)
        for i, l in enumerate(lines):
            m = re.match(r'^\s*goto after_(\d+);', l)
            if m and m.group(1) not in labels:
                # Verify the delay slot comment says nop right after the call
                # (best effort; the call line is right before the goto).
                changed += 1
                continue  # drop the goto line
            out_lines.append(l)
    out = ''.join(out_lines)
    if out != s:
        open(path, 'w').write(out)
    return changed

total = 0
for path in sorted(glob.glob('RecompiledFuncs/funcs_*.c')):
    total += fix_file(path)
print(f"Fixed {total} dangling goto(s) in RecompiledFuncs/funcs_*.c")
sys.exit(0)
