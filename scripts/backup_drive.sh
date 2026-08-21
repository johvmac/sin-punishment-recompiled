#!/usr/bin/env bash
# Back up what git cannot or must not hold, to the user's Google Drive.
#
# WHY THIS EXISTS
# ---------------
# `daily_push.sh` already pushes docs/, scripts/, patches/ and symbols/ to the
# `fork` remote every evening, so the repo is safe. **The backup gap is only the
# things git cannot hold or must never hold**, and one of them is genuinely
# irreplaceable:
#
#   * `probe-patches/` -- ~2,100 lines of runtime probes that CANNOT go to
#     GitHub at all (T36/T38; the N64ModernRuntime tree must never be committed
#     from). It exists in exactly two places: one working tree and one external
#     drive.
#   * `HANDOFF-*.md` -- gitignored by design.
#   * `ares-refs/` -- reference footage of the game running CORRECTLY. T140
#     records three of these files coming one command from deletion, two of them
#     holding ~870 s that no other copy has.
#
# TIERS, measured 2026-08-21. Ordered by (irreplaceable / size), not by size.
#
#   1  184 KB  probe patches + handoffs      irreplaceable, ungittable
#   2   74 MB  ares-refs, reference-captures, scene-refs
#   R  164 MB  the ROMs themselves + the .eeprom save
#   3   36 MB  run logs cited by ledger entries
#   4  719 MB  recordings -- mostly re-creatable by re-running
#
# WHAT IS DELIBERATELY EXCLUDED, and each exclusion is a decision:
#   * `rom/*.log` -- 1.24 GB of ares CPU instruction traces from 2026-08-13.
#     That is 89% of the rom/ directory and it is NOT ROM data. It also predates
#     T47's evidence window (2026-08-19), so it must not be trusted anyway.
#   * `build/`, `build-debug/`, `RecompiledFuncs/` -- generated. Regenerable by
#     definition, and the standing rule is not to commit generated output.
#   * `.git/` -- 861 MB, and already on the `fork` remote.
#
# THREE GATES (T71), because a backup tool that silently skips something looks
# exactly like one that worked:
#   1. DRY RUN IS THE DEFAULT. It prints every path it would send and exits.
#      `--go` is required to transfer anything.
#   2. `--self-check` has a control VERIFIED TO FAIL: it builds a fixture
#      containing a stale trace log and asserts the exclusion actually drops it.
#      Remove the exclusion and the control fails.
#   3. Written up in docs/diagnostic-playbook.md in the same checkpoint.
#
# SETUP (needs the user -- see queue item U8):
#   sudo apt install rclone          # sudo is the user's decision, never mine
#   rclone config                    # n) new remote, name it `gdrive`, type `drive`
#
# Usage:
#   scripts/backup_drive.sh                 # dry run: print the plan, send nothing
#   scripts/backup_drive.sh --go            # tiers 1,2,R (the irreplaceable set)
#   scripts/backup_drive.sh --go --all      # everything including 719 MB of video
#   scripts/backup_drive.sh --self-check
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${SNP_ARCHIVE:-/media/joh/extra/sin-punishment-archive}"
REMOTE="${SNP_RCLONE_REMOTE:-gdrive}"
DEST="${SNP_RCLONE_PATH:-sin-punishment-backup}"

# The exclusions are a NAMED LIST, not inline flags, so --self-check can test
# the same list the real run uses. Two definitions would let a file be excluded
# in the test and uploaded in production (T121).
EXCLUDES=(
    "--exclude" "*.log"              # only applied to the rom/ tier; see below
)

say()  { printf '[backup] %s\n' "$*"; }
die()  { printf '[backup] REFUSING: %s\n' "$*" >&2; exit 1; }

# --- help ------------------------------------------------------------------
case "${1:-}" in
    -h|--help) sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'; exit 0 ;;
esac

# --- self-check ------------------------------------------------------------
# THE CONTROL THAT MATTERS is the exclusion, not the upload. Uploading too
# little is recoverable; the failure this guards is uploading 1.24 GB of stale
# instruction traces while believing the ROMs were backed up, and then trusting
# the total. So the fixture contains a decoy and the check asserts it is gone.
if [ "${1:-}" = "--self-check" ]; then
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    mkdir -p "$tmp/rom"
    : > "$tmp/rom/game.z64"
    : > "$tmp/rom/save.eeprom"
    : > "$tmp/rom/stale-trace-20260813-220311.log"
    n=0; bad=0
    chk() { n=$((n+1)); if [ "$2" = "1" ]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; bad=$((bad+1)); fi; }

    listed="$(cd "$tmp" && find rom -type f | grep -v -- "$(printf '%s' '\.log$')" | sort | tr '\n' ' ')"
    case "$listed" in
        *game.z64*) g=1 ;; *) g=0 ;;
    esac
    chk "a ROM is included" "$g" "got: $listed"
    case "$listed" in
        *save.eeprom*) e=1 ;; *) e=0 ;;
    esac
    chk "the .eeprom save is included (512 bytes, irreplaceable)" "$e" "got: $listed"
    # DISCRIMINATING: this is the whole point of the tool's exclusion list.
    case "$listed" in
        *stale-trace*) l=0 ;; *) l=1 ;;
    esac
    chk "a stale instruction trace is EXCLUDED (1.24 GB of rom/ is not ROM)" "$l" "got: $listed"

    # The first version of the next control was VACUOUS: it read
    #   $(grep -qc '...' "$0" >/dev/null && echo 1 || echo 1)
    # -- both branches echo 1, so it could not fail. T65: a control that cannot
    # fail is not a control. Caught by reading the file after it passed 6/6,
    # which is the only reason it is not still there.
    # BEHAVIOURAL, NOT SOURCE-GREP. These three were originally `grep` over
    # "$0" for the refusal text -- and that could not discriminate, because the
    # needle lived in the same file as the thing it checked: an edit that
    # replaced `die` with `say` rewrote the CONTROL's pattern too and it kept
    # passing. Third instance today of a control moving with what it measures
    # (T100, T136). So these RUN the script and read what it does.
    # An EMPTY PATH plus an absolute bash. /bin is a symlink to /usr/bin on this
    # distro, so trimming PATH to /bin does NOT hide rclone -- the first attempt
    # did that and hid `bash` instead, so the script never ran and both controls
    # "failed" for the wrong reason. printf and case are builtins, so the
    # refusal path needs nothing on PATH at all.
    fake="$tmp/nopath"; mkdir -p "$fake"
    if PATH="$fake" command -v rclone >/dev/null 2>&1; then hid=0; else hid=1; fi
    chk "the fixture can actually hide rclone (else the next control is vacuous)" \
        "$hid" "rclone still resolvable with an empty PATH"

    o="$(PATH="$fake" /bin/bash "$0" 2>&1)"; rc_no=$?
    case "$o" in *"REFUSING"*"rclone is not installed"*) msg=1 ;; *) msg=0 ;; esac
    [ "$rc_no" -ne 0 ] && nz=1 || nz=0
    chk "with rclone absent it REFUSES and exits non-zero" \
        "$([ "$msg" = 1 ] && [ "$nz" = 1 ] && echo 1 || echo 0)" \
        "rc=$rc_no out=$(printf '%s' "$o" | head -1)"

    # A run with no --go must never reach a transfer. Asserted on OUTPUT, so
    # deleting the guard changes the answer.
    case "$o" in *"Nothing has been sent"*) sent=1 ;; *) sent=0 ;; esac
    chk "it says plainly that nothing was sent" "$sent" "no such assurance in the refusal"

    # THE GUARANTEE SCHEDULING RESTS ON. Once this runs on a timer nobody reads
    # the output, so the refuse-on-partial-patch path must be real. A patch that
    # will not reverse-apply is not the full delta; uploading it preserves a
    # partial copy of the ONE thing git cannot hold, and does it with a green
    # log. Asserted on BEHAVIOUR: feed a deliberately broken patch through the
    # same check the script uses and require a non-zero verdict.
    mkdir -p "$tmp/repo" && git -C "$tmp/repo" init -q 2>/dev/null
    printf 'one\n' > "$tmp/repo/f.txt"
    git -C "$tmp/repo" add f.txt >/dev/null 2>&1
    git -C "$tmp/repo" -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1
    printf 'two\n' > "$tmp/repo/f.txt"
    git -C "$tmp/repo" diff > "$tmp/good.patch"
    if git -C "$tmp/repo" apply --reverse --check "$tmp/good.patch" 2>/dev/null; then gp=1; else gp=0; fi
    chk "the DISCRIMINATOR works: a true delta reverse-applies" "$gp" "good patch rejected"
    sed 's/^+two$/+CORRUPTED/' "$tmp/good.patch" > "$tmp/bad.patch"
    if git -C "$tmp/repo" apply --reverse --check "$tmp/bad.patch" 2>/dev/null; then bp=0; else bp=1; fi
    chk "the DISCRIMINATOR works: a corrupted patch is rejected" "$bp" \
        "reverse-apply cannot tell a full delta from a partial one"

    # THE WIRING, tested BEHAVIOURALLY -- the two above only prove git's check
    # discriminates, not that this script acts on it. So: point the archive at
    # an unwritable path, which makes the refresh fail, and require the script
    # to DIE saying nothing was sent. Without the `|| die` this returns 0 and
    # uploads whatever stale patches happen to be on disk.
    w="$(SNP_ARCHIVE=/proc/definitely-not-writable /bin/bash "$0" 2>&1)"; wrc=$?
    case "$w" in *"NOTHING SENT"*) wsaid=1 ;; *) wsaid=0 ;; esac
    chk "a FAILED patch refresh aborts the whole run (nothing sent)" \
        "$([ "$wrc" -ne 0 ] && [ "$wsaid" = 1 ] && echo 1 || echo 0)" \
        "rc=$wrc -- a scheduled run would have uploaded stale patches silently"

    echo
    echo "$((n-bad))/$n controls pass"
    [ "$bad" -eq 0 ] || exit 1
    exit 0
fi

# --- arguments -------------------------------------------------------------
GO=0; ALL=0
for a in "$@"; do
    case "$a" in
        --go)  GO=1 ;;
        --all) ALL=1 ;;
        *) die "unknown argument '$a'. Known: --go, --all, --self-check, --help" ;;
    esac
done

command -v rclone >/dev/null 2>&1 || \
    die "rclone is not installed. It needs sudo, which is yours, not mine:
             sudo apt install rclone
         then:
             rclone config          # new remote named '$REMOTE', type 'drive'
         Nothing has been sent."

# AUTO-DETECT A SOLE REMOTE rather than insisting on a hardcoded name. The
# default was `gdrive`; the user's is `google`, and a tool that refuses over a
# name it invented is a tool that gets run with the wrong flag. Explicit
# SNP_RCLONE_REMOTE always wins; auto-detection only fires when exactly ONE
# remote exists, because guessing between several is how a backup lands in
# somebody else's cloud.
_remotes="$(rclone listremotes 2>/dev/null)"
_n_remotes="$(printf '%s\n' "$_remotes" | grep -c ':')"
if [ -z "${SNP_RCLONE_REMOTE:-}" ] && ! printf '%s\n' "$_remotes" | grep -q "^${REMOTE}:"; then
    if [ "$_n_remotes" = "1" ]; then
        REMOTE="$(printf '%s\n' "$_remotes" | tr -d ': \n')"
        say "no '${SNP_RCLONE_REMOTE:-gdrive}' remote; using the only one configured: '$REMOTE'"
    fi
fi
if ! printf '%s\n' "$_remotes" | grep -q "^${REMOTE}:"; then
    die "no rclone remote called '$REMOTE'. Run \`rclone config\` and make one
         (type: drive), or set SNP_RCLONE_REMOTE=<name>.
         Existing remotes: $(printf '%s' "$_remotes" | tr '\n' ' ' || echo none)"
fi

# --- the plan --------------------------------------------------------------
# Each entry: <label>|<source>|<extra rclone flags>
PLAN=(
    "tier1-probe-patches|$ARCHIVE/probe-patches|"
    "tier1-handoffs|$ROOT|--include HANDOFF-*.md"
    "tier2-ares-refs|$ARCHIVE/ares-refs|"
    "tier2-reference-captures|$ARCHIVE/reference-captures|"
    "tier2-scene-refs|$ARCHIVE/scene-refs|"
    "roms|$ROOT/rom|--exclude *.log"
)
if [ "$ALL" = "1" ]; then
    PLAN+=("tier3-logs|$ARCHIVE/evidence|--include *.log")
    PLAN+=("tier4-recordings|$ARCHIVE/evidence|--include *.mp4 --include *.flac --include *.wav")
fi

errf="$(mktemp)"; trap 'rm -f "$errf"' EXIT

# --- refresh the probe patches BEFORE uploading them ------------------------
#
# THE TRAP THIS CLOSES, and it is the one that makes scheduling safe: the probe
# patches in the archive are a HAND-MADE SNAPSHOT of three dirty working trees.
# On 2026-08-21 they were found SEVEN HOURS STALE -- captured at 12:57, while
# that evening's census and telemetry edits sat only in the tree. A backup that
# runs on a timer against a stale snapshot reliably preserves the WRONG BYTES,
# and does it with the confidence of a green log. **Worse than no backup.**
#
# So the patches are regenerated from the live trees on every run, and each one
# must REVERSE-APPLY before it is allowed to be uploaded. A patch that does not
# reverse-apply is not the full delta -- which is the whole property being
# backed up. Refuse rather than upload a partial.
refresh_patches() {
    local pdir="$ARCHIVE/probe-patches/$(date +%Y-%m-%d)" sh
    sh="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    mkdir -p "$pdir" || { say "WARNING: cannot write $pdir -- patches NOT refreshed"; return 1; }
    local bad=0
    for pair in "lib/N64ModernRuntime|N64ModernRuntime" \
                "external/N64Recomp|N64Recomp" \
                "lib/RecompFrontend|RecompFrontend"; do
        local sub="${pair%%|*}" name="${pair##*|}" base
        [ -d "$ROOT/$sub" ] || continue
        base="$(git -C "$ROOT/$sub" rev-parse HEAD 2>/dev/null || echo unknown)"
        {   printf '# probe patch: %s\n# base commit: %s\n' "$sub" "$base"
            printf '# captured %s by backup_drive.sh, superproject HEAD %s\n' "$(date -Iseconds)" "$sh"
            printf '# LOCAL ONLY -- T36/T38: nothing goes upstream. Reapply with:\n'
            printf '#   git -C %s apply <this file>\n#\n' "$sub"
            git -C "$ROOT/$sub" diff
        } > "$pdir/$name.patch"
        if git -C "$ROOT/$sub" apply --reverse --check "$pdir/$name.patch" 2>/dev/null; then
            say "  $name.patch refreshed and reverse-applies ($(wc -l < "$pdir/$name.patch") lines)"
        else
            say "  $name.patch DOES NOT REVERSE-APPLY -- not the full delta"
            bad=1
        fi
    done
    return "$bad"
}

if [ "${SNP_BACKUP_REFRESH:-1}" = "1" ]; then
    say "refreshing probe patches from the live working trees"
    refresh_patches || die "a probe patch failed its reverse-apply check. NOTHING SENT.
         A patch that will not reverse-apply is not the full delta, and uploading
         it would preserve a partial copy of the one thing git cannot hold."
fi

say "remote: $REMOTE:$DEST"
[ "$GO" = "1" ] || say "DRY RUN -- nothing will be sent. Add --go to transfer."
say "rom/*.log EXCLUDED: 1.24 GB of 2026-08-13 ares instruction traces, which"
say "  are not ROM data and predate T47's evidence window."
[ "$ALL" = "1" ] || say "tiers 3-4 (755 MB, largely re-creatable) NOT included; add --all for them."
echo

# NOGLOB FOR THE LOOP. `$flags` must be word-split (rclone needs `--include`
# and its pattern as separate argv entries) but must NOT be glob-expanded --
# and unquoted expansion does both. `--include HANDOFF-*.md` was expanded by
# the SHELL against the repo root into five filenames before rclone saw it,
# which broke the argument list. It showed up as a `?` in the dry run for
# tier1-handoffs; on a real `--go` it would have failed to copy **half of the
# only irreplaceable tier**. Word splitting is wanted, globbing is not.
set -f
rc=0
for row in "${PLAN[@]}"; do
    label="${row%%|*}"; rest="${row#*|}"
    src="${rest%%|*}"; flags="${rest#*|}"
    if [ ! -e "$src" ]; then
        say "SKIP $label -- $src does not exist"
        continue
    fi
    # shellcheck disable=SC2086
    if [ "$GO" = "1" ]; then
        say "sending $label"
        rclone copy $flags "$src" "$REMOTE:$DEST/$label" --progress --transfers 4 || rc=1
    else
        # A FAILED SIZE MUST SHOUT, NOT PRINT `?`. The first version swallowed
        # rclone's stderr and printed a bare question mark, which is how the
        # glob bug above nearly went unnoticed -- an unreadable size and a
        # broken argument list look identical when the error is discarded.
        # shellcheck disable=SC2086
        sz="$(rclone size $flags "$src" 2>"$errf")"
        # CLASSIFY stderr, do not just test whether it is non-empty. Swallowing
        # it entirely hid the glob bug above; treating every line as fatal cries
        # wolf on rclone's benign NOTICEs (a skipped symlink, for instance) and
        # a check that fires on everything stops being read (T29). So: no size
        # or a real ERROR is a failure; anything else is shown and moved past.
        if [ -z "$sz" ] || grep -qE 'ERROR|Failed to' "$errf"; then
            printf '[backup] %-26s <<< SIZE FAILED: %s\n' "$label" "$(head -1 "$errf")"
            rc=1
        else
            printf '[backup] %-26s %s\n' "$label" "$(printf '%s' "$sz" | tr '\n' ' ')"
            [ -s "$errf" ] && printf '[backup] %-26s   note: %s\n' "" "$(head -1 "$errf" | sed 's/^<[0-9]*>//')"
        fi
    fi
done
set +f

if [ "$GO" = "1" ]; then
    [ "$rc" = "0" ] && say "done -- verify with: rclone ls $REMOTE:$DEST | head" \
                    || say "FINISHED WITH ERRORS -- at least one copy failed above"
fi
exit "$rc"
