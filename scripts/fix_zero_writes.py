#!/usr/bin/env python3
"""Strip N64Recomp codegen's malformed writes to $zero from generated C.

N64Recomp's cgenerator is supposed to skip writes to $zero (MIPS register 0
-- always hardwired to 0 on real hardware, so writes to it are architectural
no-ops), but doesn't always: some instruction patterns (e.g. "sll $zero, $a0,
3") slip through and get emitted literally as "0 = <expr>;", which isn't
valid C (0 isn't an lvalue).

Deleting these lines is always behavior-preserving: a write to $zero can
never be observed on real MIPS hardware, so removing the (broken) C
statement that would have represented it changes nothing about program
behavior, regardless of whether the surrounding code is real logic or
misidentified data.
"""
import glob
import re

PATTERN = re.compile(r"^\s*0 = .*;\s*$")


def main():
    total = 0
    for path in sorted(glob.glob("RecompiledFuncs/funcs_*.c")):
        with open(path) as f:
            lines = f.readlines()
        new_lines = []
        removed = 0
        for line in lines:
            if PATTERN.match(line):
                removed += 1
                continue
            new_lines.append(line)
        if removed:
            with open(path, "w") as f:
                f.writelines(new_lines)
            print(f"{path}: removed {removed} write(s) to $zero")
            total += removed
    print(f"done. {total} total")


if __name__ == "__main__":
    main()
