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

# --- help (T37) ------------------------------------------------------------
# Prints this script's own header block. Added after `route.py --help` was
# silently ignored and fell through to a state-mutating default.
case "${1:-}" in
    -h|--help)
        sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'
        exit 0 ;;
esac
cd "$(dirname "$0")/.." || exit 1

WAIT_SECONDS="${1:-90}"
LOG_FILE="${2:-/tmp/gdb_threads.log}"
# DEFAULTS TO build-debug, NOT build. A thread dump whose frames have no
# function names is not a thread dump -- and this tool exists to read a hung
# thread's stack. Same reasoning as gdb_fault.sh's default (T85).
BIN="${3:-./build-debug/SinPunishmentRecompiled}"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: $BIN not found or not executable" >&2
    exit 1
fi

# T125's staleness warning. THIS RUNNER WAS MISSED when the check was wired in:
# T125 says "all three runners" and named run_game.sh, gdb_fault.sh and
# gdb_trace.sh. This is a FOURTH, and it is the one most likely to be pointed at
# a stale debug tree, because `build.sh --no-recomp` builds RELEASE ONLY and a
# session that has been iterating on a runtime probe leaves build-debug hours
# behind without saying so. Found 2026-08-20 while about to do exactly that.
. "$(dirname "$0")/build_staleness.sh"
snp_warn_if_stale "$BIN"

# DISPLAY ISOLATION. This runner was ALSO missed when T59 was fixed. That entry
# says "there is now exactly one copy and the three callers source it" and names
# run_game.sh, gdb_watch.sh and gdb_fault.sh -- this is a FOURTH debugger, and
# without this it inherits DISPLAY and puts a live game window on the real
# desktop with the keyboard connected to it, which is precisely the incident
# T59 records. Found 2026-08-20, about to be tripped over.
#
# Same miss as the staleness wiring above, in the same file: a fix applied to
# "the three runners" when there were four. Both controls now DISCOVER their
# list rather than declaring it.
# shellcheck source=scripts/display_isolate.sh
. "$(dirname "$0")/display_isolate.sh"
snp_isolate_display gdb_threads

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
snp_display_cleanup
exit 0
