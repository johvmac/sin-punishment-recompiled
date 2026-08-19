#!/usr/bin/env python3
"""Iteratively regenerate + syntax-check the recompiled C code, fixing
"label used but not defined" errors by reusing auto_stub_pass.py's
classify_branch()/split_symbol()/add_stub() machinery.

Why this belongs here rather than as new logic: N64Recomp tolerates a
function branching outside its own declared bounds with just a
"[Warn] Function X is branching outside of the function" -- it still emits a
"goto L_ADDR;" for the target, but since ADDR is outside the function, the
corresponding label is never generated, so the C compiler fails with "label
used but not defined". This is exactly the same symbol-boundary problem
auto_stub_pass.py already fixes (tail-merge splits, data-gap stubs, etc.) --
it just wasn't loud enough to stop N64Recomp itself, only the later C build.
So: parse the C compiler's error instead of N64Recomp's, resolve it to
(containing function, target address), and hand it to the exact same
classify_branch() used for "Unhandled branch" errors.

Usage: scripts/auto_label_fix.py [--max-fixes N] [--dry-run]
"""

# T37 GUARD. This script MUTATES state -- it regenerates code and rewrites
# files. route.py once fell through an unrecognised `--help` into its
# state-mutating default and consumed a live routing roll; the same shape here
# would silently run a code-regeneration pass. Recognise it explicitly and exit.
import sys as _sys
if "--help" in _sys.argv or "-h" in _sys.argv:
    print(__doc__)
    _sys.exit(0)
import argparse
import glob
import multiprocessing
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from auto_stub_pass import (  # noqa: E402
    ROOT, TOML_PATH, SYMS_PATH,
    load_symbols, classify_branch, split_symbol, insert_symbol,
    add_stub, current_stubs, derive_split_name, section_prefix,
)

CC = "cc"
INCLUDES = [
    "-Iinclude",
    "-Ilib/N64ModernRuntime/ultramodern/include",
    "-Ilib/N64ModernRuntime/librecomp/include",
    "-Ilib/N64ModernRuntime/N64Recomp/include",
]
DEFINES = ["-DHLSL_CPU", "-DPLUME_SDL_VULKAN_ENABLED", "-DRT64_SDL_WINDOW_VULKAN", "-D__PRFCHWINTRIN_H"]
CFLAGS = ["-std=gnu17", "-fno-strict-aliasing", "-Wno-unused-variable", "-Wno-implicit-function-declaration", "-fsyntax-only"]

RE_IN_FUNCTION = re.compile(r"^(.+\.c): In function [‘'\"]([^’'\"]+)[’'\"]:")
RE_UNDEFINED_LABEL = re.compile(r"error: label [‘'\"]L_([0-9A-Fa-f]+)[’'\"] used but not defined")
RE_LVALUE = re.compile(r"error: lvalue required as left operand of assignment")


def regenerate():
    proc = subprocess.run(["./scripts/recompile.sh"], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode == 0, proc.stdout + proc.stderr


def _check_one(path):
    """Runs in a worker process: compile one file, return its parsed errors."""
    proc = subprocess.run(
        [CC, *DEFINES, *INCLUDES, *CFLAGS, "-c", path, "-o", "/dev/null"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return []
    errors = []
    current_fn = None
    for line in proc.stderr.splitlines():
        m = RE_IN_FUNCTION.match(line)
        if m:
            current_fn = m.group(2)
            continue
        lbl = RE_UNDEFINED_LABEL.search(line)
        if lbl and current_fn:
            errors.append((current_fn, "label", int(lbl.group(1), 16)))
            continue
        if RE_LVALUE.search(line) and current_fn:
            errors.append((current_fn, "lvalue", None))
    return errors


def syntax_check_all():
    """Returns list of (function_name, kind, extra) for every parseable error
    across every generated file. Files are independent -- compiled in
    parallel across all cores instead of one at a time."""
    paths = sorted(glob.glob(str(ROOT / "RecompiledFuncs" / "funcs_*.c")))
    errors = []
    workers = multiprocessing.cpu_count()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for file_errors in pool.map(_check_one, paths):
            errors.extend(file_errors)
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fixes", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fixes = 0
    while fixes < args.max_fixes:
        ok, out = regenerate()
        if not ok:
            print(f"STOP: recompile.sh failed (not a syntax issue this script handles).\n{out[-2000:]}")
            break

        errors = syntax_check_all()
        if not errors:
            print(f"SUCCESS after {fixes} fix(es): all generated files pass -fsyntax-only.")
            break

        print(f"=== round: {len(errors)} error(s) found, batch-fixing ===")
        touched_this_round = set()
        stopped = False
        for fn_name, kind, extra in errors:
            if fixes >= args.max_fixes:
                break
            if fn_name in touched_this_round:
                continue  # already split/stubbed earlier in this same batch

            if kind == "lvalue":
                # Shouldn't normally reach here (fix_zero_writes.py handles this
                # class permanently in recompile.sh) -- if it does, something new
                # slipped through; don't guess, surface it.
                print(f"STOP: unexpected lvalue error in {fn_name} after zero-write post-processing. Needs manual review.")
                stopped = True
                break

            # Reload fresh each time (cheap, local) so fixes within this batch
            # see each other's changes without a full pipeline regenerate.
            section_syms, name_to_section, section_bounds = load_symbols()
            toml_text = TOML_PATH.read_text()
            stubbed_names = current_stubs(toml_text)

            target = extra
            verdict, reason, more = classify_branch(section_syms, name_to_section, section_bounds, fn_name, target, stubbed_names)
            if verdict is None:
                print(f"STOP: undefined label 0x{target:X} in {fn_name} -- not auto-fixable ({reason}). Needs manual review.")
                stopped = True
                break

            if verdict == "stub":
                comment = f"auto(label-fix): goto to 0x{target:X} unresolved ({reason})"
                action = f"AUTO-STUB {fn_name}: {comment}"
                if not args.dry_run:
                    toml_text = add_stub(toml_text, fn_name, comment)
                    TOML_PATH.write_text(toml_text)
            elif verdict == "gap":
                gap_start, gap_end = more
                section = name_to_section[fn_name]
                prefix = section_prefix(section_syms[section])
                new_name = f"{prefix}{gap_start:08X}"
                action = f"AUTO-SEED {new_name} (0x{gap_start:X}, 0x{gap_end - gap_start:X}) in section {section}: {reason}"
                if not args.dry_run:
                    syms_text = SYMS_PATH.read_text()
                    syms_text = insert_symbol(syms_text, section, new_name, gap_start, gap_end - gap_start)
                    SYMS_PATH.write_text(syms_text)
            else:  # split
                vram, size, name = more
                end_addr = vram + size
                new_name = derive_split_name(name, vram, target)
                action = (f"AUTO-SPLIT {name} (0x{vram:X}+{size:#x}) at 0x{target:X}: "
                          f"-> {name} (0x{vram:X}, 0x{target - vram:X}) + {new_name} (0x{target:X}, 0x{end_addr - target:X}) — {reason}")
                if not args.dry_run:
                    syms_text = SYMS_PATH.read_text()
                    syms_text = split_symbol(syms_text, name, vram, target, end_addr, new_name)
                    SYMS_PATH.write_text(syms_text)

            print(f"  {action}")
            touched_this_round.add(fn_name)
            fixes += 1

        if stopped:
            break
        if not touched_this_round:
            print("STOP: no progress possible this round (all remaining errors need manual review).")
            break
    else:
        print(f"STOP: hit --max-fixes cap ({args.max_fixes}).")

    print(f"\n{fixes} fix(es) this run.")


if __name__ == "__main__":
    main()
