#!/usr/bin/env bash
# Sets a live hardware watchpoint on a MIPS/N64 RAM address and reports the
# backtrace of whatever writes it first. Automates the pattern used
# throughout this project's boot-debugging sessions: break at
# recomp_entrypoint (the very first function that runs, so it always hits
# exactly once) to read the rdram base pointer out of $rdi (recompiled
# functions are (uint8_t* rdram, recomp_context* ctx), and rdram is the
# first argument -- SysV o32 puts that in $rdi at function entry, valid even
# without debug info), translate the target MIPS address the same way
# MEM_W/MEM_B do (rdram_base + (addr - 0x80000000)), then watch it.
#
# Usage: scripts/gdb_watch.sh <mips_addr_hex> [seconds_to_run]
#   scripts/gdb_watch.sh 0x800E4FFC
#   scripts/gdb_watch.sh 0x800E4FFC 30
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
    echo "Usage: $0 <mips_addr_hex> [seconds_to_run]" >&2
    exit 1
fi

ADDR="$1"
TIMEOUT_SECS="${2:-20}"
GDB_SCRIPT="$(mktemp /tmp/gdb_watch_XXXXXX.gdb)"
LOG_FILE="$(mktemp /tmp/gdb_watch_XXXXXX.log)"

cat > "$GDB_SCRIPT" << EOF
set pagination off
break recomp_entrypoint
run
set \$rdram_base = \$rdi
delete 1
set \$watch_addr = \$rdram_base + (${ADDR} - 0x80000000)
printf "watching MIPS ${ADDR} at host address %p\n", \$watch_addr
watch *(unsigned int*)\$watch_addr
continue
bt 8
thread apply all bt 4
quit
EOF

echo "Running under gdb (timeout ${TIMEOUT_SECS}s)..."
SP_AUTOSTART=1 timeout "$TIMEOUT_SECS" gdb -batch -x "$GDB_SCRIPT" --args ./build/SinPunishmentRecompiled > "$LOG_FILE" 2>&1 || true

set +o pipefail  # head truncating a longer pipeline below is expected, not a failure

echo "=== watch address / hit summary ==="
grep -E "watching MIPS|hit Hardware watchpoint|Old value|New value|received signal" "$LOG_FILE" || echo "(no watchpoint hit -- see full log)"
echo ""
echo "=== backtrace at hit (thread that wrote it) ==="
# The backtrace we want starts at "New value = ..." (right after the hit is
# reported) and runs through the numbered #0/#1/... frames that follow.
awk '/^New value = /{found=1; next} found' "$LOG_FILE" | sed -n '/^#[0-9]/,/^$/p' | head -20
echo ""
echo "Full log: $LOG_FILE"
