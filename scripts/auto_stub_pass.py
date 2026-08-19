#!/usr/bin/env python3
"""Iteratively run N64Recomp, auto-stub low-risk compile blockers, and stop at
anything that needs a human look.

Three error classes are auto-fixed, matching the reasoning the project already
uses for its existing stub list (see sinpunishment.toml):

  1. "Unhandled cop0 register in mfc0/mtc0" and similar unsupported-instruction
     errors (cache ops, TLB ops) — these are libultra/OS internals N64Recomp
     can't lower, and the runtime reimplements the OS layer, so stubbing is
     the established, low-risk fix already used for ~15 functions here.

  2. "Unhandled branch in FN at ADDR to TARGET" where TARGET lands *inside*
     a small neighboring function that's either already stubbed or looks like
     the same "data misidentified as code" pattern (tiny size, in a run of
     similarly-tiny functions). This matches the existing "ovl1 data-gap call
     target" precedent exactly.

  3. "Unhandled branch in FN at ADDR to TARGET" where TARGET lands inside a
     real, non-trivial neighboring function. The function-boundary map here
     was reconstructed automatically (Ghidra) from raw code, not written by
     hand, and this specific symptom — one function jumping into the middle
     of another rather than to its start — is the classic signature of
     compiler tail-merging (two functions sharing an identical epilogue, with
     the optimizer pointing later callers straight at the shared tail instead
     of duplicating it). The fix is to split the symbol table entry in two at
     TARGET, turning "jump into someone else's body" into an ordinary jump to
     the start of a (new, smaller) function. This is a real edit to the
     symbol map (symbols/sinpunishment.syms.toml), not just a stub — every
     split is logged with the exact addresses involved so it can be spot
     checked later against a disassembly if anything downstream looks wrong.

  4. "Failed to analyze FN" (control-flow analysis gave up, no specific
     address) — usually means FN is still too large/complex in one piece
     (e.g. a coarse seed symbol covering a region Ghidra never split into
     real functions at all). Bisected at the 4-byte-aligned midpoint and
     retried; recurses until pieces are small enough to analyze or a real,
     addressable error shows up that the other tiers can act on.

  5. "Unhandled instruction: NAME" (a real, named opcode — distinct from the
     "INVALID" case, which means garbage/non-code bytes and is intentionally
     NOT auto-fixed) — an unsupported hardware/coprocessor instruction, same
     class and same fix as the cop0-register case above.

  6. "No function found for jal target: ADDR" where ADDR is outside plausible
     N64 RAM (~0x80000000-0x80800000) — a data word misidentified as a jal
     instruction, same "embedded data" pattern as tier 2/3, just surfacing as
     a bad call target instead of a bad branch target. When ADDR looks like
     it could be real RAM, this is NOT auto-fixed (could be a genuinely
     missing symbol).

Unrecognized error formats (including "Unhandled instruction: INVALID", which
usually means the bytes aren't real code) are NOT auto-fixed — the run stops
and reports it for manual review.

Usage: scripts/auto_stub_pass.py [--max-fixes N] [--dry-run]
Writes a log of every action to scripts/auto_stub_pass.log.
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
import bisect
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOML_PATH = ROOT / "sinpunishment.toml"
SYMS_PATH = ROOT / "symbols" / "sinpunishment.syms.toml"
LOG_PATH = ROOT / "scripts" / "auto_stub_pass.log"

DATA_GAP_MAX_SIZE = 0x10  # neighbors this size or smaller are "probably data"

RE_COP0 = re.compile(r"Unhandled cop0 register in (\w+): (\d+)")
RE_BRANCH = re.compile(r"Unhandled branch in (\S+) at (0x[0-9A-Fa-f]+) to (0x[0-9A-Fa-f]+)")
RE_ANALYZE_FAIL = re.compile(r"Failed to analyze (\S+)")
# "No function found for jal target: 0xADDR" — a jal (call) whose encoded
# target isn't a known function. When ADDR falls outside plausible N64 RAM
# (~0x80000000-0x80800000, the 8MB-expansion-pak ceiling), this is a data
# word misidentified as an instruction, not a real call — same "embedded
# data inside a function" pattern as the data-gap/tail-merge cases, just a
# different symptom. Confirmed non-random: the same (address, size, target)
# triple recurs identically across unrelated overlay files sharing boilerplate
# code, which random corruption would not do.
RE_BAD_JAL = re.compile(r"No function found for jal target: (0x[0-9A-Fa-f]+)")
VALID_RAM_LO = 0x80000000
VALID_RAM_HI = 0x80800000
RE_ERROR_FN = re.compile(r"Error recompiling (\S+)")
# "Unhandled instruction: bc0f" etc — unsupported opcode, distinct from the
# generic "INVALID" case (a real, named MIPS instruction N64Recomp's decoder
# just doesn't implement, same class as the cop0-register cases: hardware/
# coprocessor instructions the runtime reimplements anyway, safe to stub).
RE_UNHANDLED_INSTR_NAMED = re.compile(r"Unhandled instruction: (?!INVALID$)(\S+)")
RE_UNHANDLED_INSTR = re.compile(r"Unhandled instruction")
# N64Recomp emits many of these per run as tolerated warnings (not just the
# one hard error it stops at) -- each is the exact same situation the
# "branch" error kind handles, just not fatal to N64Recomp itself. Harvesting
# and batch-fixing all of them per run, instead of waiting to hit each one as
# a separate hard error across many separate runs, cuts the number of
# (relatively expensive, whole-ROM) N64Recomp invocations dramatically.
RE_WARN_BRANCH = re.compile(r"\[Warn\] Function (\S+) is branching outside of the function \(to (0x[0-9A-Fa-f]+)\)")

# Below this, bisecting an analysis failure isn't productive — too small to
# usefully halve, needs a human look instead.
BISECT_MIN_SIZE = 0x20


def load_symbols():
    """Returns (section_syms, name_to_section, section_bounds): overlays share
    VRAM ranges but are never loaded simultaneously, so address lookups MUST
    stay scoped to the erroring function's own section — cross-overlay lookups
    are meaningless."""
    data = tomllib.loads(SYMS_PATH.read_text())
    section_syms = {}
    section_bounds = {}
    name_to_section = {}
    for section in data.get("section", []):
        sname = section["name"]
        syms = sorted((fn["vram"], fn["size"], fn["name"]) for fn in section.get("functions", []))
        section_syms[sname] = syms
        section_bounds[sname] = (section["vram"], section["size"])
        for _, _, fname in syms:
            name_to_section[fname] = sname
    return section_syms, name_to_section, section_bounds


def find_gap(syms, section_vram, section_size, addr):
    """If addr falls in an unmapped gap within the section's own declared
    bounds (between two known functions, or between a function and the
    section edge), return (gap_start, gap_end). Otherwise None."""
    section_end = section_vram + section_size
    if not (section_vram <= addr < section_end):
        return None
    starts = [s[0] for s in syms]
    idx = bisect.bisect_right(starts, addr)
    gap_end = syms[idx][0] if idx < len(syms) else section_end
    gap_start = section_vram
    if idx > 0:
        gap_start = syms[idx - 1][0] + syms[idx - 1][1]
    return gap_start, gap_end


def section_prefix(syms):
    vram, size, name = syms[0]
    suffix = f"{vram:08X}"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return name + "_"


def insert_symbol(syms_text, section_name, new_name, vram, size):
    header_pat = re.compile(r'\[\[section\]\]\nname = "' + re.escape(section_name) + r'"\n')
    hm = header_pat.search(syms_text)
    if not hm:
        raise RuntimeError(f"couldn't find section {section_name} in {SYMS_PATH}")
    fm = re.search(r"functions = \[\n", syms_text[hm.end():])
    if not fm:
        raise RuntimeError(f"couldn't find functions array for section {section_name}")
    insert_at = hm.end() + fm.end()
    line = f'    {{ name = "{new_name}", vram = 0x{vram:08X}, size = 0x{size:X} }},\n'
    return syms_text[:insert_at] + line + syms_text[insert_at:]


def find_containing(syms, addr):
    """Return (vram, size, name) of the function containing addr within a
    single section's symbol list, or None."""
    lo, hi = 0, len(syms) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        vram, size, name = syms[mid]
        if vram <= addr:
            best = syms[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if best and best[0] <= addr < best[0] + best[1]:
        return best
    return None


def current_stubs(toml_text):
    m = re.search(r"stubs\s*=\s*\[(.*?)\n\]", toml_text, re.S)
    if not m:
        raise RuntimeError("could not find stubs = [ ... ] block in sinpunishment.toml")
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def add_stub(toml_text, name, comment):
    marker = "\nstubs = [\n"
    idx = toml_text.index(marker) + len(marker)
    line = f'    "{name}",   # {comment}\n'
    return toml_text[:idx] + line + toml_text[idx:]


def classify_branch(section_syms, name_to_section, section_bounds, from_fn, target_addr, stubbed_names):
    """Returns (action, reason, extra) where action is 'stub', 'split', 'gap', or None.
    'extra' carries the containing-function tuple (vram, size, name) for 'split',
    or (gap_start, gap_end) for 'gap'."""
    section = name_to_section.get(from_fn)
    if section is None:
        return None, f"'{from_fn}' not found in any section's symbol list", None
    syms = section_syms[section]
    fn = find_containing(syms, target_addr)
    if fn is None:
        section_vram, section_size = section_bounds[section]
        gap = find_gap(syms, section_vram, section_size, target_addr)
        if gap is not None:
            gap_start, gap_end = gap
            return "gap", (f"target lands in an unmapped gap (0x{gap_start:X}-0x{gap_end:X}, "
                            f"0x{gap_end - gap_start:X} bytes) between known functions in section {section}"), gap
        if not (VALID_RAM_LO <= target_addr < VALID_RAM_HI):
            # Same reasoning as the bad_jal tier: a branch target nowhere near
            # plausible N64 RAM is a data word misidentified as an instruction,
            # not a real branch. Stub the function containing the bad branch.
            return "stub", (f"branch target 0x{target_addr:X} is outside valid N64 RAM "
                             f"(0x{VALID_RAM_LO:X}-0x{VALID_RAM_HI:X}); embedded data word misidentified as a branch instruction"), None
        # In-range but unmapped: normally not auto-fixable (could be a real
        # missing symbol). Exception, confirmed by manual inspection of
        # ovlfile12_func_80112CC4/80112CE4 (see sinpunishment.toml): when the
        # immediately preceding function in this same section was already
        # stubbed as misidentified data, subsequent adjacent functions in the
        # same incoherent-jump run are overwhelmingly likely to be more of the
        # same data blob, not new legitimate code.
        prev_name = None
        for i, (v, s, n) in enumerate(syms):
            if n == from_fn:
                prev_name = syms[i - 1][2] if i > 0 else None
                break
        if prev_name is not None and prev_name in stubbed_names:
            return "stub", (f"branch target 0x{target_addr:X} is unmapped but in plausible RAM; auto-fixed only because "
                             f"the immediately preceding function ({prev_name}) was already confirmed misidentified data, "
                             f"and this is the same incoherent-jump pattern continuing into it"), None
        return None, f"no symbol in section {section} contains the branch target, and it's outside the section's declared bounds", None
    vram, size, name = fn
    if vram == target_addr:
        # Branch lands exactly on a function boundary; that's a normal call,
        # not the pattern we're auto-fixing (N64Recomp wouldn't have errored
        # on this in the first place in the cases we've seen, but be safe).
        return None, f"target is the start of {name}, not a mid-function landing", None
    if name in stubbed_names:
        return "stub", f"target lands inside already-stubbed {name} (0x{vram:X}+{size:#x})", None
    if size <= DATA_GAP_MAX_SIZE:
        return "stub", f"target lands inside small ({size:#x}-byte) neighbor {name}, consistent with data-gap pattern", None
    # Real, non-trivial neighbor: likely tail-merging (shared epilogue) —
    # split the symbol at the branch target instead of stubbing real code.
    return "split", f"target lands 0x{target_addr - vram:X} bytes inside {name} (0x{vram:X}, size {size:#x}) — treating as a tail-merge split point", fn


def split_symbol(syms_text, old_name, vram, split_addr, end_addr, new_name):
    pattern = re.compile(
        r'\{ name = "' + re.escape(old_name) + r'", vram = 0x[0-9A-Fa-f]+, size = 0x[0-9A-Fa-f]+ \},'
    )
    m = pattern.search(syms_text)
    if not m:
        raise RuntimeError(f"couldn't find symbol line for {old_name} in {SYMS_PATH}")
    first_size = split_addr - vram
    second_size = end_addr - split_addr
    replacement = (
        f'{{ name = "{old_name}", vram = 0x{vram:08X}, size = 0x{first_size:X} }},\n'
        f'    {{ name = "{new_name}", vram = 0x{split_addr:08X}, size = 0x{second_size:X} }},'
    )
    return syms_text[:m.start()] + replacement + syms_text[m.end():]


def derive_split_name(old_name, old_vram, split_addr):
    suffix = f"{old_vram:08X}"
    new_suffix = f"{split_addr:08X}"
    if old_name.endswith(suffix):
        return old_name[: -len(suffix)] + new_suffix
    return f"{old_name}_{new_suffix}"


RE_TAIL_CALL = re.compile(r"Tail call in (\S+) to (0x[0-9A-Fa-f]+)")
RE_STATIC_NAME = re.compile(r"^static_(\d+)_([0-9A-Fa-f]+)$")


def resolve_static_caller(output, static_name, name_to_section, section_order, _seen=None):
    """N64Recomp auto-synthesizes 'static_N_ADDR' placeholder functions for
    tail-call targets that don't match any of our declared symbols, instead
    of raising a normal catchable error at the call site. When one of these
    synthesized functions itself fails, the error is attributed to a name we
    can't stub (it's not in our config at all) or look up in our symbol map.
    The actual fix is the same as any other bad-branch case -- stub the REAL
    function that tail-called into the bad target -- we just have to trace
    back through the "Tail call in X to Y" lines to find it, since the
    synthesized name only tells us the target address, not the caller.
    Follows the chain if the caller is itself another synthesized name.

    N (in "static_N_ADDR") is N64Recomp's own section index (0=.boot,
    1=.boot_bss, 2=.main, 3=.ovlfile01, ...) matching section_order. This
    matters because every ovlfileNN section shares the same 0x800E4780 VRAM
    window, so the same target address can have multiple *different* real
    callers across different files -- only the one in the matching section
    is the actual caller for this specific synthesized instance."""
    if _seen is None:
        _seen = set()
    if static_name in _seen:
        return None  # cycle guard
    _seen.add(static_name)
    m = RE_STATIC_NAME.match(static_name)
    if not m:
        return None
    section_idx = int(m.group(1))
    if section_idx >= len(section_order):
        return None
    expected_section = section_order[section_idx]
    target_addr = f"0x{m.group(2)}"
    for caller, to_addr in RE_TAIL_CALL.findall(output):
        if to_addr.upper() != target_addr.upper():
            continue
        if RE_STATIC_NAME.match(caller):
            resolved = resolve_static_caller(output, caller, name_to_section, section_order, _seen)
            if resolved is not None:
                return resolved
            continue
        if name_to_section.get(caller) == expected_section:
            return caller
    return None


def run_recomp():
    proc = subprocess.run(
        ["./N64Recomp", "sinpunishment.toml"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_first_error(stderr):
    for line in stderr.splitlines():
        cop0 = RE_COP0.search(line)
        if cop0:
            return "cop0", line, cop0
        branch = RE_BRANCH.search(line)
        if branch:
            return "branch", line, branch
        analyze_fail = RE_ANALYZE_FAIL.search(line)
        if analyze_fail:
            return "analyze_fail", line, analyze_fail
        named_instr = RE_UNHANDLED_INSTR_NAMED.search(line)
        if named_instr:
            return "unhandled_instr", line, named_instr
        bad_jal = RE_BAD_JAL.search(line)
        if bad_jal:
            return "bad_jal", line, bad_jal
        if RE_UNHANDLED_INSTR.search(line):
            return "unknown", line, None
    return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fixes", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    log_lines = []
    fixes = 0

    while fixes < args.max_fixes:
        rc, stdout, stderr = run_recomp()

        # Batch-fix every "branching outside the function" warning from this
        # run before even looking at the (possibly unrelated) hard error --
        # same classify_branch() logic as the "branch" error kind below, just
        # applied to everything this run surfaced instead of one at a time.
        warn_pairs = []
        seen_pairs = set()
        for fn_name, to_addr in RE_WARN_BRANCH.findall(stderr):
            key = (fn_name, to_addr)
            if key not in seen_pairs:
                seen_pairs.add(key)
                warn_pairs.append(key)

        touched_this_round = set()
        for fn_name, to_addr in warn_pairs:
            if fixes >= args.max_fixes:
                break
            if fn_name in touched_this_round:
                continue
            section_syms, name_to_section, section_bounds = load_symbols()
            toml_text = TOML_PATH.read_text()
            stubbed_names = current_stubs(toml_text)
            target = int(to_addr, 16)
            verdict, reason, extra = classify_branch(section_syms, name_to_section, section_bounds, fn_name, target, stubbed_names)
            if verdict is None:
                continue  # not confidently fixable from a warning alone; leave for the hard-error path or manual review
            if verdict == "stub":
                comment = f"auto(warn-batch): branches to {to_addr} ({reason})"
                action = f"AUTO-STUB {fn_name}: {comment}"
                if not args.dry_run:
                    toml_text = add_stub(toml_text, fn_name, comment)
                    TOML_PATH.write_text(toml_text)
            elif verdict == "gap":
                gap_start, gap_end = extra
                section = name_to_section[fn_name]
                prefix = section_prefix(section_syms[section])
                new_name = f"{prefix}{gap_start:08X}"
                action = f"AUTO-SEED {new_name} (0x{gap_start:X}, 0x{gap_end - gap_start:X}) in section {section}: {reason}"
                if not args.dry_run:
                    syms_text = SYMS_PATH.read_text()
                    syms_text = insert_symbol(syms_text, section, new_name, gap_start, gap_end - gap_start)
                    SYMS_PATH.write_text(syms_text)
            else:  # split
                vram, size, name = extra
                end_addr = vram + size
                new_name = derive_split_name(name, vram, target)
                action = (f"AUTO-SPLIT {name} (0x{vram:X}+{size:#x}) at {to_addr}: "
                          f"-> {name} (0x{vram:X}, 0x{target - vram:X}) + {new_name} (0x{target:X}, 0x{end_addr - target:X}) — {reason}")
                if not args.dry_run:
                    syms_text = SYMS_PATH.read_text()
                    syms_text = split_symbol(syms_text, name, vram, target, end_addr, new_name)
                    SYMS_PATH.write_text(syms_text)
            print(f"[warn-batch] {action}")
            log_lines.append(action)
            touched_this_round.add(fn_name)
            fixes += 1

        if rc == 0:
            msg = f"SUCCESS after {fixes} auto-fix(es): N64Recomp completed with no errors."
            print(msg)
            log_lines.append(msg)
            break

        if touched_this_round:
            # Made progress from the warning batch this round -- re-run
            # N64Recomp fresh rather than also acting on the (possibly now
            # stale) hard error below, since fixing a warning can easily
            # resolve what would have been the next hard error too.
            continue

        # Reload fresh: nothing changed above, but keep this explicit in case
        # a future edit reorders things.
        section_syms, name_to_section, section_bounds = load_symbols()
        kind, line, match = parse_first_error(stderr)
        if kind is None:
            msg = f"STOP: recompile failed but no recognized error pattern found.\n--- stderr tail ---\n{stderr[-2000:]}"
            print(msg)
            log_lines.append(msg)
            break

        err_fn_match = RE_ERROR_FN.search(stderr)
        err_fn = err_fn_match.group(1) if err_fn_match else None

        toml_text = TOML_PATH.read_text()
        stubbed_names = current_stubs(toml_text)

        if kind == "cop0":
            instr, reg = match.group(1), match.group(2)
            if err_fn is None:
                msg = f"STOP: cop0 error but couldn't find the offending function name.\nLine: {line}"
                print(msg); log_lines.append(msg); break
            comment = f"auto: unhandled cop0 register in {instr} ({reg}); unsupported OS-level instruction, same class as existing cop0/TLB stubs"
            action = f"AUTO-STUB {err_fn}: {comment}"
        elif kind == "unhandled_instr":
            instr = match.group(1)
            if err_fn is None:
                msg = f"STOP: unhandled instruction '{instr}' but couldn't find the offending function name.\nLine: {line}"
                print(msg); log_lines.append(msg); break
            comment = f"auto: unhandled instruction '{instr}'; unsupported opcode (hardware/coprocessor), same class as existing cop0/TLB stubs"
            action = f"AUTO-STUB {err_fn}: {comment}"
        elif kind == "bad_jal":
            target = int(match.group(1), 16)
            if err_fn is None:
                msg = f"STOP: bad jal target 0x{target:X} but couldn't find the offending function name.\nLine: {line}"
                print(msg); log_lines.append(msg); break
            if not (VALID_RAM_LO <= target < VALID_RAM_HI):
                comment = f"auto: jal target 0x{target:X} is outside valid N64 RAM (0x{VALID_RAM_LO:X}-0x{VALID_RAM_HI:X}); embedded data word misidentified as a jal instruction"
                action = f"AUTO-STUB {err_fn}: {comment}"
            else:
                msg = (f"STOP: jal target 0x{target:X} in {err_fn} is within plausible RAM but no function was found there — "
                       f"could be a genuinely missing symbol, not auto-fixable. Needs manual review.")
                print(msg); log_lines.append(msg); break
        elif kind == "branch":
            fn_name, from_addr, to_addr = match.group(1), match.group(2), match.group(3)
            target = int(to_addr, 16)
            if RE_STATIC_NAME.match(fn_name):
                # N64Recomp-synthesized placeholder, not one of our symbols --
                # trace back to the real function that tail-called into it and
                # stub that instead (see resolve_static_caller docstring).
                # "Tail call in X to Y" lines are on stdout, not stderr.
                section_order = list(section_syms.keys())
                real_caller = resolve_static_caller(stdout + stderr, fn_name, name_to_section, section_order)
                if real_caller is None:
                    msg = (f"STOP: unhandled branch in synthesized '{fn_name}' at {from_addr} to {to_addr}, and couldn't "
                           f"trace back to a real caller via 'Tail call in X to Y' lines. Needs manual review.")
                    print(msg); log_lines.append(msg); break
                comment = f"auto: tail-calls into N64Recomp-synthesized '{fn_name}' (unresolvable branch inside it at {to_addr}); real symbol-boundary issue, not addressable via this synthesized name"
                action = f"AUTO-STUB {real_caller}: {comment}"
                print(action); log_lines.append(action)
                if not args.dry_run:
                    toml_text = add_stub(toml_text, real_caller, comment)
                    TOML_PATH.write_text(toml_text)
                fixes += 1
                continue
            verdict, reason, extra = classify_branch(section_syms, name_to_section, section_bounds, fn_name, target, stubbed_names)
            if verdict is None:
                msg = (f"STOP: unhandled branch in {fn_name} at {from_addr} to {to_addr} — "
                       f"not auto-fixable ({reason}). Needs manual review.")
                print(msg); log_lines.append(msg); break
            if verdict == "stub":
                comment = f"auto: branches to {to_addr} ({reason})"
                action = f"AUTO-STUB {fn_name}: {comment}"
                if not args.dry_run:
                    toml_text = add_stub(toml_text, fn_name, comment)
                    TOML_PATH.write_text(toml_text)
            elif verdict == "gap":
                gap_start, gap_end = extra
                section = name_to_section[fn_name]
                prefix = section_prefix(section_syms[section])
                new_name = f"{prefix}{gap_start:08X}"
                action = (f"AUTO-SEED {new_name} (0x{gap_start:X}, 0x{gap_end - gap_start:X}) in section {section}: {reason}")
                if not args.dry_run:
                    syms_text = SYMS_PATH.read_text()
                    syms_text = insert_symbol(syms_text, section, new_name, gap_start, gap_end - gap_start)
                    SYMS_PATH.write_text(syms_text)
            else:  # split
                vram, size, name = extra
                end_addr = vram + size
                new_name = derive_split_name(name, vram, target)
                action = (f"AUTO-SPLIT {name} (0x{vram:X}+{size:#x}) at {to_addr}: "
                          f"-> {name} (0x{vram:X}, 0x{target - vram:X}) + {new_name} (0x{target:X}, 0x{end_addr - target:X}) — {reason}")
                if not args.dry_run:
                    syms_text = SYMS_PATH.read_text()
                    syms_text = split_symbol(syms_text, name, vram, target, end_addr, new_name)
                    SYMS_PATH.write_text(syms_text)
            print(action)
            log_lines.append(action)
            fixes += 1
            continue
        elif kind == "analyze_fail":
            fail_fn = match.group(1)
            section = name_to_section.get(fail_fn)
            if section is None:
                msg = f"STOP: analysis failed on '{fail_fn}' but it's not in any section's symbol list (bug?)."
                print(msg); log_lines.append(msg); break
            fn = next((s for s in section_syms[section] if s[2] == fail_fn), None)
            if fn is None:
                msg = f"STOP: couldn't find '{fail_fn}' in section {section}'s symbol list."
                print(msg); log_lines.append(msg); break
            vram, size, name = fn
            if size <= BISECT_MIN_SIZE:
                msg = (f"STOP: analysis failed on {name} (0x{vram:X}, size {size:#x}) — "
                       f"too small to usefully bisect further. Needs manual review.")
                print(msg); log_lines.append(msg); break
            mid = vram + ((size // 2) // 4) * 4  # 4-byte aligned midpoint
            end_addr = vram + size
            new_name = derive_split_name(name, vram, mid)
            action = (f"AUTO-BISECT {name} (0x{vram:X}+{size:#x}) — analysis failed, no specific address given: "
                      f"-> {name} (0x{vram:X}, 0x{mid - vram:X}) + {new_name} (0x{mid:X}, 0x{end_addr - mid:X})")
            if not args.dry_run:
                syms_text = SYMS_PATH.read_text()
                syms_text = split_symbol(syms_text, name, vram, mid, end_addr, new_name)
                SYMS_PATH.write_text(syms_text)
            print(action)
            log_lines.append(action)
            fixes += 1
            continue
        else:
            msg = f"STOP: unrecognized error type.\nLine: {line}"
            print(msg); log_lines.append(msg); break

        print(action)
        log_lines.append(action)
        if not args.dry_run:
            toml_text = add_stub(toml_text, err_fn, comment)
            TOML_PATH.write_text(toml_text)
        fixes += 1
    else:
        msg = f"STOP: hit --max-fixes cap ({args.max_fixes}) without a clean recompile. Re-run to continue."
        print(msg)
        log_lines.append(msg)

    LOG_PATH.write_text("\n".join(log_lines) + "\n")
    print(f"\n{fixes} auto-fix(es) this run. Log: {LOG_PATH}")


if __name__ == "__main__":
    main()
