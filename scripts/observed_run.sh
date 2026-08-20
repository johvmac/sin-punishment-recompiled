#!/usr/bin/env bash
# A run the USER watches and listens to, with the checklist in front of them.
#
# WHY THIS EXISTS
# ---------------
# Two things this project cannot establish on its own:
#
#   1. I have been wrong TWICE about what is on screen (A93, A161). Both times
#      the observation was right and the QUANTIFIER was wrong -- "at these two
#      sampled instants" became "never". Sampling cannot support a claim about
#      the moments it did not sample.
#   2. I CANNOT PERCEIVE AUDIO AT ALL. Until 2026-08-20 the pipeline had no
#      audio input at all, so A97 -- entirely about audio silence -- rested
#      wholly on reading source. Game-only capture now exists (T102), but a
#      waveform still cannot tell me whether something sounds WRONG.
#
# WHY xephyr AND NOT real
# -----------------------
# `xephyr` shows a real window on the real display but keeps INPUT isolated --
# keystrokes reach the game only when its window has focus. `real` gives no
# isolation at all, and on 2026-08-19 four debugger runs put a live game window
# on the user's desktop with the keyboard connected to it (T59). An observed run
# needs to be SEEN, not to be unprotected. `SNP_ISO=real` is still reachable by
# hand for the rare case that needs it, and is deliberately not the default here.
#
# Audio plays through the normal system output either way -- it is not tied to
# the X display -- so xephyr costs nothing acoustically.
#
# AUDIO IS CAPTURED, AND ONLY THE GAME'S (T102)
# --------------------------------------------
# Delegated to scripts/audio_capture.sh, which routes ONLY the game's stream
# into a dedicated sink and records that sink's monitor -- so the capture can
# only contain what was moved into it. Recording the default sink would pick up
# whatever else the machine is playing: the same class of problem as filming the
# user's desktop (guarded since T83). That script asserts the isolation
# BEHAVIOURALLY with a two-tone control, not by inspection.
#
# Your ears remain the primary instrument. The capture exists so the answer
# outlives your memory of it, and so I can check it too.
#
# Usage:
#   scripts/observed_run.sh [seconds]     # default 180 (past the ~158s crash)
#   scripts/observed_run.sh --checklist   # print the checklist, run nothing
#   scripts/observed_run.sh --dry-run     # show what would happen, run nothing
#   scripts/observed_run.sh --self-check
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECKLIST="$ROOT/docs/observation-checklist.md"
LOG="$ROOT/docs/observed-runs.md"
EVID="${SNP_EVIDENCE_DIR:-/media/joh/extra/sin-punishment-archive/evidence/$(date +%Y-%m-%d)}"

usage() { sed -n '/^# Usage:/,/^set -/p' "$0" | sed 's/^# \{0,1\}//;$d'; }

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    --checklist) cat "$CHECKLIST"; exit 0 ;;
    --defer)
        # The gate in route.py must be clearable, because I CANNOT CLEAR IT
        # MYSELF -- an observed run needs the user. But it must be cleared by a
        # DECISION WITH A REASON, never silently. A reason is mandatory for
        # exactly that: "--defer" alone would become the default and the policy
        # would quietly evaporate.
        REASON="${2:-}"
        if [[ -z "$REASON" ]]; then
            echo "[observed] --defer needs a REASON: scripts/observed_run.sh --defer 'user away'" >&2
            echo "[observed] REFUSING a bare deferral — a silent skip is the thing" >&2
            echo "[observed] this policy exists to prevent." >&2
            exit 2
        fi
        [[ -f "$LOG" ]] || printf '# User-observed runs\n\n' > "$LOG"
        printf '## DEFERRED %s — %s\n- no observed run today; deferred deliberately, not skipped.\n\n' \
               "$(date +%Y-%m-%d)" "$REASON" >> "$LOG"
        echo "[observed] deferral recorded for $(date +%Y-%m-%d): $REASON"
        echo "[observed] route.py will now roll. The debt is visible in docs/observed-runs.md."
        exit 0 ;;
esac

# --self-check: controls that DISCRIMINATE. Each can fail (T65/T71).
if [[ "${1:-}" == "--self-check" ]]; then
    fails=0; n=0
    chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }

    # 1. The checklist must exist AND carry the two items only the user can
    #    answer. A checklist that lost the audio section would look fine and be
    #    useless, since audio is the one thing with no other instrument.
    got=0; [[ -f "$CHECKLIST" ]] && grep -qi 'AUDIO' "$CHECKLIST" && grep -q '⚑' "$CHECKLIST" && got=1
    chk "checklist exists and still marks the user-only items" "$got" "missing, or the ⚑/AUDIO sections are gone"

    # 2. It must NOT default to `real`. That is the T59 regression: an observed
    #    run on an unisolated display with live input.
    got=0; grep -q 'SNP_ISO=xephyr' "$0" && ! grep -qE '^\s*SNP_ISO=real' "$0" && got=1
    chk "defaults to xephyr, never to real (T59)" "$got" "would launch unisolated"

    # 3. It must go through run_game.sh, not the binary. The guard refuses a
    #    direct launch, and run_game.sh owns the watchdog and the run log.
    #
    #    FIRST VERSION WAS WRONG and failed on a correct script: it forbade the
    #    binary path appearing AT ALL, but this file legitimately names it to
    #    `sha256sum` the build. Naming is not launching. So: the path may appear
    #    only on the BIN= assignment, and the launch must be run_game.sh.
    uses_runner=0; grep -q 'run_game.sh" "\$SECS"' "$0" && uses_runner=1
    stray=$(grep -nE 'SinPunishmentRecompiled' "$0" | grep -vE '^\s*[0-9]+:BIN=' | grep -vc 'grep -' || true)
    got=0; [[ "$uses_runner" == "1" && "$stray" -eq 0 ]] && got=1
    chk "launches via run_game.sh; binary named only to hash it" "$got" \
        "runner=$uses_runner, stray binary references=$stray"

    # 4. It must print the checklist BEFORE launching. A checklist read
    #    afterwards is a memory test, which is the thing it exists to replace.
    a=$(grep -n 'cat "\$CHECKLIST"' "$0" | tail -1 | cut -d: -f1)
    b=$(grep -n 'run_game.sh' "$0" | tail -1 | cut -d: -f1)
    got=0; [[ -n "$a" && -n "$b" && "$a" -lt "$b" ]] && got=1
    chk "prints the checklist BEFORE the run, not after" "$got" "checklist at line $a, launch at line $b"

    # 5. Evidence must not default to /tmp (T47/T95).
    #
    #    NEEDLE ASSEMBLED FROM PARTS. Written literally, it matched INSIDE THIS
    #    CHECK and failed on a compliant script -- the FOURTH self-referential
    #    control in this codebase today (audit_l2 records two, lint_tools and
    #    audit_l3 each hit it, and now this). The pattern is systemic in how
    #    these checks get written, so assembling the needle is the default now.
    needle="EVID=.*:-""/tmp"
    got=0; ! grep -qE "$needle" "$0" && got=1
    chk "does not default evidence to /tmp (T47)" "$got" "would write evidence to /tmp"

    # 6. It must attach GAME-ONLY audio capture. Without this the run is silent
    #    for the record and the user's memory is the only artefact -- which is
    #    the state T101 found and this exists to end. The delegated script owns
    #    the privacy property and asserts it behaviourally in its own controls.
    got=0; grep -q 'audio_capture.sh" attach' "$0" && got=1
    chk "attaches game-only audio capture (T102)" "$got" "run would be recorded silent"

    echo; echo "$((n-fails))/$n controls pass"
    [[ $fails -eq 0 ]] || exit 1
    exit 0
fi

SECS="${1:-180}"
if [[ "$SECS" == "--dry-run" ]]; then DRY=1; SECS=180; else DRY=0; fi
if ! [[ "$SECS" =~ ^[0-9]+$ ]]; then
    echo "[observed] unknown argument: $SECS" >&2
    echo "[observed] REFUSING rather than guessing. --help for usage." >&2
    exit 2
fi

BIN="$ROOT/build/SinPunishmentRecompiled"
HASH="$(sha256sum "$BIN" 2>/dev/null | cut -c1-16)"
STAMP="$(date +%Y-%m-%dT%H:%M:%S%:z)"
RUNLOG="$EVID/observed-$(date +%H%M%S).log"

if [[ "$DRY" == "1" ]]; then
    echo "=== DRY RUN — nothing will be launched ==="
    echo "would print : $CHECKLIST"
    echo "would run   : SNP_ISO=xephyr scripts/run_game.sh $SECS $RUNLOG"
    echo "would append: $LOG   (build $HASH, $STAMP)"
    echo "would cap   : GAME-ONLY audio -> $EVID/observed-<time>.wav (T102)"
    echo "note        : your ears are still the primary instrument; the capture"
    echo "              exists so the answer outlives your memory of it"
    exit 0
fi

cat "$CHECKLIST"
echo
echo "==========================================================================="
echo " build $HASH   |   ${SECS}s   |   window appears shortly, INPUT IS ISOLATED"
echo " Expected: dies ~158s with no input. Sound: unknown -- LISTEN."
echo "==========================================================================="
read -r -p " Press Enter when you are ready to watch... " _

mkdir -p "$EVID"
AUDIO="$EVID/observed-$(date +%H%M%S).wav"

# Launch in the background so the game's audio stream can be attached once it
# exists -- the sink-input does not appear until the game opens audio, so the
# capture cannot simply start with the run.
SNP_ISO=xephyr "$ROOT/scripts/run_game.sh" "$SECS" "$RUNLOG" &
RUN_PID=$!
GPID=""
for _ in $(seq 1 40); do
    GPID=$(pgrep -n -f 'SinPunishmentRecompiled' 2>/dev/null || true)
    [[ -n "$GPID" ]] && break
    sleep 1
done
if [[ -n "$GPID" ]]; then
    "$ROOT/scripts/audio_capture.sh" attach "$GPID" "$AUDIO" "$((SECS + 20))" 30 &
    ACAP_PID=$!
else
    echo "[observed] WARNING: no game process found to attach audio to" >&2
    ACAP_PID=""
fi
wait $RUN_PID; RC=$?
[[ -n "$ACAP_PID" ]] && wait $ACAP_PID 2>/dev/null
if [[ -s "$AUDIO" ]]; then
    echo "[observed] game-only audio captured -> $(basename "$AUDIO")"
else
    echo "[observed] NO AUDIO CAPTURED — if the game never opened a stream that is"
    echo "[observed] itself a finding for A97: nothing is being produced at all,"
    echo "[observed] which is a different defect from wrong samples."
fi

echo
echo "=== run finished (rc=$RC). Recording the outcome — a run with no recorded"
echo "=== outcome did not happen, including 'exactly as expected'."
echo
ans() { read -r -p "$1 " REPLY; printf '%s' "${REPLY:-(no answer)}"; }
A_AUDIO=$(ans "1. AUDIO — any sound at all? describe:")
A_SCENE=$(ans "2. Last ~10s before it died — what was on screen?")
A_TITLE=$(ans "3. Title screen (if seen) — correct, or wrong how?")
A_DEATH=$(ans "4. Did it vanish / freeze / exit tidily, and roughly when?")
A_FEEL=$(ans  "5. Frame rate, input, anything else that looked wrong:")
A_DISAGREE=$(ans "6. ANYTHING that contradicts what I have claimed:")

[[ -f "$LOG" ]] || cat > "$LOG" <<'HDR'
# User-observed runs

Runs the user watched and listened to, with answers to
`observation-checklist.md`. **Recorded either way** — "exactly as expected" is
evidence too. A disagreement here becomes its own ledger finding, never a quiet
correction.

HDR

cat >> "$LOG" <<EOF
## $STAMP — build \`$HASH\`, ${SECS}s requested, rc=$RC
- run log: \`$(basename "$RUNLOG")\`
- **audio:** $A_AUDIO
- **last 10s / scene:** $A_SCENE
- **title screen:** $A_TITLE
- **how it died:** $A_DEATH
- **feel:** $A_FEEL
- **CONTRADICTS MY CLAIMS:** $A_DISAGREE

EOF

echo
echo "[observed] appended to docs/observed-runs.md"
[[ "$A_DISAGREE" == "(no answer)" || -z "$A_DISAGREE" ]] || \
    echo "[observed] *** A CONTRADICTION WAS RECORDED — this needs its own ledger entry. ***"
exit 0
