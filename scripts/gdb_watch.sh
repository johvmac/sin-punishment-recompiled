#!/usr/bin/env bash
# Catch the code that WRITES a given game (vram) address, via a hardware
# watchpoint, and print the backtrace of the writer.
#
# Usage: scripts/gdb_watch.sh <vram_addr> [arm_after_s] [deadline_s] [log] [bin]
#   scripts/gdb_watch.sh 0x8007AF0C 20 70 /tmp/watch.log
#     (arm at 20s, give up and quit at 70s)
#
# Why a watchpoint rather than more probes: on 2026-08-17 the attract-mode
# graphics stall was traced to the callback table at 0x8007AF0C being
# overwritten with float data at exactly the frame rendering stops. Counters can
# show WHEN a word changes; only a watchpoint shows WHO wrote it.
#
# Mechanics carried over from gdb_threads.sh -- do not "simplify" these away:
#
# * The game is launched as gdb's OWN CHILD, not attached to. Attaching hits
#   ptrace_scope on this machine; launching as a child does not.
# * The arming pause is posted from INSIDE gdb by a real OS thread. External
#   `kill -INT` is either fatal to gdb or silently swallowed when gdb has no
#   controlling tty, which is the case here.
# * arm_after_seconds must land BEFORE the write you are hunting. gdb does NOT
#   slow a freely-running program -- the playbook's "gdb slows execution 10-20x"
#   applies to SOFTWARE watchpoints and single-stepping, not to `run`. Confirmed
#   2026-08-17: the user observed normal speed under gdb. An arming delay chosen
#   as if the game were 10x slower lands long after the event and the watchpoint
#   never fires. x86 hardware watchpoints (4 bytes, as used here) also run at
#   full speed once armed.
#
# * There is a HARD DEADLINE. `continue` after arming blocks forever if the
#   watchpoint never fires (wrong address, write already past, watchpoint failed
#   to arm), leaving the game window open on the user's screen indefinitely --
#   which is exactly what happened twice on 2026-08-17. A second timer thread
#   force-quits gdb at deadline_seconds no matter what. Never remove it.
#
# The watchpoint address is computed as (rdram + (vram - 0x80000000)); rdram is
# read out of the running process, since it is mmap'd at a fresh address each
# run. Word access is native (only BYTE access is XOR-3 swapped), so watching
# the word directly is correct.
set -uo pipefail

# --- help (T37) ------------------------------------------------------------
# Prints this script's own header block. Added after `route.py --help` was
# silently ignored and fell through to a state-mutating default.
case "${1:-}" in
    -h|--help)
        sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'
        exit 0 ;;
esac
cd "$(dirname "$0")/.." || exit 1

VRAM="${1:?usage: gdb_watch.sh <vram_addr> [arm_after_seconds] [logfile] [binary]}"
ARM_AFTER="${2:-20}"
DEADLINE="${3:-70}"
LOG_FILE="${4:-/tmp/gdb_watch.log}"
BIN="${5:-./build/SinPunishmentRecompiled}"
# Optional gdb condition expression, e.g. '$_val > 0x80070000'. Use it to skip
# the normal traffic on a hot word and stop only on the anomalous write.
WATCH_COND="${6:-}"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: $BIN not found or not executable" >&2
    exit 1
fi

GDB_SCRIPT="$(mktemp /tmp/gdb_watch_XXXXXX.gdb)"

# QUOTED delimiter: with an unquoted EOF the shell expands the body, and the
# backticks inside the COMMENTS below run as commands -- `rdram` and `bt 20`
# both executed and vanished from the generated script ("bt: command not
# found"). Harmless only by luck. Values are substituted by sed afterwards, via
# __NAME__ placeholders that nothing can expand by accident. Same bug and same
# fix as scripts/ares_watch.sh.
cat > "$GDB_SCRIPT" << 'EOF'
set pagination off
set confirm off

python
import threading, gdb
def arm():
    import time
    time.sleep(__ARM_AFTER__)
    gdb.post_event(lambda: gdb.execute("interrupt"))
def deadline():
    import time, os, signal
    time.sleep(__DEADLINE__)
    # Hard stop. gdb.execute("quit") from a thread can itself block if the
    # inferior is running, so kill the process group outright.
    os.killpg(os.getpgid(0), signal.SIGKILL)
threading.Thread(target=arm, daemon=True).start()
threading.Thread(target=deadline, daemon=True).start()
end

run

echo \n===== ARMING WATCHPOINT =====\n
python
import gdb
base = None
try:
    # g_rdram_base is exported by ultramodern's init_events precisely for this.
    # Two failure modes already hit here, both from the Release build having no
    # DWARF: reading `rdram` out of a stack frame fails ("could not find rdram
    # in any frame") because the parameter lives in a register, and reading the
    # global by name fails ("has unknown type") because only the ELF symbol
    # table entry survives. Taking its address and casting explicitly works
    # with minimal symbols alone.
    base = int(gdb.parse_and_eval("*(unsigned long long *)&g_rdram_base"))
except gdb.error as e:
    print("FAILED: cannot read g_rdram_base (%s)" % e)
if not base:
    print("FAILED: g_rdram_base is null -- armed before init_events ran?")
else:
    vram = int(__VRAM__)
    addr = base + (vram - 0x80000000)
    cur = int(gdb.parse_and_eval("*(unsigned int*)0x%x" % addr))
    print("rdram=0x%x vram=0x%x -> host 0x%x" % (base, vram, addr))
    print("current value = 0x%08x" % cur)
    cond = """__WATCH_COND__"""
    cmd = "watch *(unsigned int *) 0x%x" % addr
    if cond.strip():
        # gdb evaluates the condition on each hardware trigger; the watched
        # word's new value is readable by dereferencing the same address.
        cmd += " if (*(unsigned int *) 0x%x) %s" % (addr, cond)
    print("watch command: " + cmd)
    gdb.execute(cmd)
end

echo \n===== CONTINUING UNTIL WRITE =====\n
continue

echo \n===== WRITER BACKTRACE (full depth) =====\n
# NOT `bt 20`. The first use of this script truncated at 20 frames and the
# recursion under investigation turned out to be far deeper than that -- the
# depth IS the finding. Print everything and summarise afterwards.
#
# NOT `bt -1` EITHER. That was the "unlimited" fix and it is the opposite:
# in gdb a NEGATIVE count prints the OUTERMOST n frames, so `bt -1` printed
# exactly one frame -- clone3 -- on every run since. Found 2026-08-19 when the
# writer of 0x8013C278 was caught and the backtrace contained nothing but the
# thread entry point. A bare `bt` prints all frames, which is what was meant.
bt
echo \n===== FAULTING INSTRUCTION =====\n
# Which register did the store use? Without debug info we cannot name ctx
# fields, but the instruction itself names its base register, which settles
# "wrote via the game's \$sp" vs "wrote via an explicit destination pointer".
# `disassemble` with NO range: it decodes the WHOLE current function from its
# own entry point, so every boundary is right. A range starting at $pc-N is
# still an arbitrary offset and still resyncs through garbage first -- the
# 2026-08-19 fix to this line swapped x/i for a RANGED disassemble and got
# `add %al,(%rax)` for its first three lines anyway. Verbose beats wrong.
disassemble
info registers rip rax rbx rcx rdx rsi rdi rbp
quit
EOF

sed -i \
    -e "s|__ARM_AFTER__|${ARM_AFTER}|g" \
    -e "s|__DEADLINE__|${DEADLINE}|g" \
    -e "s|__VRAM__|${VRAM}|g" \
    -e "s|__WATCH_COND__|${WATCH_COND}|g" \
    "$GDB_SCRIPT"

# shellcheck source=scripts/display_isolate.sh
. "$(dirname "$0")/display_isolate.sh"
snp_isolate_display gdb_watch
trap 'rm -f "$GDB_SCRIPT"; snp_display_cleanup' EXIT INT TERM

echo "launching $BIN under gdb; arm at ${ARM_AFTER}s, hard deadline ${DEADLINE}s..."
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 \
    setsid stdbuf -oL -eL gdb -batch -x "$GDB_SCRIPT" --args "$BIN" > "$LOG_FILE" 2>&1

echo "gdb exited; log: $LOG_FILE ($(wc -l < "$LOG_FILE") lines)"

# Clean up by PID/exe, never by `pkill -f <path>` (that kills the caller).
_self_exe="$(readlink -f "$BIN" 2>/dev/null)"
for _pid in $(pgrep -f SinPunishmentRecompiled 2>/dev/null); do
    [[ "$_pid" == "$$" ]] && continue
    if [[ "$(readlink -f "/proc/$_pid/exe" 2>/dev/null)" == "$_self_exe" ]]; then
        kill -9 "$_pid" 2>/dev/null
    fi
done
rm -f "$GDB_SCRIPT"
exit 0
