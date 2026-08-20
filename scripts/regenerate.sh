#!/usr/bin/env bash
# The ONLY correct way to regenerate RecompiledFuncs and rebuild.
#
# WHY THIS EXISTS (T116)
# ----------------------
# On 2026-08-20 a regeneration was done by hand and went wrong twice in one
# afternoon:
#
#   1. **The previous state was destroyed with no snapshot.** `RecompiledFuncs/`
#      is untracked and the binaries were overwritten in place, so when the
#      crash signature changed, "is it fixed or masked?" became unanswerable --
#      there was nothing to A/B against (T115).
#   2. **Only 2 of the 5 repair passes were run.** Two of them announce
#      themselves as COMPILE ERRORS; three are SILENT. The build linked, and the
#      binary rendered NOTHING -- gfx_tasks=1, stalled 179 s -- because
#      patch_si_stubs.py had not run (T114).
#
# **A pipeline where some steps fail loudly and others fail silently will always
# be run partially.** So it is one script, in order, with a snapshot first and a
# smoke test last -- because "it links" was exactly the check that passed on an
# inert binary.
#
# THE ORDER MATTERS
#   0. snapshot            <- BEFORE anything is destroyed. Not optional.
#   1. N64Recomp           regenerate from symbols + toml
#   2. fix_zero_writes     ) these two announce themselves as compile errors
#   3. fix_dangling_gotos  )
#   4. patch_si_stubs      <- SILENT. Without it the game never clears
#                             controller detection and renders nothing.
#   5. build + build-debug
#   6. SMOKE TEST          a short run that must report non-trivial gfx_tasks
#
# auto_stub_pass.py and auto_label_fix.py are NOT run here: they fix compile
# blockers by editing sinpunishment.toml, which is a decision, not a repair. If
# step 5 fails on an unhandled instruction or a missing label, run them by hand
# and look at what they changed.
#
# Usage:
#   scripts/regenerate.sh "<reason for this regeneration>"
#   scripts/regenerate.sh --dry-run "<reason>"
#   scripts/regenerate.sh --self-check
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

usage() { sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'; }

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    --self-check)
        fails=0; n=0
        chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }

        # THE SNAPSHOT MUST COME FIRST. Needles assembled and matched against the
        # actual invocations, not against mentions -- a control that greps its
        # own file for a bare word passes on a script that only TALKS about
        # snapshotting (T100, six instances).
        # STRUCTURAL FIX FOR A WHOLE BUG CLASS: grep the EXECUTABLE REGION only.
        #
        # Eight times in this codebase a control has matched its own text and
        # passed on a broken script (T100/T112, and three times while writing
        # THIS pair of tools). Assembling needles from parts fixes one control at
        # a time and is forgotten the next time. Excluding the self-check block
        # from what is searched fixes EVERY control in the file at once, and
        # cannot be forgotten because there is nothing to remember.
        #
        # `BODY` is everything after the `esac` that closes the argument case --
        # i.e. the code that actually runs. The dry-run echoes live before it too,
        # so this also stops a control matching documentation instead of code.
        BODY=$(awk 'f{print} /^esac$/{f=1}' "$0")

        # MATCH THE REAL INVOCATIONS, NOT THE DRY-RUN ECHOES. The first version
        # matched the dry-run block -- which lists every step in order as TEXT --
        # so it reported generate-before-snapshot on a correct script AND passed
        # when a repair pass was deleted. Seventh instance of a control matching
        # prose instead of code (T112). Each needle below appears only in the
        # executable line: `$ROOT/`-qualified, `python3 `-prefixed, or
        # redirect-suffixed.
        _snap='"$ROOT/scripts/snapshot_build.sh"'
        _gen="./N64""Recomp sinpunishment.toml >/dev/null"
        i_snap=$(printf '%s\n' "$BODY" | grep -nF "$_snap" | head -1 | cut -d: -f1)
        i_gen=$(printf  '%s\n' "$BODY" | grep -nF "$_gen"  | head -1 | cut -d: -f1)
        got=0; [[ -n "$i_snap" && -n "$i_gen" && "$i_snap" -lt "$i_gen" ]] && got=1
        chk "snapshots BEFORE regenerating (the state is destroyed after)" "$got" \
            "snapshot@${i_snap:-none}, generate@${i_gen:-none}"

        # ALL FIVE REPAIRS, and the silent one especially. Its absence produced a
        # binary that compiled, linked, ran to completion, and was inert.
        miss=""
        for r in fix_zero_writes fix_dangling_gotos patch_si_stubs; do
            printf '%s\n' "$BODY" | grep -qF "python3 scripts/$r.py" || miss="$miss $r"
        done
        chk "runs every repair pass, including the SILENT patch_si_stubs" \
            "$([[ -z "$miss" ]] && echo 1 || echo 0)" "missing:$miss"

        # A SMOKE TEST, because "it links" passed on an inert binary.
        got=0; printf '%s\n' "$BODY" | grep -q 'gfx_tasks' && \
               printf '%s\n' "$BODY" | grep -q 'SMOKE' && got=1
        chk "ends in a smoke test on gfx_tasks, not just a successful link" "$got" \
            "no behavioural post-condition"

        # A reason is mandatory -- it is what the snapshot gets labelled with.
        "$0" >/dev/null 2>&1; rc=$?
        chk "refuses with no REASON" "$([[ $rc -eq 2 ]] && echo 1 || echo 0)" "rc=$rc, want 2"

        echo; echo "$((n-fails))/$n controls pass"
        [[ $fails -eq 0 ]] || exit 1
        exit 0 ;;
esac

DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi
REASON="${1:-}"
if [[ -z "$REASON" ]]; then
    echo "[regen] a REASON is required — it labels the snapshot this takes first." >&2
    echo "[regen] REFUSING: scripts/regenerate.sh 'why you are regenerating'" >&2
    exit 2
fi

if [[ "$DRY" == "1" ]]; then
    echo "=== DRY RUN — nothing regenerated ==="
    echo " 0. snapshot_build.sh 'regenerate: $REASON'   <- BEFORE anything is destroyed"
    echo " 1. ./N64Recomp sinpunishment.toml"
    echo " 2. scripts/fix_zero_writes.py       (loud: 'lvalue required')"
    echo " 3. scripts/fix_dangling_gotos.py    (loud: 'label used but not defined')"
    echo " 4. scripts/patch_si_stubs.py        (SILENT — an inert binary without it)"
    echo " 5. ninja -C build && ninja -C build-debug"
    echo " 6. SMOKE: 25s run; gfx_tasks must exceed 100"
    exit 0
fi

echo "=== 0/6  SNAPSHOT (before anything is destroyed)"
"$ROOT/scripts/snapshot_build.sh" "regenerate: $REASON" || {
    echo "[regen] REFUSING to regenerate: the snapshot failed, so the current" >&2
    echo "[regen] state would be unrecoverable. That is exactly T115." >&2
    exit 1; }

echo "=== 1/6  N64Recomp"
./N64Recomp sinpunishment.toml >/dev/null 2>&1 || { echo "[regen] N64Recomp failed" >&2; exit 1; }

echo "=== 2/6  fix_zero_writes";      python3 scripts/fix_zero_writes.py     | tail -1
echo "=== 3/6  fix_dangling_gotos";   python3 scripts/fix_dangling_gotos.py  | tail -1
echo "=== 4/6  patch_si_stubs (the silent one)"; python3 scripts/patch_si_stubs.py | tail -1

echo "=== 5/6  build"
ninja -C build        >/dev/null 2>&1 || { echo "[regen] build FAILED — run auto_stub_pass.py / auto_label_fix.py by hand and look at what they change" >&2; exit 1; }
ninja -C build-debug  >/dev/null 2>&1 || { echo "[regen] build-debug FAILED" >&2; exit 1; }
for b in build build-debug; do
    echo "    $b $(sha256sum $b/SinPunishmentRecompiled | cut -c1-16)"
done

echo "=== 6/6  SMOKE TEST — 'it links' is not evidence that it runs"
SMOKELOG="${SNP_EVIDENCE_DIR:-/media/joh/extra/sin-punishment-archive/evidence/$(date +%Y-%m-%d)}/regen-smoke-$(date +%H%M%S).log"
scripts/run_game.sh 25 "$SMOKELOG" >/dev/null 2>&1
GFX=$(grep -oE 'gfx_tasks=[0-9]+' "$SMOKELOG" 2>/dev/null | tail -1 | cut -d= -f2)
GFX="${GFX:-0}"
if [[ "$GFX" -gt 100 ]]; then
    echo "    PASS: gfx_tasks=$GFX — the binary is rendering"
    exit 0
fi
echo "[regen] SMOKE TEST FAILED: gfx_tasks=$GFX after 25s." >&2
echo "[regen] The build LINKED and the game is INERT — this is T114's failure." >&2
echo "[regen] Suspect a repair pass that did not apply. Snapshot is in builds/." >&2
exit 1
