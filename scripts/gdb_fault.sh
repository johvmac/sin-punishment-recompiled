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
BIN="${3:-build-debug/SinPunishmentRecompiled}"

# DEFAULT IS build-debug, deliberately. This script's own header says `ctx`
# does not resolve against the release build, and that A122 cost a whole run
# to exactly that -- yet it defaulted to the release build until 2026-08-19.
# The result is the worst kind of output: the signature control prints
#     ok    expected boot_func_80033758
# which reads as success, while every register line silently says
#     (unsigned long long)ctx->r16 : No symbol "ctx" in current context.
# The fault is then IDENTIFIED but not CHARACTERISED, and two faults in the
# same function cannot be told apart. That is what nearly let A162 be merged
# into A99 on frame count alone. Pass the release build as $3 to override.

case "${1:-}" in
    --help|-h) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --self-check)
        # This script had NO controls at all until A191, despite producing
        # A99's identification. These are static: they check that the
        # A99-specific register LABELS cannot be printed on a fault the
        # script's own control has just declared is not A99.
        #
        # GREP THE EXECUTABLE REGION ONLY -- everything after the `esac` that
        # closes this case. Eight times in this codebase a control has matched
        # its own text and passed on a broken script (T100/T112). Excluding
        # the self-check block fixes every control in the file at once.
        fails=0; n=0
        chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }
        BODY=$(awk 'f{print} /^esac$/{f=1}' "$0")

        _lbl='the garbage pointer that was dereferenced'
        _grd='if _is_a99:'
        i_grd=$(printf '%s\n' "$BODY" | grep -nF "$_grd" | head -1 | cut -d: -f1)
        i_lbl=$(printf '%s\n' "$BODY" | grep -nF "$_lbl" | head -1 | cut -d: -f1)
        got=0; [[ -n "$i_grd" && -n "$i_lbl" && "$i_grd" -lt "$i_lbl" ]] && got=1
        chk "A99's register labels are GUARDED, not unconditional" "$got" \
            "guard@${i_grd:-none}, label@${i_lbl:-none} -- a non-A99 fault would be mislabelled"

        # The unlabelled branch must actually say why, or a reader reads two
        # bare numbers and supplies A99's meanings from memory.
        got=0; printf '%s\n' "$BODY" | grep -qF 'UNLABELLED ON PURPOSE' && \
               printf '%s\n' "$BODY" | grep -qF 'caller-saved' && got=1
        chk "the unlabelled branch explains itself and names the \$v0 trap" "$got" \
            "no explanation -- bare numbers invite A99's meanings"

        # The in-run control that discriminates must still be there.
        got=0; printf '%s\n' "$BODY" | grep -qF 'This is NOT A99' && got=1
        chk "the fault-identity control is present" "$got" "no discrimination between faults"

        # T85: it must default to the DEBUG build or ctx does not resolve.
        got=0; printf '%s\n' "$BODY" | grep -q 'build-debug' && got=1
        chk "defaults to build-debug (T85: no ctx, no registers)" "$got" "would report a fault with no registers"

        echo; echo "$((n-fails))/$n controls pass"
        [[ $fails -eq 0 ]] || exit 1
        exit 0 ;;
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

echo \n===== CONTROL: is this the fault we think it is? =====\n
# Without this, a register dump from SOME OTHER crash reads exactly like a
# register dump from the expected one, and every ledger number keyed to A99
# would be quietly wrong. Cheap, and it is the difference between a measurement
# and a plausible-looking one.
python
import gdb
try:
    f = gdb.selected_frame()
    name = f.name() or "<unknown>"
    expected = "boot_func_80033758"
    ok = (name == expected)
    print("  faulting function = %s" % name)
    print("  %s  expected %s" % ("ok  " if ok else "MISMATCH --", expected))
    if not ok:
        print("  >>> This is NOT A99's crash. Ledger values keyed to A99 do not apply here.")
    n = 0
    fr = f
    while fr and n < 40:
        if (fr.name() or "") == expected:
            n += 1
        fr = fr.older()
    print("  %s frames of %s on the stack (A99 shows 5)" % (n, expected))
except Exception as e:
    print("  control FAILED to evaluate: %s" % e)
end

echo \n===== GAME REGISTER FILE AT THE FAULT =====\n
# The recompiled functions carry a `ctx` (recomp_context*). $s0 is r16 and
# $v0 is r2. THE REST OF THIS COMMENT DESCRIBES A99 AND ONLY A99 (A191) --
# the register ROLES below are read off A99's faulting instruction, so they
# are meaningless at any other site. The code prints them only when the
# control confirms A99.
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
    # THE LABELS ARE A99-SPECIFIC AND MUST NOT BE PRINTED ON ANOTHER FAULT (A191).
    # This block used to print them unconditionally, three lines below the
    # control that says "This is NOT A99's crash". On the post-A99 fault that
    # produced "$v0 (r2) = 0x8013CF7C  <-- the garbage pointer that was
    # dereferenced" -- and it was neither. The dereferenced pointer was $s0=0,
    # and $v0 is CALLER-SAVED, so after a jalr it holds the callee's RETURN
    # VALUE. A reader taking the label at face value would chase a number with
    # no established meaning.
    try:
        _is_a99 = (gdb.selected_frame().name() or "") == "boot_func_80033758"
    except Exception:
        _is_a99 = False
    if _is_a99:
        print("  $s0 (r16) vram = 0x%08X   <-- ADDRESS the faulting value was loaded FROM" % r16)
        print("  $v0 (r2)  vram = 0x%08X   <-- the garbage pointer that was dereferenced" % r2)
    else:
        print("  $s0 (r16) vram = 0x%08X" % r16)
        print("  $v0 (r2)  vram = 0x%08X" % r2)
        print("  >>> UNLABELLED ON PURPOSE: the roles above are A99's, and the")
        print("      control already reported this is not A99. Work out what each")
        print("      register means AT THIS SITE before using either value.")
        print("      In particular $v0 is caller-saved -- immediately after a")
        print("      call it is a RETURN VALUE, not necessarily a pointer.")
    if 0x80000000 <= r16 < 0x80800000:
        host = base + (r16 - 0x80000000)
        print("  word currently at $s0 = 0x%08X" % int(gdb.parse_and_eval("*(unsigned int *)%d" % host)))
except Exception as e:
    # LOUD, because the signature control above prints "ok" either way.
    # Against a non-debug build every ctx lookup raises and the report still
    # LOOKS like a successful identification -- the fault is named but not
    # characterised, so two different faults in the same function are
    # indistinguishable (that is how A162 nearly merged into A99 on frame count
    # alone). A tool must not report success for a measurement it did not make.
    print("\n  !! REGISTERS NOT CAPTURED: %s" % e)
    print("  !! The fault is IDENTIFIED but NOT CHARACTERISED -- $s0/$v0 are unknown,")
    print("  !! so this log CANNOT distinguish two faults in the same function.")
    print("  !! Almost certainly a non-debug binary: `ctx` only resolves in build-debug (A122).")
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
        # WALKER-FRAME GATE (A132). Do not guess the recursion depth, and do
        # NOT take gdb's backtrace as a frame count -- it showed five walker
        # frames where the game stack has three, and that single mistake
        # produced A125's "measured discontinuity", A128's five-level premise
        # and A130's stack-corruption story, all three withdrawn.
        #
        # The prologue saves $s2 at +0x18 and $s4 at +0x20, and the walker
        # holds the node pointer in $s2 and the child list in $s4 for its
        # whole body. So a frame whose SAVED $s2/$s4 are not node-array
        # pointers was NOT entered from the walker: the descent ends at the
        # frame before it, and everything above is another function's locals.
        s2 = u32(base + (fsp + 0x18 - 0x80000000))
        s4 = u32(base + (fsp + 0x20 - 0x80000000))
        isnode = lambda w: 0x80200000 <= w < 0x80400000
        walker = isnode(s2) and isnode(s4)
        flag = "" if walker else "   <-- entered from something ELSE; descent ends above this"
        print("  %-4d 0x%08X   0x%08X   0x%08X%s%s" % (k, fsp, s0, ra, delta, flag))
        prev = s0
    print("")
    steps = 0
    vals = [live]
    for k in range(4):
        fsp = (sp + k * FRAME) & 0xFFFFFFFF
        if not (0x80000000 <= fsp < 0x80800000):
            break
        vals.append(u32(base + (fsp + S0_OFF - 0x80000000)))
    for i in range(len(vals) - 1):
        d = (vals[i] - vals[i + 1]) & 0xFFFFFFFF
        if d and d < 0x400 and d % 4 == 0:
            steps += 1
        else:
            break
    print("  CONTROL: %d consecutive level(s) differ by a small multiple of 4," % steps)
    print("  which is the stride A124 predicts. 0 would mean the walk is misaligned")
    print("  or these are not walker frames -- do NOT read the values above as a")
    print("  descent in that case. (Do not use saved $ra as the check: it carries no")
    print("  meaning in recompiled output, A125.)")
    print("  DEPTH (A132): count the UNFLAGGED rows above, plus the live $s0. That is")
    print("  the recursion depth. Do NOT use gdb's backtrace for it -- it reports more")
    print("  walker frames than the game stack has, and three withdrawn entries")
    print("  (A125, A128's premise, A130) all trace to trusting it.")
    print("  Sanity: $s0 moves +0..+1020 per level (andi 0xFF then sll 2), never back.")
except Exception as e:
    print("  stack walk failed: %s" % e)
end

echo \n===== RDRAM SNAPSHOT =====\n
# The USEFUL alternative to a core file. librecomp reserves 4GB and commits
# 512MB (addresses.hpp), which is why generate-core-file produced 11.8 GB (T63).
# But every address this project has ever examined -- 0x8013C278, 0x802E1798,
# 0x80376160 -- is inside the first few MB of RDRAM. So dump THAT: 8MB, about
# 1/1500th of a core, and it contains everything we actually query.
#
# Written alongside it: the ctx register file, so the snapshot is self-contained
# and can answer "what was $s0" as well as "what was at this address".
# Read it back with scripts/rdram_peek.py -- no gdb needed.
python
import gdb, os, struct
path = os.environ.get("SNP_RDRAM_DUMP", "")
if path:
    try:
        base = int(gdb.parse_and_eval("*(unsigned long long *)&g_rdram_base"))
        size = int(os.environ.get("SNP_RDRAM_MB", "8")) * 1024 * 1024
        gdb.execute("dump binary memory %s %d %d" % (path, base, base + size))
        regs = []
        for i in range(32):
            regs.append(int(gdb.parse_and_eval("(unsigned long long)ctx->r%d" % i)) & 0xFFFFFFFFFFFFFFFF)
        with open(path + ".ctx", "wb") as f:
            f.write(struct.pack("<Q", base))
            for v in regs:
                f.write(struct.pack("<Q", v))
        print("  wrote %s (%.1f MB) + .ctx" % (path, os.path.getsize(path) / 1e6))
        print("  read it with:  scripts/rdram_peek.py %s 0x8013C278" % path)
    except Exception as e:
        print("  snapshot FAILED: %s" % e)
else:
    print("  skipped -- set SNP_RDRAM_DUMP=<path> (8MB). Prefer this over SNP_CORE.")
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
