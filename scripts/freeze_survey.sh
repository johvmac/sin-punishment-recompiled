#!/usr/bin/env bash
# Run freeze_check.sh N times against one binary and tabulate the OUTCOMES.
#
# Usage: scripts/freeze_survey.sh <N> <binary> [outdir] [times]
#
# WHY: this game's boot is NONDETERMINISTIC run-to-run -- the same binary
# produces "animates fine", "freezes on one frame", "silent exit" and "never
# renders (black)" on different runs. Any conclusion drawn from a single run is
# unfounded by construction; two such conclusions were made and retracted on
# 2026-08-15. Only the outcome RATE over N runs means anything.
#
# Outcome classification per run:
#   BLACK     - every captured frame is ~fully dark and identical
#   EXITED    - process died before the last capture
#   FROZEN    - last two captures are the identical frame (and not black)
#   ANIMATING - every capture is a distinct frame
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

N="${1:-5}"
BIN="${2:-./build/SinPunishmentRecompiled}"
OUTDIR="${3:-/tmp/freeze_survey}"
TIMES="${4:-15 30 45 60}"
mkdir -p "$OUTDIR"

declare -A counts=( [ANIMATING]=0 [FROZEN]=0 [BLACK]=0 [EXITED]=0 )

echo "survey: $N runs of $BIN  (captures at: $TIMES)"
echo

for i in $(seq 1 "$N"); do
    OUT="$OUTDIR/run$i"
    RESULT=$(bash "$(dirname "$0")/freeze_check.sh" "$TIMES" "$BIN" "$OUT" 2>&1)

    if grep -q "PROCESS EXITED" <<<"$RESULT"; then
        VERDICT=EXITED
    else
        # Collect the frame hashes and darkness values in capture order.
        HASHES=$(grep -oE 'frame=[0-9a-f]+' <<<"$RESULT" | cut -d= -f2)
        DARKS=$(grep -oE 'dark=[0-9.]+' <<<"$RESULT" | cut -d= -f2)
        UNIQ=$(sort -u <<<"$HASHES" | grep -c .)
        TOTAL=$(grep -c . <<<"$HASHES")
        ALLDARK=$(awk '$1 < 0.995 { bright=1 } END { print bright ? "no" : "yes" }' <<<"$DARKS")

        if [ "$ALLDARK" = "yes" ] && [ "$UNIQ" -eq 1 ]; then
            VERDICT=BLACK
        elif [ "$UNIQ" -eq "$TOTAL" ] && [ "$TOTAL" -gt 1 ]; then
            VERDICT=ANIMATING
        else
            VERDICT=FROZEN
        fi
    fi

    counts[$VERDICT]=$(( counts[$VERDICT] + 1 ))
    printf 'run %-2s -> %s\n' "$i" "$VERDICT"
done

echo
echo "===== SUMMARY: $BIN ====="
for k in ANIMATING FROZEN BLACK EXITED; do
    printf '  %-10s %s/%s\n' "$k" "${counts[$k]}" "$N"
done
exit 0
