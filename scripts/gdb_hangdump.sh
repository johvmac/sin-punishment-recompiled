#!/usr/bin/env bash
# Catch a HANG in the act: run under gdb, interrupt after a delay, dump every
# thread's backtrace, exit. The instrument gdb_fault.sh cannot be, because a
# hang raises no signal to catch.
#
# Usage: scripts/gdb_hangdump.sh <settle_s> <out.txt> [bin]
#   settle_s  how long to let the process run before the interrupt
#   out.txt   where the backtraces land
#   bin       default build-debug/SinPunishmentRecompiled
#
# WHY IT EXISTS (2026-08-25, A104 rerun): with SIG0 honest, one audio task
# enters the recompiled ucode and never returns (A104, 3/3). A357 proved no
# COP0 wait loop can spin, so the hang site is unknown and only a live
# backtrace can name it. ptrace attach is blocked by yama ptrace_scope, so the
# process must be BORN under gdb -- same launch shape as gdb_trace.sh, same
# isolation, none of the breakpoint machinery.
#
# CONTROLS
#   * POSITIVE (run it on a healthy binary): the dump must contain the game's
#     thread roster with symbolised frames -- proving interrupt+bt works. A
#     hang diagnosis is only meaningful against that baseline.
#   * The dump REFUSES to report success if the backtrace contains no thread
#     matching the RSP/task path -- an empty dump is an instrument failure,
#     not evidence of health (T65: silence must be distinguishable).
#
# RDRAM AT A HANG (2026-08-27, A577/A580): set SNP_RDRAM_DUMP=<path> and the
# interrupt also snapshots the first SNP_RDRAM_MB (default 8) MB of game
# memory, readable with scripts/rdram_peek.py. This is the SAME pure-gdb
# mechanism gdb_fault.sh carries -- `dump binary memory` off g_rdram_base, no
# fault handler involved, so it fires at any stop. ONE DELIBERATE DIFFERENCE:
# the .ctx register file is guarded SEPARATELY, because at an arbitrary
# interrupt the stopped frame may not be recompiled code and `ctx` may not
# resolve (A122). A missing .ctx is reported and does NOT discredit the
# memory dump, which needs only the global g_rdram_base.
set -uo pipefail
case "${1:-}" in -h|--help) sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'; exit 0;; esac

SETTLE="${1:?settle seconds}"
OUT="${2:?output path}"
BIN="${3:-build-debug/SinPunishmentRecompiled}"
cd "$(dirname "$0")/.." || exit 1

. "$(dirname "$0")/display_isolate.sh"
. "$(dirname "$0")/build_staleness.sh"
snp_warn_if_stale "$BIN"
snp_isolate_display gdb_hangdump
trap 'snp_display_cleanup' EXIT INT TERM

echo "launching $BIN under gdb; interrupting after ${SETTLE}s for a full thread dump..."
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 \
    setsid stdbuf -oL -eL gdb -batch \
    -ex 'set pagination off' \
    -ex 'run' \
    -ex "python
import gdb, os, struct
path = os.environ.get('SNP_RDRAM_DUMP', '')
if path:
    try:
        base = int(gdb.parse_and_eval('*(unsigned long long *)&g_rdram_base'))
        size = int(os.environ.get('SNP_RDRAM_MB', '8')) * 1024 * 1024
        gdb.execute('dump binary memory %s %d %d' % (path, base, base + size))
        print('  wrote %s (%.1f MB)' % (path, os.path.getsize(path) / 1e6))
        print('  read it with:  scripts/rdram_peek.py %s 0x80068A84' % path)
    except Exception as e:
        print('  RDRAM snapshot FAILED: %s' % e)
    else:
        # ctx is guarded SEPARATELY (A122): at a hang interrupt the stopped
        # frame may not be recompiled code. The memory dump above stands
        # either way.
        try:
            regs = []
            for i in range(32):
                regs.append(int(gdb.parse_and_eval('(unsigned long long)ctx->r%d' % i)) & 0xFFFFFFFFFFFFFFFF)
            with open(path + '.ctx', 'wb') as f:
                f.write(struct.pack('<Q', base))
                for v in regs:
                    f.write(struct.pack('<Q', v))
            print('  wrote %s.ctx' % path)
        except Exception as e:
            print('  no .ctx (ctx not in scope at the interrupt point: %s) -- the memory dump is still valid' % e)
else:
    print('  RDRAM skipped -- set SNP_RDRAM_DUMP=<path> (8MB)')
end" \
    -ex 'thread apply all bt 16' \
    -ex 'info threads' \
    --args "$BIN" > "$OUT" 2>&1 &
GDB_PGID=$!

sleep "$SETTLE"
# SIGINT the whole process group: gdb forwards the stop to the inferior, `run`
# returns, and the remaining -ex commands produce the dump.
INF_PID=$(pgrep -x -n SinPunishmentRe || true)
if [[ -z "$INF_PID" ]]; then
    # comm is truncated to 15 chars; match the prefix explicitly if -x missed
    INF_PID=$(ps -eo pid,comm | awk '$2 ~ /^SinPunishmentRe/ {print $1}' | tail -1)
fi
if [[ -z "$INF_PID" ]]; then
    echo "REFUSING a verdict: no inferior process found to interrupt" | tee -a "$OUT"
    kill -TERM -- -"$GDB_PGID" 2>/dev/null
    exit 2
fi
kill -INT "$INF_PID"
# give gdb time to unwind every thread, then make sure everything dies
for _ in $(seq 1 30); do kill -0 "$GDB_PGID" 2>/dev/null || break; sleep 1; done
kill -TERM -- -"$GDB_PGID" 2>/dev/null
pkill -9 -x SinPunishmentRe 2>/dev/null || true

THREADS=$(grep -c '^Thread ' "$OUT" || true)
echo "dump: $OUT ($(wc -l < "$OUT") lines, $THREADS thread section(s))"
if [[ "$THREADS" -eq 0 ]]; then
    echo "REFUSING a verdict: no thread sections in the dump -- instrument failure"
    exit 2
fi
