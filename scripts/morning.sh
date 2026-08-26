#!/usr/bin/env bash
# The day's machine-side preparation, run by cron before anyone is awake.
#
# WHY (the user's request, 2026-08-27): "make all of this trigger asap in the
# day - like 6am or something? I'd rather not have to wait around for it to get
# sorted out every day." The morning chores were being done at the keyboard
# while they waited. Everything here is work a machine can do alone.
#
# WHAT IT DELIBERATELY DOES NOT DO, and both are worth knowing:
#
#   1. IT DOES NOT REPUBLISH THE STATUS PAGE. That goes through the claude.ai
#      artifact capability, which needs interactive auth and is documented as
#      absent from headless/cron runs. A cron job that "publishes" and silently
#      fails every morning is precisely T194 -- the nightly push that died for
#      three days into a log nobody read. So it is not attempted; the session
#      does it, and the regenerate it needs takes under a second anyway.
#   2. IT DOES NOT RUN THE GAME, AND IT NEVER CLEARS THE OBSERVED-RUN GATE.
#      That gate exists because there are two things nobody here can check
#      alone -- audio, and scene identity (T101). A cron that cleared it would
#      destroy the one property it has. It only REPORTS whether one is owed.
#
# T151, THE USER'S RULE ABOUT RECURRING WORK, AND HOW THIS OBEYS IT:
# "Nothing recurring on this project may accumulate. A day with no work owes
# nothing." This job is CALENDAR-gated -- it fires at 6am whether or not anyone
# works that day -- which would normally be exactly the thing forbidden. It is
# allowed because IT BILLS NOBODY: it creates no debt, sends no notification,
# and nags about nothing. Its output is a file that is read only if someone
# comes to work. An idle day leaves a state file nobody opens. **If this ever
# grows a notification, it becomes calendar-gated nagging and breaks the rule.**
#
# THE DETECTOR, because a third cron job with a log file would repeat T194 (the
# push that failed silently for three days, surfaced only by an audit printing
# the last log line). This writes `.morning-state.json`, and `check_ledger.py`
# reads it and says so if it is stale or reports failures. That check runs when
# WORK happens, not on a clock -- so the detector is activity-gated even though
# the job is not.
#
# Usage:
#   scripts/morning.sh              # do it
#   scripts/morning.sh --dry-run    # say what it would do, change nothing
#   scripts/morning.sh --self-check
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2
STATE="$ROOT/docs/.morning-state.json"
REPORT="$ROOT/docs/MORNING.md"
TODAY="$(date +%Y-%m-%d)"
EVID="${SNP_EVIDENCE_DIR:-/media/joh/extra/sin-punishment-archive/evidence/$TODAY}"

usage() { sed -n '/^# Usage:/,/^set -/p' "$0" | sed 's/^# \{0,1\}//;$d'; }
case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    # REFUSE AN UNKNOWN ARGUMENT rather than silently doing a full run. This
    # fires on cron, unattended -- a typo'd flag that ran the real thing anyway
    # would be indistinguishable from the intended behaviour in the log.
    -*) if [[ "$1" != "--dry-run" && "$1" != "--self-check" ]]; then
            echo "[morning] unknown option: $1" >&2; usage >&2; exit 2
        fi ;;
esac

DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1

if [[ "${1:-}" == "--self-check" ]]; then
    fails=0; n=0
    chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"
            else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }

    # 1. It must never launch the game. The gate it reports on can only be
    #    cleared by a person, and a job that ran the game would look like it had.
    got=0; ! grep -qE '(run_game\.sh|observed_run\.sh)[^-]' "$0" && got=1
    chk "never launches the game or the observed run" "$got" \
        "a cron that runs the game looks like it cleared a gate only a person can"

    # 2. It must not attempt to publish. Needle assembled from parts -- written
    #    literally it matches inside this very check, which is how four
    #    self-referential controls in this codebase produced false results.
    _pub="mark-pub""lished"
    got=0; ! grep -q "$_pub" "$0" && got=1
    chk "does not attempt the publish it cannot do headless" "$got" \
        "would fail silently every morning -- T194's exact shape"

    # 3. THE ONE THAT MATTERS: the state file must record FAILURE, not just
    #    success. A detector that only ever writes ok is the log-file problem
    #    with extra steps -- it cannot distinguish "ran and everything passed"
    #    from "ran and everything broke".
    got=0; grep -q '"failures"' "$0" && grep -q '"ok"' "$0" && got=1
    chk "the state file records failures, not only that it ran" "$got" \
        "an always-ok detector detects nothing"

    # 4. It must not nag. T151: a calendar-gated job that notifies is exactly
    #    the accumulating-recurring-work the user's rule forbids.
    # NEEDLE ASSEMBLED FROM PARTS, and the first version was not -- it wrote the
    # pattern literally, matched ITS OWN LINE, and failed on a compliant script.
    # That is the fifth self-referential control in this codebase and it was
    # caught here by the control failing, one line after a comment explaining
    # the technique for control 2. Writing the rule down is not the same as
    # applying it.
    _n1="noti""fy-send"; _n2="cu""rl -X POST"; _n3="ma""il -s"
    got=0; ! grep -qE "($_n1|$_n2|$_n3)" "$0" && got=1
    chk "sends no notification (T151: calendar-gated must not nag)" "$got" \
        "would bill the user for days they were not here"

    # 5. --dry-run must change nothing. Asserted by running it and checking the
    #    state file's mtime is untouched.
    before=$(stat -c %Y "$STATE" 2>/dev/null || echo none)
    "$0" --dry-run >/dev/null 2>&1
    after=$(stat -c %Y "$STATE" 2>/dev/null || echo none)
    got=0; [[ "$before" == "$after" ]] && got=1
    chk "--dry-run writes nothing" "$got" "dry run modified $STATE"

    echo; echo "$((n-fails))/$n controls pass"
    [[ $fails -eq 0 ]] || exit 1
    exit 0
fi

say() { [[ "$DRY" == "1" ]] && echo "would: $*" || echo "[morning] $*"; }
FAILED=""
run_step() {                       # run_step <name> <command...>
    local name="$1"; shift
    if [[ "$DRY" == "1" ]]; then echo "would run: $name ($*)"; return 0; fi
    if "$@" >/dev/null 2>&1; then echo "[morning] ok   $name"
    else echo "[morning] FAIL $name"; FAILED="$FAILED $name"; fi
}

say "preparing $TODAY"

# 1. The daily audit. Cheap, mine to run, and due every day by design.
run_step "L2-audit" python3 scripts/audit_l2.py

# 2. Today's evidence directory, so nothing writes to /tmp by accident (T47).
if [[ "$DRY" == "1" ]]; then echo "would mkdir: $EVID"; else mkdir -p "$EVID"; fi

# 3. Regenerate the status page HTML. NOT published -- see the header. Having it
#    already built means the session only fetches, merges and publishes.
run_step "status-page-regen" python3 scripts/status_page.py "$ROOT/docs/.status-fresh.html"

# 4. Anything still running from overnight? Reported, never killed: a long job
#    left deliberately alive is normal here, and a cron that killed one would
#    destroy hours of work. Counted by comm-prefix -- `pgrep -f` self-matches
#    and `pgrep -x` cannot match this 23-char binary against comm's 15-char cap.
GAME=$(ps -eo comm= | grep -c '^SinPunishmentRe' || true)
XVFB=$(ps -eo comm= | grep -c '^Xvfb' || true)

# 5. What is owed, read from the project's own files rather than restated here.
# `grep -c` PRINTS ITS ZERO AND THEN EXITS 1, so `|| echo 0` appends a SECOND
# line and the value becomes "0\n0" -- which produced malformed JSON on this
# script's first real run and a bash arithmetic error. Caught by its own
# detector saying "morning state unreadable" rather than by reading the output,
# which is the whole argument for the detector not being a log line. `|| true`
# is the correct idiom: it swallows the exit status and keeps the printed zero.
OWED=$(python3 scripts/check_ledger.py --quiet 2>&1 | grep -c '^\[ledger\] note' || true)
OBS=$(grep -c "^## \(DEFERRED \)\?$TODAY" docs/observed-runs.md 2>/dev/null || true)
OWED=${OWED:-0}; OBS=${OBS:-0}

if [[ "$DRY" == "1" ]]; then
    echo "would write: $STATE and $REPORT"
    exit 0
fi

OK=true; [[ -z "$FAILED" ]] || OK=false
cat > "$STATE" <<EOF
{"last_date": "$TODAY", "ok": $OK, "failures": "${FAILED# }",
 "game_procs": $GAME, "xvfb_procs": $XVFB, "observed_today": $OBS,
 "notes": $OWED, "generated": "$(date +%Y-%m-%dT%H:%M:%S%:z)"}
EOF

cat > "$REPORT" <<EOF
# Morning state — $TODAY

Written by \`scripts/morning.sh\` at $(date +%H:%M) by cron. Machine-side only:
nothing here ran the game, cleared a gate, or published anything.

- daily audit: $([[ "$FAILED" == *L2* ]] && echo "**FAILED**" || echo "done")
- status page HTML: rebuilt at \`docs/.status-fresh.html\` (**not published** —
  that needs an interactive session; fetch clicks first, then publish)
- still running from overnight: $GAME game process(es), $XVFB Xvfb
- observed run recorded today: $([[ "$OBS" -gt 0 ]] && echo "yes" || echo "**no — this is the one thing that needs you**")
- open reminders from the ledger check: $OWED
${FAILED:+
**STEPS THAT FAILED:**$FAILED
}
## What still needs a person

The observed run. Nobody here can hear audio, and scene identity has been wrong
twice from sampling — that is the whole reason the gate exists. Everything else
above was done while you were asleep.
EOF

echo "[morning] wrote $REPORT"
[[ -z "$FAILED" ]] || echo "[morning] FAILURES:$FAILED"
exit 0
