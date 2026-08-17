#!/usr/bin/env bash
# G7: dump every thread's backtrace from a running (usually hung) game.
#
# Usage: scripts/gdb_threads.sh [wait_seconds] [logfile] [binary]
#   scripts/gdb_threads.sh 90 /tmp/threads.log
#   scripts/gdb_threads.sh 90 /tmp/threads.log known_good_builds/SomeVariant
#
# Notes baked in from the playbook's G7 section -- do not "simplify" these away:
#
# * The game is launched as gdb's OWN CHILD, not attached to. Attaching runs
#   into ptrace_scope on this machine; launching as a child does not.
# * The interrupt is posted from INSIDE gdb by a real OS thread, not by an
#   external `kill -INT`. External signals were confirmed twice to either kill
#   gdb outright or be silently swallowed when gdb has no controlling tty
#   (which is the case under this tool's non-interactive execution), producing
#   no backtrace either way.
# * gdb slows execution roughly 10-20x, so wait_seconds is wall-clock time
#   under gdb and needs to be generously larger than the equivalent native
#   runtime you're trying to reach.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

WAIT_SECONDS="${1:-90}"
LOG_FILE="${2:-/tmp/gdb_threads.log}"
BIN="${3:-./build/SinPunishmentRecompiled}"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: $BIN not found or not executable" >&2
    exit 1
fi

GDB_SCRIPT="$(mktemp /tmp/gdb_threads_XXXXXX.gdb)"

cat > "$GDB_SCRIPT" << EOF
set pagination off
set confirm off
python
import threading, gdb
def interrupter():
    import time
    time.sleep(${WAIT_SECONDS})
    gdb.post_event(lambda: gdb.execute("interrupt"))
threading.Thread(target=interrupter, daemon=True).start()
end
run
echo \n===== THREAD STATE DUMP =====\n
info threads
echo \n===== FULL BACKTRACES =====\n
thread apply all bt 14
quit
EOF

echo "launching $BIN under gdb; will interrupt after ${WAIT_SECONDS}s wall..."
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 \
    gdb -batch -x "$GDB_SCRIPT" --args "$BIN" > "$LOG_FILE" 2>&1

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
