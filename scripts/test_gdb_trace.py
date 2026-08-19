#!/usr/bin/env python3
"""Self-check for gdb_trace.sh -- run as `scripts/gdb_trace.sh --self-check`.

WHY THIS EXISTS
gdb_trace.sh gained a SECOND trace location (2026-08-19, roll #86) so that two
sites can be compared WITHIN one run instead of across runs -- the thing that
let A99's contradiction survive six rolls (A157).

That change introduces a failure mode with no symptom. gdb numbers breakpoints
in creation order, so the second site's are 3 and 4. If `ignore` or `commands`
is aimed at the wrong number, NOTHING complains:

  * `ignore` on a conditional breakpoint -> it stops the inferior on every hit
    instead of counting silently. At a line reached ~79,000 times per run that is
    a run that never finishes. (Not an A138 perturbation argument -- T72 withdrew
    that causal claim; the deadline argument needs no help.)
  * `commands` on the reach counter -> the printf never fires, the log is empty,
    and it reads exactly like "the condition was never true".

Both cost a full 280 s deadline to discover, and both produce evidence that
looks fine. So the numbering is PARSED out of the generated script and checked
against the order the `break` statements actually appear in -- not asserted
against the literals 3 and 4, which would just restate the bug if it were there.

T71 gate 2: every control below was verified to FAIL when the thing it checks
is broken, not merely to pass when it works.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE = ROOT / "scripts" / "gdb_trace.sh"

LOC1 = "funcs_4.c:228"
COND1 = "((ctx->r6 & 0xFFFFFFFF) >= 0x8013A000 && (ctx->r6 & 0xFFFFFFFF) <= 0x8013D000)"
ARGS1 = "ctx->r4, ctx->r5, ctx->r6, ctx->r29"
LOC2 = "funcs_4.c:661"
COND2 = "((ctx->r16 & 0xFFFFFFFF) >= 0x8013A000 && (ctx->r16 & 0xFFFFFFFF) <= 0x8013D000)"
ARGS2 = "ctx->r16, ctx->r3, ctx->r6, ctx->r29"


def gen(extra_env=None, args=None):
    """Generate a gdb script via the real dry-run path. Returns (rc, stdout)."""
    env = dict(os.environ, SNP_TRACE_DRYRUN="1")
    env.pop("SNP_TRACE_LOC2", None)
    env.pop("SNP_TRACE_COND2", None)
    env.pop("SNP_TRACE_ARGS2", None)
    env.update(extra_env or {})
    p = subprocess.run([str(TRACE)] + (args or [LOC1, COND1, ARGS1, "150", "280"]),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


def breakpoint_map(script):
    """Number the `break` statements in creation order, as gdb does.

    Returns {number: 'reach'|'cond'}. gdb assigns 1, 2, 3... in the order the
    break commands are executed, which for a batch script is source order.
    """
    bps, n = {}, 0
    for line in script.split("\n"):
        s = line.strip()
        if not s.startswith("break "):
            continue
        n += 1
        bps[n] = "cond" if re.search(r"\bif\b", s) else "reach"
    return bps


def check_numbering(script, want_breaks):
    """`ignore` must target reach breakpoints, `commands` must target conditional
    ones. This is the control that cannot be satisfied by restating the code."""
    problems = []
    bps = breakpoint_map(script)
    if len(bps) != want_breaks:
        problems.append(f"expected {want_breaks} break statements, found {len(bps)}")
    for m in re.finditer(r"^ignore (\d+) ", script, re.M):
        num = int(m.group(1))
        if bps.get(num) != "reach":
            problems.append(f"`ignore {num}` targets a {bps.get(num, 'nonexistent')} "
                            f"breakpoint -- it must target the reach counter, or the "
                            f"run stops on every hit and never finishes")
    for m in re.finditer(r"^commands (\d+)$", script, re.M):
        num = int(m.group(1))
        if bps.get(num) != "cond":
            problems.append(f"`commands {num}` targets a {bps.get(num, 'nonexistent')} "
                            f"breakpoint -- the printf would never fire and the log "
                            f"would read as 'condition never true'")
    return problems


def main():
    checks = []

    def add(name, ok, detail):
        checks.append((name, ok, detail))

    # ---- single location: the pre-existing behaviour must not regress -------
    rc, out = gen()
    add("single-location dry run exits 0", rc == 0, f"rc={rc}")
    add("single-location numbering (2 breaks, ignore->reach, commands->cond)",
        not check_numbering(out, 2), "; ".join(check_numbering(out, 2)) or "clean")
    add("single-location emits no HIT2 and no empty FIELDS2 line",
        "HIT2" not in out and "FIELDS (in HIT2" not in out,
        "clean" if "HIT2" not in out else "leaked a second-site artifact")
    add("no unsubstituted placeholder survives",
        not re.search(r"__[A-Z_]+__", out),
        sorted(set(re.findall(r"__[A-Z_]+__", out))) or "clean")

    # ---- two locations ------------------------------------------------------
    env2 = {"SNP_TRACE_LOC2": LOC2, "SNP_TRACE_COND2": COND2, "SNP_TRACE_ARGS2": ARGS2}
    rc2, out2 = gen(env2)
    add("two-location dry run exits 0", rc2 == 0, f"rc={rc2}")
    probs = check_numbering(out2, 4)
    add("two-location numbering (4 breaks, ignore->reach, commands->cond)",
        not probs, "; ".join(probs) or "bp1/3 reach, bp2/4 conditional")
    add("both locations present in the generated script",
        out2.count(LOC1) >= 2 and out2.count(LOC2) >= 2,
        f"{LOC1}x{out2.count(LOC1)}, {LOC2}x{out2.count(LOC2)}")
    add("both conditions substituted LITERALLY (the `&` trap)",
        COND1 in out2 and COND2 in out2,
        "both intact" if COND1 in out2 and COND2 in out2 else "a condition was mangled")
    add("hits are distinguishable (HIT1 and HIT2 both emitted)",
        "HIT1 %08X" in out2 and "HIT2 %08X" in out2,
        "distinct prefixes")
    add("no unsubstituted placeholder in two-location mode",
        not re.search(r"__[A-Z_]+__", out2),
        sorted(set(re.findall(r"__[A-Z_]+__", out2))) or "clean")

    # ---- REFUSALS: controls that must fire ---------------------------------
    # A partial second-site set would silently produce a ONE-site log that reads
    # exactly like the two-site run you asked for. That is the failure the whole
    # feature exists to avoid, so it must refuse rather than proceed.
    rc3, _ = gen({"SNP_TRACE_LOC2": LOC2})
    add("refuses a PARTIAL second-site set (LOC2 only)", rc3 == 2, f"rc={rc3}, want 2")
    rc4, _ = gen({"SNP_TRACE_LOC2": LOC2, "SNP_TRACE_COND2": COND2})
    add("refuses a PARTIAL second-site set (LOC2+COND2)", rc4 == 2, f"rc={rc4}, want 2")
    rc5, _ = gen({**env2, "SNP_TRACE_ARGS2": "ctx->r16, ctx->r3, ctx->r6"})
    add("refuses 3 printf args for the second site", rc5 == 2, f"rc={rc5}, want 2")
    rc6, _ = gen(args=[LOC1, COND1, "ctx->r4, ctx->r5, ctx->r6", "150", "280"])
    add("refuses 3 printf args for the first site", rc6 == 2, f"rc={rc6}, want 2")

    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:58} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
