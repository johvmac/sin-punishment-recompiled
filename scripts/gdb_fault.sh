#!/usr/bin/env bash
# Catch the SIGSEGV and print the game-side context at the fault.
#
# Usage: scripts/gdb_fault.sh [deadline_s] [logfile] [binary]
#   scripts/gdb_fault.sh 200 /tmp/fault.log
#
# WHY THIS EXISTS
# ---------------
# A99 faults at `lw $s3, 0x0($v0)` (vram 0x800337C4) with $v0 = 0x02000000
# (A102). To find WHO wrote that word we first need the ADDRESS it was loaded
# from -- i.e. $s0 in the game's register file -- and deriving it statically
# needs `k`, which depends on which of three writers ran (A114/A118).
# Reading it off the fault is one run and settles it with no derivation.
#
# `run_game.sh` reports "(core dumped)" on the crash, but `ulimit -c` is 0 and
# apport owns core_pattern on this machine, so NO core file is produced and
# there is nothing to inspect offline. That message is bash reporting the
# signal disposition, not evidence a file exists. Hence a live gdb run.
#
# Launch mechanics are copied from gdb_watch.sh and are not incidental:
#  * the game is gdb's OWN CHILD, never attached to -- ptrace_scope blocks
#    attaching on this machine, launching as a child is unaffected;
#  * a watchdog thread inside gdb force-quits at the deadline. Never remove it.
set -uo pipefail

DEADLINE="${1:-200}"
LOG_FILE="${2:-/tmp/gdb_fault.log}"
BIN="${3:-build/SinPunishmentRecompiled}"

case "${1:-}" in
    --help|-h) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

[ -x "$BIN" ] || { echo "no binary at $BIN" >&2; exit 1; }

GDB_SCRIPT="$(mktemp /tmp/gdb_fault_XXXXXX.gdb)"

cat > "$GDB_SCRIPT" <<'EOF'
set pagination off
set confirm off
set print elements 0

python
import threading, gdb, os, signal
def watchdog():
    os._exit(3)
t = threading.Timer(__DEADLINE__, watchdog)
t.daemon = True
t.start()
end

# Let the game run; stop only when it actually faults.
run

echo \n===== SIGNAL / FRAME =====\n
info signal SIGSEGV
frame
bt 12

echo \n===== GAME REGISTER FILE AT THE FAULT =====\n
# The recompiled functions carry a `ctx` (recomp_context*). $s0 is r16 and
# $v0 is r2 -- the load that faults is `lw $s3, 0x0($v0)` and $v0 came from
# `lw $v0, 0x0($s0)`, so r16 is the ADDRESS we are after and r2 is the value.
python
import gdb
def show(expr):
    try:
        print("  %-28s = %s" % (expr, gdb.parse_and_eval(expr)))
    except Exception as e:
        print("  %-28s : %s" % (expr, e))
for f in ("r2","r16","r18","r20","r29","r31"):
    show("(unsigned long long)ctx->%s" % f)
try:
    base = int(gdb.parse_and_eval("*(unsigned long long *)&g_rdram_base"))
    r16  = int(gdb.parse_and_eval("(unsigned long long)ctx->r16")) & 0xFFFFFFFF
    r2   = int(gdb.parse_and_eval("(unsigned long long)ctx->r2"))  & 0xFFFFFFFF
    print("\n  rdram base   = 0x%x" % base)
    print("  $s0 (r16) vram = 0x%08X   <-- ADDRESS the faulting value was loaded FROM" % r16)
    print("  $v0 (r2)  vram = 0x%08X   <-- the garbage pointer that was dereferenced" % r2)
    if 0x80000000 <= r16 < 0x80800000:
        host = base + (r16 - 0x80000000)
        print("  word currently at $s0 = 0x%08X" % int(gdb.parse_and_eval("*(unsigned int *)%d" % host)))
except Exception as e:
    print("  derivation failed: %s" % e)
end

echo \n===== GAME STACK: $s0 PER RECURSION LEVEL (A124) =====\n
# The recompiled ctx holds ONE register file per thread, so ctx->r16 is only the
# INNERMOST frame's $s0 -- which is why A112/A122 confused an outer-call trace
# with the faulting one. The per-level values are on the GAME stack: the walker
# opens `addiu $sp,$sp,-0x50` and immediately does `sw $s0,0x10($sp)`, so the
# word at sp + k*0x50 + 0x10 is the $s0 belonging to the frame ABOVE level k.
# Walking that recovers the whole descent from a single fault, with no probe and
# no rebuild.
#
# DO NOT sanity-check this walk by expecting the saved $ra at sp+0x28 to be a
# code address. The store IS emitted, but $ra carries no meaning in recompiled
# output -- returns are real C returns -- so that check fails on a CORRECT walk
# (A125). The control that works is self-consistency: successive levels should
# differ by the stride the static read predicts. And the walk is only valid
# across the walker's OWN frames; func_80033A40 opens 0x18, not 0x50.
python
import gdb
def u32(host):
    return int(gdb.parse_and_eval("*(unsigned int *)%d" % host)) & 0xFFFFFFFF
try:
    base = int(gdb.parse_and_eval("*(unsigned long long *)&g_rdram_base"))
    sp   = int(gdb.parse_and_eval("(unsigned long long)ctx->r29")) & 0xFFFFFFFF
    live = int(gdb.parse_and_eval("(unsigned long long)ctx->r16")) & 0xFFFFFFFF
    FRAME, S0_OFF, RA_OFF = 0x50, 0x10, 0x28
    print("  live $s0 (innermost)      = 0x%08X" % live)
    print("  %-4s %-12s %-12s %-12s" % ("lvl", "frame_sp", "saved_$s0", "saved_$ra"))
    prev = live
    for k in range(8):
        fsp = (sp + k * FRAME) & 0xFFFFFFFF
        if not (0x80000000 <= fsp < 0x80800000):
            print("  level %d: sp 0x%08X outside RDRAM -- stopping" % (k, fsp)); break
        s0 = u32(base + (fsp + S0_OFF - 0x80000000))
        ra = u32(base + (fsp + RA_OFF - 0x80000000))
        delta = ""
        if 0x80000000 <= s0 < 0x80800000 and 0x80000000 <= prev < 0x80800000:
            d = (prev - s0) & 0xFFFFFFFF
            if d < 0x10000:
                delta = "   (inner is +0x%X = idx %d at stride 4)" % (d, d // 4)
        print("  %-4d 0x%08X   0x%08X   0x%08X%s" % (k, fsp, s0, ra, delta))
        prev = s0
    print("\n  A124's question: are these successive elements of ONE array, or does")
    print("  the chain walk out of it? Compare the span against the array it starts in.")
except Exception as e:
    print("  stack walk failed: %s" % e)
end

echo \n===== CORE FILE =====\n
# gdb writes the core ITSELF, on demand, at the moment of the fault.
#
# This is deliberately NOT the system core-dump path. That would need
# `ulimit -c unlimited` plus taking core_pattern away from apport (sudo), and it
# would then dump EVERY crash anywhere on the machine to a fixed location. This
# writes one core, only when we are already debugging, exactly where we say --
# no sudo, no apport, and nothing lands on the root filesystem.
#
# Worth having because a core is re-inspectable: on 2026-08-19 gdb_fault.sh was
# run twice against the same crash purely because the first pass used the
# release binary and `ctx` would not resolve (A122). With a core the second pass
# costs nothing instead of a 158-second run.
python
import gdb, os
path = os.environ.get("SNP_CORE", "")
if path:
    try:
        gdb.execute("generate-core-file %s" % path)
        print("  wrote %s (%.0f MB)" % (path, os.path.getsize(path) / 1e6))
        print("  re-inspect with:  gdb build-debug/SinPunishmentRecompiled %s" % path)
    except Exception as e:
        print("  core generation FAILED: %s" % e)
else:
    print("  skipped. SNP_CORE=<path> writes one, but MEASURE FIRST: a core of this\n"
          "  process is ~11.8 GB, not tens of MB -- the recompiler maps a very large\n"
          "  writable region and gdb dumps all of it (T63). Re-running this script\n"
          "  costs 158s and is almost always the better trade.")
end

echo \n===== FAULTING INSTRUCTION =====\n
# `disassemble`, NOT `x/i $pc-N`. x/i decodes from an arbitrary byte offset and
# on x86 that lands mid-instruction, printing confident nonsense -- A102 was
# misled by exactly this once, and the first version of THIS script repeated it
# (`rorb $0x84,(%rdi)` in the middle of a load sequence). `disassemble` decodes
# from the function's own start, so the boundaries are right.
# `disassemble` with NO range: it decodes the WHOLE current function from its
# own entry point, so every boundary is right. A range starting at $pc-N is
# still an arbitrary offset and still resyncs through garbage first -- the
# 2026-08-19 fix to this line swapped x/i for a RANGED disassemble and got
# `add %al,(%rax)` for its first three lines anyway. Verbose beats wrong.
disassemble
echo \n===== HOST REGISTERS (for when ctx is unavailable) =====\n
info registers rip rax rbx rcx rdx rsi rdi rbp
quit
EOF

sed -i -e "s|__DEADLINE__|${DEADLINE}|g" "$GDB_SCRIPT"

# shellcheck source=scripts/display_isolate.sh
. "$(dirname "$0")/display_isolate.sh"
snp_isolate_display gdb_fault
trap 'rm -f "$GDB_SCRIPT"; snp_display_cleanup' EXIT INT TERM

echo "launching $BIN under gdb; hard deadline ${DEADLINE}s..."
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 \
    setsid stdbuf -oL -eL gdb -batch -x "$GDB_SCRIPT" --args "$BIN" > "$LOG_FILE" 2>&1

echo "gdb exited; log: $LOG_FILE ($(wc -l < "$LOG_FILE") lines)"
