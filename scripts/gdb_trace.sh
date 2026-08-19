#!/usr/bin/env bash
#
# Log a function's ENTRY ARGUMENTS at runtime, conditioned so it fires only on
# the case of interest.
#
# Usage: scripts/gdb_trace.sh <file:line> <cond> <printf-args> [arm_s] [deadline_s] [log] [bin]
#   e.g. scripts/gdb_trace.sh funcs_4.c:228 \
#          '((ctx->r6 & 0xFFFFFFFF) >= 0x8013A000 && (ctx->r6 & 0xFFFFFFFF) <= 0x8013D000)' \
#          'ctx->r4, ctx->r5, ctx->r6, ctx->r29' 150 280
#
# WHY THIS EXISTS (T69)
# A single RDRAM snapshot cannot tell a live stack frame from a leftover: memory
# above the outermost live frame holds whatever an earlier, deeper call left
# there, and leftovers of a recursive function look exactly like live frames of
# it. A99's stack yielded FOUR self-consistent, mutually incompatible readings
# (A125, A128, A130, A132); three are withdrawn. Call chains must be established
# by logging entry arguments, where each record is ONE REAL INVOCATION and a
# leftover cannot appear.
#
# TWO LOCATIONS IN ONE RUN (added 2026-08-19, roll #86, for A157)
# Set SNP_TRACE_LOC2 / SNP_TRACE_COND2 / SNP_TRACE_ARGS2 (all three, or none)
# to trace a SECOND line in the same run. Hits are prefixed HIT1 and HIT2.
#
# WHY THIS EXISTS. A99 spent six rolls on a contradiction that only survived
# because its three measurements were three separate runs (A157): :661 says a
# frame holds $s0 = 0x8013C270, :228 says that value was never passed as $a2,
# and :718 says the epilogue never restored it. Each is a negative from a
# different run, and T72 already cost us one negative that way. Comparing two
# sites ACROSS runs cannot distinguish "the instrument is wrong" from "the two
# runs differed"; comparing them WITHIN one run can.
#
# TWO CONTROLS, both required, because a silent no-fire is the danger:
#   * A REACH COUNTER -- a second breakpoint at the same line with a huge
#     `ignore` count. It never stops, it just counts. `info breakpoints` at the
#     end reports how many times the line was reached AT ALL. Zero conditional
#     hits means nothing only if the reach count is non-zero; if both are zero
#     the instrument never armed and the run says nothing (T56).
#   * ARM TIME must land BEFORE the event. gdb does not rewind. If the log shows
#     the fault but no hits and a healthy reach count, the condition is wrong,
#     not the timing.
#
# LOG (T47): defaults to <archive>/evidence/<today>/gdb_trace-<HHMMSS>.log, NOT
# /tmp -- a trace log is the evidence for whatever the run concludes, and the
# old /tmp default both died with the session and overwrote itself run to run.
# If the archive drive is not mounted it REFUSES rather than falling back.
# SNP_EVIDENCE_DIR overrides the directory; arg 6 overrides the whole path.
#
# BUILD: use build-debug. Against the release build `ctx` does not resolve and
# every condition silently errors (A122 cost a whole run to this).
#
# SIGN EXTENSION: ctx->rN is the SIGN-EXTENDED 64-bit value (I17). A KSEG0
# address arrives as 0xFFFFFFFF8xxxxxxx, so mask with & 0xFFFFFFFF in every
# condition and every printf. Comparing the raw value against 0x8013A000 is
# always false and looks exactly like "the case never happened".
set -uo pipefail

case "${1:-}" in
    -h|--help)
        sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'
        exit 0 ;;
    --self-check)
        exec "$(dirname "$0")/test_gdb_trace.py" ;;
esac
cd "$(dirname "$0")/.." || exit 1

LOC="${1:?usage: gdb_trace.sh <file:line> <cond> <printf-args> [arm_s] [deadline_s] [log] [bin]}"
COND="${2:?need a condition -- an unconditional trace at a hot line will not finish}"
ARGS="${3:?need printf arguments}"
ARM_AFTER="${4:-150}"
DEADLINE="${5:-280}"
# T47: EVIDENCE GOES TO THE ARCHIVE DRIVE, NEVER /tmp. This defaulted to
# /tmp/gdb_trace.log, which is the exact trap T47 records -- 11 cited filenames
# in the ledger are already unrecoverable because of it, and a trace log IS the
# evidence for whatever the run concludes. It also silently overwrote itself run
# to run, so a second trace destroyed the first one's record. Same convention
# and same failure behaviour as display_isolate.sh's recorder: name the run, and
# if the drive is absent say so rather than quietly writing somewhere that will
# not survive the session.
_default_log_dir="${SNP_EVIDENCE_DIR:-/media/joh/extra/sin-punishment-archive/evidence/$(date +%Y-%m-%d)}"
if [[ -z "${6:-}" ]] && ! mkdir -p "$_default_log_dir" 2>/dev/null; then
    echo "ERROR: cannot write $_default_log_dir -- the archive drive is not"  >&2
    echo "       mounted. Refusing to fall back to /tmp (T47): a trace log is" >&2
    echo "       evidence. Mount it, or pass an explicit log path as arg 6."   >&2
    exit 1
fi
LOG_FILE="${6:-$_default_log_dir/gdb_trace-$(date +%H%M%S).log}"
BIN="${7:-./build-debug/SinPunishmentRecompiled}"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: $BIN not found or not executable" >&2
    exit 1
fi
case "$BIN" in
    *build-debug*) ;;
    *) echo "WARNING: $BIN is not build-debug; 'ctx' will not resolve and every"
       echo "         condition will silently fail (A122). Continuing anyway." >&2 ;;
esac

# The printf format has exactly four %08X. Fewer arguments makes gdb error at
# every hit and the trace silently logs nothing; more silently drops them. Count
# top-level commas and refuse -- this costs nothing and a bad trace costs a run.
_ncomma=$(printf '%s' "$ARGS" | tr -cd ',' | wc -c)
if [[ "$_ncomma" -ne 3 ]]; then
    echo "ERROR: <printf-args> must be exactly 4 comma-separated expressions" >&2
    echo "       (the format string carries four %08X); got $((_ncomma + 1))." >&2
    exit 2
fi

# Second location: all three or none. A partial set is always a mistake, and
# silently ignoring it would produce a single-site log that LOOKS like the
# two-site run you asked for -- the failure mode this whole feature exists to
# avoid. Refuse instead.
LOC2="${SNP_TRACE_LOC2:-}"
COND2="${SNP_TRACE_COND2:-}"
ARGS2="${SNP_TRACE_ARGS2:-}"
_n2set=0
[[ -n "$LOC2"  ]] && _n2set=$((_n2set + 1))
[[ -n "$COND2" ]] && _n2set=$((_n2set + 1))
[[ -n "$ARGS2" ]] && _n2set=$((_n2set + 1))
if [[ "$_n2set" -ne 0 && "$_n2set" -ne 3 ]]; then
    echo "ERROR: SNP_TRACE_LOC2/COND2/ARGS2 must be set together or not at all" >&2
    echo "       (got $_n2set of 3). A partial set would silently trace one site." >&2
    exit 2
fi
if [[ "$_n2set" -eq 3 ]]; then
    _ncomma2=$(printf '%s' "$ARGS2" | tr -cd ',' | wc -c)
    if [[ "$_ncomma2" -ne 3 ]]; then
        echo "ERROR: SNP_TRACE_ARGS2 must be exactly 4 comma-separated expressions;" >&2
        echo "       got $((_ncomma2 + 1))." >&2
        exit 2
    fi
fi

GDB_SCRIPT="$(mktemp /tmp/gdb_trace_XXXXXX.gdb)"

# QUOTED delimiter -- an unquoted one expands the backticks in the comments and
# runs them as commands (the bug this file's sibling hit; see gdb_watch.sh).
cat > "$GDB_SCRIPT" << 'EOF'
set pagination off
set confirm off
set print elements 0

python
import threading, gdb
def arm():
    import time
    time.sleep(__ARM_AFTER__)
    gdb.post_event(lambda: gdb.execute("interrupt"))
def deadline():
    import time, os, signal
    time.sleep(__DEADLINE__)
    os.killpg(os.getpgid(0), signal.SIGKILL)
threading.Thread(target=arm, daemon=True).start()
threading.Thread(target=deadline, daemon=True).start()
end

run

echo \n===== ARMING TRACE =====\n
# The REACH COUNTER first, so it is impossible to forget. A huge ignore count
# means it never stops the inferior; gdb still counts every hit, and
# `info breakpoints` reports the total at the end. Without this, "0 hits" is
# ambiguous between "the condition was never true" and "the breakpoint was
# never reached", and those call for opposite next steps.
break __LOC__
ignore 1 1000000000

break __LOC__ if __COND__
commands 2
silent
# Generic labels + a header naming the expressions. The labels used to be
# hardcoded "a0/a1/a2/sp", which was right for the first trace and WRONG for
# the second (r16/r3/r6/r29 logged under a0/a1/a2 headings). A mislabelled
# log is worse than no log: it is evidence that reads as something else.
printf "HIT1 %08X %08X %08X %08X\n", __ARGS__
continue
end
__BLOCK2__
info breakpoints
echo \nFIELDS (in HIT1 order): __ARGS__\n
__FIELDS2__
echo \n===== CONTINUING =====\n
continue

echo \n===== STOPPED (fault, or deadline) =====\n
bt
echo \n===== BREAKPOINT COUNTS -- THE CONTROL =====\n
# Read this before believing any conclusion. bp1 is the reach counter: if it
# shows 0 hits the line was never executed and the trace proves nothing.
info breakpoints
quit
EOF

# NOT sed. In a sed replacement `&` means "the whole match", so the FIRST run of
# this script turned the condition
#     ((ctx->r6 & 0xFFFFFFFF) >= 0x8013A000 && ...)
# into
#     ((ctx->r6 __COND__ 0xFFFFFFFF) >= 0x8013A000 __COND____COND__ ...)
# gdb rejected it, the trace never armed, and the run cost 300 s to learn that.
# Any C condition worth writing here contains `&`. Substitute LITERALLY.
SNP_SUB_SCRIPT="$GDB_SCRIPT" SNP_SUB_ARM="$ARM_AFTER" SNP_SUB_DEAD="$DEADLINE" \
SNP_SUB_LOC="$LOC" SNP_SUB_COND="$COND" SNP_SUB_ARGS="$ARGS" \
SNP_SUB_LOC2="$LOC2" SNP_SUB_COND2="$COND2" SNP_SUB_ARGS2="$ARGS2" python3 - <<'PYSUB'
import os
p = os.environ["SNP_SUB_SCRIPT"]
s = open(p).read()

# The second site's breakpoints are 3 (reach) and 4 (conditional), because the
# first site already took 1 and 2 and gdb numbers them in creation order. Those
# numbers are asserted by test_gdb_trace.py against the generated script rather
# than trusted here: an `ignore`/`commands` aimed at the wrong breakpoint is
# silent -- the reach counter would stop the inferior on every hit, or the
# conditional one would never print -- and either ruins a whole run.
loc2 = os.environ["SNP_SUB_LOC2"]
if loc2:
    block2 = (
        "break {loc2}\n"
        "ignore 3 1000000000\n"
        "break {loc2} if {cond2}\n"
        "commands 4\n"
        "silent\n"
        'printf "HIT2 %08X %08X %08X %08X\\n", {args2}\n'
        "continue\n"
        "end\n"
    ).format(loc2=loc2, cond2=os.environ["SNP_SUB_COND2"],
             args2=os.environ["SNP_SUB_ARGS2"])
    fields2 = "echo \\nFIELDS (in HIT2 order): {}\\n\n".format(os.environ["SNP_SUB_ARGS2"])
else:
    block2 = ""
    fields2 = ""

for k, v in (("__ARM_AFTER__", os.environ["SNP_SUB_ARM"]),
             ("__DEADLINE__",  os.environ["SNP_SUB_DEAD"]),
             ("__BLOCK2__",    block2),
             ("__FIELDS2__",   fields2),
             ("__LOC__",       os.environ["SNP_SUB_LOC"]),
             ("__COND__",      os.environ["SNP_SUB_COND"]),
             ("__ARGS__",      os.environ["SNP_SUB_ARGS"])):
    s = s.replace(k, v)
open(p, "w").write(s)
PYSUB

# Refuse rather than run a mangled script. A leftover placeholder means a
# substitution silently did nothing, and the run would burn its whole deadline
# before the log revealed it.
if grep -q '__[A-Z_]*__' "$GDB_SCRIPT"; then
    echo "ERROR: unsubstituted placeholder(s) remain in the gdb script:" >&2
    grep -o '__[A-Z_]*__' "$GDB_SCRIPT" | sort -u >&2
    rm -f "$GDB_SCRIPT"
    exit 2
fi

# SNP_TRACE_DRYRUN=1 prints the generated script and exits WITHOUT launching.
# Use it before every real trace: a gdb syntax error costs one full deadline to
# discover, and costs nothing to catch here.
if [[ -n "${SNP_TRACE_DRYRUN:-}" ]]; then
    echo "=== generated gdb script (SNP_TRACE_DRYRUN, not launching) ==="
    cat "$GDB_SCRIPT"
    rm -f "$GDB_SCRIPT"
    exit 0
fi

# shellcheck source=scripts/display_isolate.sh
. "$(dirname "$0")/display_isolate.sh"
snp_isolate_display gdb_trace
trap 'rm -f "$GDB_SCRIPT"; snp_display_cleanup' EXIT INT TERM

if [[ -n "$LOC2" ]]; then
    echo "launching $BIN under gdb; trace $LOC + $LOC2, arm ${ARM_AFTER}s, deadline ${DEADLINE}s..."
else
    echo "launching $BIN under gdb; trace $LOC, arm ${ARM_AFTER}s, deadline ${DEADLINE}s..."
fi
SP_AUTOSTART=1 SDL_VIDEODRIVER=x11 \
    setsid stdbuf -oL -eL gdb -batch -x "$GDB_SCRIPT" --args "$BIN" > "$LOG_FILE" 2>&1

echo "gdb exited; log: $LOG_FILE ($(wc -l < "$LOG_FILE") lines)"
echo "conditional hits at $LOC: $(grep -c '^HIT1 ' "$LOG_FILE" 2>/dev/null || true)"
if [[ -n "$LOC2" ]]; then
    echo "conditional hits at $LOC2: $(grep -c '^HIT2 ' "$LOG_FILE" 2>/dev/null || true)"
fi

_self_exe="$(readlink -f "$BIN" 2>/dev/null)"
for _pid in $(pgrep -f SinPunishmentRecompiled 2>/dev/null); do
    [[ "$_pid" == "$$" ]] && continue
    if [[ "$(readlink -f "/proc/$_pid/exe" 2>/dev/null)" == "$_self_exe" ]]; then
        kill -9 "$_pid" 2>/dev/null
    fi
done
rm -f "$GDB_SCRIPT"
exit 0
