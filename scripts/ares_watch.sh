#!/usr/bin/env bash
# G6: watch a game address inside ares (hardware-accurate) and report whether
# the real game ever writes it.
#
# Usage: scripts/ares_watch.sh <vram_addr> [deadline_s] [logfile]
#   scripts/ares_watch.sh 0x8007AF0C 90 /tmp/ares_watch.log
#
# WHY: our build corrupts the callback table at 0x8007AF0C at attract frame
# 1240, because thread 4's scene walk runs 98% of the way down its 8KB stack and
# its callees cross the floor. The open question is whether that depth is
# faithful to hardware (so the real game overflows too) or whether our call
# chain is ~240 bytes fatter. ares is hardware-accurate, so if the real game
# never writes that address, the overflow is ours.
#
# Requires gdb-multiarch: system gdb has no MIPS target ("set architecture mips"
# -> Undefined item) and cannot decode the register set, which is what blocked
# this comparison previously.
#
# Hard-won mechanics, do not remove:
# * ABSOLUTE ROM path. A relative path does not resolve inside the flatpak
#   sandbox: ares starts, opens the debug port, and sits at its menu with
#   nothing running -- the port listens and the session still fails, i.e. the
#   same symptom for a completely different reason.
# * Verify the LIVE process cmdline, not the command you think you ran. A failed
#   background relaunch once left an older, wrongly-invoked instance running and
#   the "retry" silently re-tested it.
# * Hard deadline + unbuffered log. A watchpoint that never fires otherwise
#   leaves `continue` blocking forever with a window open, and killing the
#   process discards gdb's buffered output so the log looks empty rather than
#   negative.
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

VRAM="${1:?usage: ares_watch.sh <vram_addr> [deadline_s] [logfile]}"
DEADLINE="${2:-90}"
LOG_FILE="${3:-/tmp/ares_watch.log}"
# Optional canary: a value written into the watched word before polling starts.
# Used to test whether the real game's stack ever descends into a region ours
# does. A CONDITIONAL BREAKPOINT cannot answer this -- boot_func_80033758 is
# called ~62,000 times in 42s, and gdb stops and evaluates the condition at
# every hit, which is hopelessly slow over RSP. Writing a sentinel into
# currently-unused stack and polling it costs nothing and answers the same
# question: if the value survives, the game never reached that depth.
CANARY="${4:-}"
# Positive control: a block of RDRAM that a RUNNING game must churn (thread 3's
# stack, per SNP_STACKS). Sampled every poll purely to prove the emulator is
# executing -- see the VERDICT section. Overridable for a different game state.
CONTROL="${SNP_CONTROL_ADDR:-0x80067000}"
CONTROL_WORDS="${SNP_CONTROL_WORDS:-64}"
ROM="$(pwd)/rom/Tsumi to Batsu - Hoshi no Keishousha (Japan).z64"
PORT=9123

if ! command -v gdb-multiarch >/dev/null; then
    echo "ERROR: gdb-multiarch not installed" >&2; exit 1
fi
if [[ ! -r "$ROM" ]]; then
    echo "ERROR: ROM not readable at $ROM" >&2; exit 1
fi

# Clear any earlier instance so we cannot accidentally test the wrong one.
for p in $(pgrep -f 'ares --setting' 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
sleep 1

echo "launching ares (window opens for up to ${DEADLINE}s)..."
nohup timeout -s KILL "$((DEADLINE + 20))" flatpak run dev.ares.ares \
    --setting DebugServer/Enabled=true \
    --setting DebugServer/Port="$PORT" \
    --setting DebugServer/UseIPv4=true \
    --system "Nintendo 64" "$ROM" > "${LOG_FILE}.ares" 2>&1 &

# Wait for the port, and confirm the running instance really has the ROM.
for _ in $(seq 1 30); do
    sleep 1
    ss -ltn 2>/dev/null | grep -q ":${PORT}" && break
done
if ! pgrep -af 'ares --setting' | grep -q "Tsumi to Batsu"; then
    echo "ERROR: running ares instance does not have the ROM on its cmdline" >&2
    pgrep -af 'ares --setting' | head -2 >&2
    exit 1
fi
sleep 3

GDB_SCRIPT="$(mktemp /tmp/ares_watch_XXXXXX.gdb)"
# QUOTED delimiter. With an unquoted 'EOF' the shell expands the body, and a
# backtick pair inside a COMMENT becomes command substitution: the two
# `continue` mentions below ran as shell builtins ("continue: only meaningful in
# a for/while/until loop") and were deleted from the generated script. Harmless
# by luck here -- they were comments -- but the same expansion would silently
# mangle any $ or backtick in the gdb/Python body. Values are substituted
# explicitly via sed below instead. Same family as the heredoc trap in the
# playbook.
cat > "$GDB_SCRIPT" << 'EOF'
set pagination off
set confirm off
set architecture mips:4000
target remote localhost:__PORT__

echo \n===== INITIAL VALUE =====\n
x/1xw __VRAM__

python
import threading, gdb, os, signal
def deadline():
    import time
    time.sleep(__DEADLINE__)
    os.killpg(os.getpgid(0), signal.SIGKILL)
threading.Thread(target=deadline, daemon=True).start()
end

echo \n===== CANARY =====\n
python
canary = "__CANARY__".strip()
if canary:
    import gdb
    gdb.execute("set *(unsigned int *) __VRAM__ = %s" % canary)
    print("[ares] planted %s at __VRAM__" % canary, flush=True)
    print(gdb.execute("x/1xw __VRAM__", to_string=True).strip(), flush=True)
end

echo \n===== POLLING =====\n
# POLL rather than watch. A watchpoint can force ares to single-step, which
# slows emulation so much that it may never reach the attract transition inside
# the deadline -- so "watchpoint never fired" would be unfalsifiable. Polling
# lets ares run at full speed and still shows any change, with the tradeoff that
# we see the change but not its writer. Establish WHETHER first, WHO second.
python
import gdb, threading, time
# `continue` blocks until the target stops, so the interrupt has to come from a
# separate OS thread via post_event -- the same mechanism gdb_threads.sh uses.
# `continue &` is not available in batch mode. Every print flushes explicitly:
# gdb's Python stdout buffers independently of stdbuf, so an unflushed line is
# lost when the deadline kills the process group.
def interrupter():
    while True:
        time.sleep(2.0)
        gdb.post_event(lambda: gdb.execute("interrupt", to_string=True))
threading.Thread(target=interrupter, daemon=True).start()

def read_words(addr, count):
    out = []
    for line in gdb.execute("x/%dxw %s" % (count, addr), to_string=True).splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2:
            out.extend(parts[1].split())
    return out

# POSITIVE CONTROL, sampled every poll alongside the watched address.
#
# Without it, "the watched word never changed" is unfalsifiable: a HALTED
# emulator produces exactly that reading, and so does a running one that simply
# never writes there. This is the failure that voided the 2026-08-17 run -- a
# 0xDEADBEEF canary survived 86 seconds at 0x8007AF0C, which cannot happen while
# the game is live (that word is a function pointer the callback pump dispatches
# through), and gdb reported PC = 0xffffffff at every stop.
#
# The control is a block of thread 3's stack. A running game hammers its stacks
# continuously, so if not one word here changes across the whole run, ares was
# not executing and every number the run produced is void.
control_prev = None
control_changes = 0
polls = 0
pcs = set()

prev = None
start_t = time.time()
while time.time() - start_t < __DEADLINE__ - 15:
    try:
        gdb.execute("continue", to_string=True)
    except gdb.error:
        pass
    try:
        val = read_words("__VRAM__", 1)[-1]
        control = read_words("__CONTROL__", __CONTROL_WORDS__)
    except (gdb.error, IndexError) as e:
        print("[ares] read failed: %s" % e, flush=True)
        break
    polls += 1
    try:
        pcs.add(str(gdb.parse_and_eval("$pc")))
    except gdb.error:
        pass
    if control_prev is not None and control != control_prev:
        control_changes += 1
    control_prev = control
    tag = "   <<< CHANGED" if prev is not None and val != prev else ""
    print("[ares] t=%5.1fs __VRAM__ = %s%s  [control %d/%d]"
          % (time.time() - start_t, val, tag, control_changes, polls), flush=True)
    prev = val

print("\n===== VERDICT =====", flush=True)
print("[ares] polls=%d  control block __CONTROL__ changed in %d of them"
      % (polls, control_changes), flush=True)
print("[ares] distinct PC values seen: %s" % (sorted(pcs)[:4] or "none"), flush=True)
if polls and control_changes * 4 >= polls:
    print("[ares] CONTROL OK -- ares was executing; the __VRAM__ result is meaningful.",
          flush=True)
else:
    print("[ares] CONTROL FAILED -- RDRAM was static, so ares was NOT running the",
          flush=True)
    print("[ares] game. This run proves NOTHING about __VRAM__. Do not use it.",
          flush=True)
end
quit
EOF

# Substitute values into the quoted heredoc. Placeholders are __NAME__ rather
# than ${NAME} so nothing in the body can be expanded by accident.
sed -i \
    -e "s|__PORT__|${PORT}|g" \
    -e "s|__VRAM__|${VRAM}|g" \
    -e "s|__DEADLINE__|${DEADLINE}|g" \
    -e "s|__CANARY__|${CANARY}|g" \
    -e "s|__CONTROL_WORDS__|${CONTROL_WORDS}|g" \
    -e "s|__CONTROL__|${CONTROL}|g" \
    "$GDB_SCRIPT"

setsid stdbuf -oL -eL gdb-multiarch -batch -x "$GDB_SCRIPT" >> "$LOG_FILE" 2>&1

echo "gdb exited; log: $LOG_FILE"
for p in $(pgrep -f 'ares --setting' 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
rm -f "$GDB_SCRIPT"
exit 0
