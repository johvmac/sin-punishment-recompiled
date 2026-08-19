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
trap 'rm -f "$GDB_SCRIPT"' EXIT

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

echo \n===== FAULTING INSTRUCTION =====\n
# `disassemble`, NOT `x/i $pc-N`. x/i decodes from an arbitrary byte offset and
# on x86 that lands mid-instruction, printing confident nonsense -- A102 was
# misled by exactly this once, and the first version of THIS script repeated it
# (`rorb $0x84,(%rdi)` in the middle of a load sequence). `disassemble` decodes
# from the function's own start, so the boundaries are right.
disassemble $pc-32,+48
echo \n===== HOST REGISTERS (for when ctx is unavailable) =====\n
info registers rip rax rbx rcx rdx rsi rdi rbp
quit
EOF

sed -i -e "s|__DEADLINE__|${DEADLINE}|g" "$GDB_SCRIPT"

echo "launching $BIN under gdb; hard deadline ${DEADLINE}s..."
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 \
    setsid stdbuf -oL -eL gdb -batch -x "$GDB_SCRIPT" --args "$BIN" > "$LOG_FILE" 2>&1

echo "gdb exited; log: $LOG_FILE ($(wc -l < "$LOG_FILE") lines)"
