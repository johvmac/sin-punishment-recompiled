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

    # 6. It must capture GAME-ONLY audio, set up BEFORE launch (T104).
    #
    #    THIS CONTROL PRODUCED A FALSE PASS AND IS THE REASON THE RULE IS NOW
    #    ABSOLUTE. Its first version grepped for the literal string `attach`,
    #    which appeared nowhere in the script except INSIDE THIS CHECK -- so it
    #    matched itself and reported ok while the audio wiring had been replaced
    #    and was entirely unverified. The four earlier self-referential controls
    #    today produced false FAILURES, which are merely noisy. **A false PASS
    #    silently vouches for something that is not there**, which is strictly
    #    worse and is exactly what a control exists to prevent.
    #
    #    So: needles assembled from parts, and the check requires BOTH ends of
    #    the lifecycle -- a `prepare` with no `finish` leaks a null sink and
    #    silently breaks the user's audio routing.
    _pre="audio_capture.sh\" pre""pare"; _fin="audio_capture.sh\" fin""ish"
    got=0; grep -q "$_pre" "$0" && grep -q "$_fin" "$0" && got=1
    chk "captures game audio, set up BEFORE launch and torn down after (T104)" "$got" \
        "run would be recorded silent, or leak a null sink"

    # 7. The recorded outcome must come from run-log.tsv, NOT run_game.sh's exit
    #    status. The first observed run wrote "rc=0" into docs/observed-runs.md
    #    for a run that run-log.tsv recorded as "158 139 CRASHED": run_game.sh
    #    exits 0 having successfully run a game that died. **A permanent record
    #    that reads "exited cleanly" for a SIGSEGV is worse than no record.**
    #    THE NEEDLE MUST BE A CODE CONSTRUCT, NOT A WORD. The first version
    #    grepped for the filename -- which appears in the COMMENT above -- so it
    #    passed with the code path deleted. Assembling from parts is not enough
    #    on its own: prose that explains the check will also contain the words
    #    the check looks for. Match the ASSIGNMENT, which only code can contain.
    #    AND IT MUST REACH THE RECORD, NOT JUST THE TERMINAL. The first version
    #    of this control checked only that run-log.tsv was CONSULTED -- so it
    #    passed while the verdict was printed to the screen and left out of the
    #    stanza entirely. **A control that verifies the mechanism instead of the
    #    result is the same false-pass shape as control 6.** Check the template.
    _rc="RCROW=\$(""tail"; _vt="requested, rc=\$RC (\$VER""DICT)"
    got=0; grep -q "$_rc" "$0" && grep -q 'cut -f''4' "$0" && grep -q "$_vt" "$0" && got=1
    chk "the run log's rc AND verdict reach the permanent record" "$got" \
        "would record rc=0, or drop the verdict, for a crashed run"

    # 8. THE MEDIA MUST REACH THE RECORD, NOT JUST THE TERMINAL (T150). The
    #    stanza named the run LOG alone, while run_game.sh printed the finished
    #    .mp4 to the screen where it died with the scrollback. The agreed return
    #    path is time-aligned annotation of that recording (A266), which cannot
    #    start if the permanent record does not say which file.
    #    SAME FALSE-PASS SHAPE AS 6 AND 7, so the same defence: check the STANZA
    #    TEMPLATE, not the resolution step -- resolving a path the record never
    #    prints is precisely the failure being replaced. Needles assembled from
    #    parts, and BOTH media are required separately, because our .mp4 carries
    #    no audio track: a check satisfied by the video alone would vouch for
    #    handing the user a silent film and leaving A97 where it is.
    _vid="VIDEO=\$(""ls"; _vln="**vi""deo:**"; _sln="**sou""nd:**"
    got=0; grep -qF "$_vid" "$0" && grep -qF "$_vln" "$0" && grep -qF "$_sln" "$0" && got=1
    chk "video AND sound paths reach the permanent record (T150)" "$got" \
        "the annotator gets a text log and is told to go find the recording"

    # EVERY ANSWER ASKED FOR MUST REACH THE RECORD. The prompts and the stanza
    # are two halves with nothing connecting them but matching variable names,
    # and this project has now been bitten FIVE times by state that lives in two
    # places with no check that they agree (T185/T187/T193/T194/T195/T200).
    # Rename a variable in one half and the user answers a question whose answer
    # is silently dropped -- the worst possible failure for a procedure whose
    # entire cost is THEIR time. Added 2026-08-26 when the prompts were re-aimed.
    asked=$(grep -oE '^A_[A-Z]+=\$\(ans ' "$0" | sed 's/=\$(ans //')
    missing=""
    for v in $asked; do
        grep -q "\$$v" <(sed -n '/^cat >> "\$LOG" <<EOF/,/^EOF$/p' "$0") || missing="$missing $v"
    done
    nasked=$(printf '%s\n' $asked | grep -c . )
    chk "every prompt's answer reaches the stanza ($nasked asked)" \
        "$([[ -z "$missing" ]] && echo 1)" \
        "DROPPED ON THE FLOOR:$missing — the user would answer and it would vanish"

    echo; echo "$((n-fails))/$n controls pass"
    [[ $fails -eq 0 ]] || exit 1
    exit 0
fi

# DEFAULT RAISED 180 -> 250 ON 2026-08-26 (A461), AND THE REASON IS A REAL COST
# ALREADY PAID: the prompts below ask what happens WHEN THE PICTURE FREEZES, and
# the freeze is at ~205-213 s (A451). At the old 180 s default the run ended on
# the watchdog before ever reaching it — so two of the six questions were
# UNANSWERABLE BY CONSTRUCTION, and the user answered them about the watchdog
# kill instead. **The prompts and the run length are a third pair of halves that
# must agree; the check below is what asserts it.**
SECS="${1:-250}"
if [[ "$SECS" == "--dry-run" ]]; then DRY=1; SECS=180; else DRY=0; fi
if ! [[ "$SECS" =~ ^[0-9]+$ ]]; then
    echo "[observed] unknown argument: $SECS" >&2
    echo "[observed] REFUSING rather than guessing. --help for usage." >&2
    exit 2
fi

# SAY SO IF THE RUN CANNOT REACH WHAT THE QUESTIONS ASK ABOUT (A461). Two of the
# six prompts are about the freeze at ~205-213 s. A shorter run is legitimate --
# the user may want a quick look -- but it must not silently collect answers to
# questions the run could never have shown them, which is exactly what happened
# on 2026-08-26 and cost half that run's value.
STALL_AT=205
if (( DRY == 0 && SECS < STALL_AT + 15 )); then
    echo "[observed] *** NOTE: ${SECS}s ENDS BEFORE THE FREEZE (~${STALL_AT}s). ***"
    echo "[observed] Questions 3 and 4 ask what happens WHEN THE PICTURE FREEZES."
    echo "[observed] This run will be stopped by the watchdog first, and a watchdog"
    echo "[observed] kill stops picture and sound together — which looks exactly"
    echo "[observed] like the thing those questions are about. Answer them 'n/a"
    echo "[observed] (run too short)' rather than describing the shutdown."
    echo "[observed] For the freeze, re-run with: scripts/observed_run.sh 250"
    echo
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
# BANNER RE-AIMED 2026-08-27. It said "dies ~158s with no input. Sound: unknown"
# and BOTH halves were dead: A450/A451 measured that nothing dies -- the picture
# freezes at ~205-213 s while the engine and the audio run straight on -- and the
# sound has worked since A447. A banner is the last thing read before watching,
# so a stale one aims the whole observation at a closed question.
#
# WHAT IS DELIBERATELY NOT SAID HERE: what I expect the sound to do. A498
# measured a specific prediction last night and it is timestamped in the ledger,
# so it cannot be retrofitted -- but printing it above the run would collect
# AGREEMENT rather than a judgement. That is the same principle the labelling
# task is built on (my answers are never shown beside the question), and it
# matters more here, because the listener is the only instrument there is.
echo " Nothing crashes. The PICTURE freezes ~205-213s; engine and sound run on."
echo " Sound works. What is OPEN is whether it stays WITH the picture -- listen"
echo " early, then again near the end, and judge for yourself."
echo "==========================================================================="
read -r -p " Press Enter when you are ready to watch... " _

mkdir -p "$EVID"
AUDIO="$EVID/observed-$(date +%H%M%S).wav"

# PREPARE THE CAPTURE BEFORE LAUNCHING (T104). The first observed run recorded
# 198 s of pure silence while the user HEARD a loud blip "as the program
# opened" -- the capture attached 6 s in, because the old path had to POLL for a
# sink-input that does not exist until the game opens audio. The one event worth
# hearing fell inside that gap, and a capture that reliably misses the
# interesting moment is worse than none: it yields a confident silent artefact.
CAPSINK=$("$ROOT/scripts/audio_capture.sh" prepare "$AUDIO" 2>/dev/null || true)
if [[ -n "$CAPSINK" ]]; then
    echo "[observed] capturing game audio from its FIRST sample (sink $CAPSINK)"
    PULSE_SINK="$CAPSINK" SNP_ISO=xephyr "$ROOT/scripts/run_game.sh" "$SECS" "$RUNLOG"
else
    echo "[observed] WARNING: audio capture unavailable; run silent for the record" >&2
    SNP_ISO=xephyr "$ROOT/scripts/run_game.sh" "$SECS" "$RUNLOG"
fi
"$ROOT/scripts/audio_capture.sh" finish 2>/dev/null || true

# THE TWO THINGS AN ANNOTATOR ACTUALLY NEEDS, AND THEY WERE BEING THROWN AWAY
# (T150). The stanza below named the run LOG and nothing else; run_game.sh
# prints the finished .mp4 to the TERMINAL, where it is lost the moment the
# scrollback goes. The agreed return path is time-aligned annotation of the
# recording (T101, and A266 is the worked example) -- which is impossible if
# the permanent record does not say WHICH FILE. Resolved here rather than
# parsed out of run_game.sh's output, because a path scraped from a log line
# breaks the next time that line is reworded.
#
# Audio finalises to .flac beside the .wav, and our .mp4 has NO audio track --
# so both are named separately and deliberately. A player handed only the video
# annotates a silent film and A97 stays exactly where it is.
VIDEO=$(ls -1t "$EVID"/run_game-*.mp4 2>/dev/null | head -1)
SOUND="${AUDIO%.wav}.flac"
[[ -f "$SOUND" ]] || SOUND="$AUDIO"
[[ -f "$SOUND" ]] || SOUND=""

# THE OUTCOME COMES FROM run-log.tsv, NOT from run_game.sh's exit status.
# The first observed run recorded "rc=0" in this file while run-log.tsv said
# "158 139 CRASHED" -- run_game.sh exits 0 having successfully run a game that
# died. A record reading "exited cleanly" for a SIGSEGV is worse than no record,
# and this file is meant to be read months later.
RCROW=$(tail -1 "$ROOT/docs/run-log.tsv" 2>/dev/null)
RC=$(printf '%s' "$RCROW" | cut -f4); VERDICT=$(printf '%s' "$RCROW" | cut -f9)
[[ -n "$RC" ]] || RC="unknown"

echo "=== run finished — run log says rc=$RC ($VERDICT). Recording the outcome; a"
echo "=== run with no recorded outcome did not happen, including 'as expected'."
echo
ans() { read -r -p "$1 " REPLY; printf '%s' "${REPLY:-(no answer)}"; }
# THE PROMPTS TRACK THE OPEN QUESTIONS AND MUST BE RE-AIMED WHEN THOSE CHANGE
# (2026-08-26, at the user's direction). The previous six were written during
# the SILENCE era and had gone stale in a way that wastes the one resource this
# whole procedure exists to spend: "AUDIO — any sound at all?" when the sound
# has worked since A447, and "before it DIED" when A450/A451 established that
# nothing dies — the picture freezes while the engine and the audio run on.
# **A stale prompt does not just miss an answer, it aims the user's attention
# at a question that is already closed.** Keep #6 verbatim whatever else moves:
# it is the standing disagreement channel (T101) and nothing else collects it.
# PROMPT 3 RETIRED AND ITS SLOT REUSED, 2026-08-27. It asked whether the sound
# keeps going past the freeze. THAT IS NOW ANSWERED BY AN INSTRUMENT and does
# not need the user's time: A498 stamped audio continuously to 214.6 s across
# two runs, well past the ~208 s freeze, so the answer is yes and it is
# measured. Retiring a prompt the moment an instrument can answer it is the
# whole discipline here — this procedure spends the ONE resource I cannot
# regenerate, and a question already answered elsewhere is a pure waste of it.
#
# WHAT REPLACES IT IS THE THING ONLY EARS CAN SETTLE. A498 established that we
# QUEUE far more audio than the device can play. It could NOT establish whether
# that excess ever reaches a listener — if it is being discarded somewhere, the
# backlog is a number in a log and nothing more. No probe I can write answers
# that. A person hearing whether the sound keeps pace with the picture does,
# in one run, and it is the difference between a real defect and an artefact.
#
# ASKED NEUTRALLY, AND SPLIT EARLY-VS-LATE ON PURPOSE: a single "is it in sync"
# invites a yes, and a drift that grows is invisible unless the question makes
# you compare two moments. No expected value is stated, here or in the banner.
A_MUSIC=$(ans   "1. Is it the RIGHT MUSIC? (same tunes/moments as the real game) —")
A_TEXTURE=$(ans "2. Does the sound have any STUTTER, BUZZ or GRAIN — or is it smooth? —")
A_SYNC=$(ans    "3. Sound vs picture: does it line up EARLY? and still near the END, or behind? —")
A_FREEZE=$(ans  "4. The freeze: WAITING mid-instruction (text card up), or HARD LOCK mid-motion? —")
A_SCENERY=$(ans "5. Tutorial background — still black/empty, or is any scenery there? —")
A_DISAGREE=$(ans "6. ANYTHING that contradicts what I have claimed:")

[[ -f "$LOG" ]] || cat > "$LOG" <<'HDR'
# User-observed runs

Runs the user watched and listened to, with answers to
`observation-checklist.md`. **Recorded either way** — "exactly as expected" is
evidence too. A disagreement here becomes its own ledger finding, never a quiet
correction.

HDR

cat >> "$LOG" <<EOF
## $STAMP — build \`$HASH\`, ${SECS}s requested, rc=$RC ($VERDICT)
- run log: \`$(basename "$RUNLOG")\`
- **video:** ${VIDEO:-\*\*NOT RECORDED\*\* — nothing to annotate}
- **sound:** ${SOUND:-\*\*NOT CAPTURED\*\* — A97 cannot be answered from this run}
- **right music (A97):** $A_MUSIC
- **sound texture / stutter (A460):** $A_TEXTURE
- **sound vs picture, early then late (A498):** $A_SYNC
- **freeze: waiting or locked (A451):** $A_FREEZE
- **tutorial scenery (A218):** $A_SCENERY
- **CONTRADICTS MY CLAIMS:** $A_DISAGREE

EOF

echo
echo "[observed] appended to docs/observed-runs.md"
[[ "$A_DISAGREE" == "(no answer)" || -z "$A_DISAGREE" ]] || \
    echo "[observed] *** A CONTRADICTION WAS RECORDED — this needs its own ledger entry. ***"
exit 0
