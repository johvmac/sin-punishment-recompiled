#!/usr/bin/env bash
# Snapshot everything needed to REPRODUCE or A/B a build, before anything eats it.
#
# WHY THIS EXISTS (T115)
# ---------------------
# On 2026-08-20 a symbol fix was applied, `RecompiledFuncs/` was regenerated, and
# both binaries were rebuilt. Then the crash signature changed -- and the
# question "is A99 fixed, or merely masked by a new fault?" could not be
# answered, because:
#
#   * `RecompiledFuncs/` is UNTRACKED (generated, 137 files, 47 MB). Regenerating
#     it destroys the previous tree with no git baseline to diff or restore.
#   * the previous binaries were overwritten in place.
#   * no build snapshots existed on the archive despite the handoff claiming two.
#
# **The pre-change state was unrecoverable, so no A/B was possible.** That is
# T47's lesson (evidence must survive the session) applied to build state rather
# than to logs.
#
# WHAT IT CAPTURES, and why each piece
# ------------------------------------
#   RecompiledFuncs/     the ONLY irreplaceable piece -- untracked, and the
#                        product of a generator PLUS five repair passes (T114)
#                        that are easy to run partially
#   symbols/, *.toml     the inputs that produced it; without these the tree
#                        cannot be regenerated even in principle
#   both binaries        so an A/B needs no rebuild
#   MANIFEST             hashes, git HEAD, dirty state, and the REASON
#
# The generated tree compresses ~9x (47 MB -> ~5 MB), so cost is not a reason to
# skip it. Binaries dominate; --no-binaries drops them when only the sources
# matter.
#
# Usage:
#   scripts/snapshot_build.sh "<reason>"        # snapshot everything
#   scripts/snapshot_build.sh --no-binaries "<reason>"
#   scripts/snapshot_build.sh --list
#   scripts/snapshot_build.sh --dry-run "<reason>"
#   scripts/snapshot_build.sh --self-check
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="${SNP_ARCHIVE:-/media/joh/extra/sin-punishment-archive}"
SNAPDIR="$ARCHIVE/builds"

usage() { sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'; }

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    --list)
        if [[ -d "$SNAPDIR" ]]; then
            for d in "$SNAPDIR"/*/; do
                [[ -d "$d" ]] || continue
                printf "  %-34s %8s  %s\n" "$(basename "$d")" \
                    "$(du -sh "$d" 2>/dev/null | cut -f1)" \
                    "$(sed -n 's/^reason: //p' "$d/MANIFEST" 2>/dev/null | head -1)"
            done
        else
            echo "  no snapshots yet ($SNAPDIR)"
        fi
        exit 0 ;;
    --self-check)
        fails=0; n=0
        chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }

        # 1/2. NEEDLES ASSEMBLED, AND MATCHED AGAINST THE `tar` COMMAND, not
        #    against any mention. The first version grepped for the bare word,
        #    which appears in the CONTROL'S OWN LINE -- so renaming the captured
        #    directory throughout left the control passing. **Sixth instance of a
        #    control matching its own text** (T100), and the second where it
        #    produced a FALSE PASS rather than a false failure. Matching the
        #    actual command also means a control that only *documents* the
        #    capture cannot satisfy it.
        _rf="tar -cf - -C \"\$ROOT\" Recompiled""Funcs"
        _in="tar -cf - -C \"\$ROOT\" symbols sinpunishment"".toml"
        got=0; grep -qF "$_rf" "$0" && got=1
        chk "the tar command captures the untracked generated tree" "$got" \
            "no tar of the generated tree -- an A/B would be impossible"
        got=0; grep -qF "$_in" "$0" && got=1
        chk "the tar command captures the inputs that produced it" "$got" \
            "inputs not tarred -- the tree could never be regenerated"

        # 3. T47: it must refuse when the archive is absent, never fall back.
        out=$(SNP_ARCHIVE=/proc/nonexistent/x "$0" "self-check refusal probe" 2>&1)
        got=0; [[ "$?" != "0" || "$out" == *REFUS* ]] && got=1
        chk "REFUSES when the archive is unavailable (T47)" "$got" "would write somewhere else"

        # 4. A reason is MANDATORY. An unlabelled snapshot is a directory nobody
        #    can interpret six weeks later -- the same failure as a bare --defer
        #    (T103).
        #
        #    PROBED AGAINST A THROWAWAY ARCHIVE, not the real one. The first
        #    version invoked "$0" directly, so when the reason-guard was broken
        #    to VERIFY the control, the probe sailed past it and wrote a real
        #    94 MB snapshot with an empty reason into the archive. **A
        #    self-check must not be able to mutate the thing it checks** -- the
        #    test for a destructive guard has to run somewhere disposable.
        _probe=$(mktemp -d)
        SNP_ARCHIVE="$_probe" "$0" >/dev/null 2>&1; rc=$?
        rm -rf "$_probe"
        chk "refuses a snapshot with no REASON" "$([[ $rc -eq 2 ]] && echo 1 || echo 0)" "rc=$rc, want 2"

        echo; echo "$((n-fails))/$n controls pass"
        [[ $fails -eq 0 ]] || exit 1
        exit 0 ;;
esac

NOBIN=0
if [[ "${1:-}" == "--no-binaries" ]]; then NOBIN=1; shift; fi
DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi

REASON="${1:-}"
if [[ -z "$REASON" ]]; then
    echo "[snap] a REASON is required: scripts/snapshot_build.sh 'why this state matters'" >&2
    echo "[snap] REFUSING — an unlabelled snapshot is a directory nobody can read later." >&2
    exit 2
fi

if ! mkdir -p "$SNAPDIR" 2>/dev/null; then
    echo "[snap] REFUSING: cannot write $SNAPDIR — the archive is not mounted." >&2
    echo "[snap] Build state must survive the session (T47/T115); /tmp does not." >&2
    exit 1
fi

STAMP="$(date +%Y-%m-%d-%H%M%S)"
SLUG="$(printf '%s' "$REASON" | tr -c 'A-Za-z0-9' '-' | tr -s '-' | cut -c1-40 | sed 's/-$//')"
DEST="$SNAPDIR/$STAMP-$SLUG"

if [[ "$DRY" == "1" ]]; then
    echo "=== DRY RUN — nothing written ==="
    echo "would create : $DEST"
    echo "would capture: RecompiledFuncs/ (tar.zst), symbols/, sinpunishment.toml, rsp/*.toml"
    [[ "$NOBIN" == "0" ]] && echo "               build/ and build-debug/ binaries (zst)" \
                          || echo "               (binaries SKIPPED: --no-binaries)"
    echo "               MANIFEST with hashes, git HEAD and the reason"
    exit 0
fi

mkdir -p "$DEST"
tar -cf - -C "$ROOT" RecompiledFuncs 2>/dev/null | zstd -3 -q -o "$DEST/RecompiledFuncs.tar.zst"
tar -cf - -C "$ROOT" symbols sinpunishment.toml 2>/dev/null | zstd -3 -q -o "$DEST/inputs.tar.zst"
[[ -d "$ROOT/rsp" ]] && tar -cf - -C "$ROOT" rsp 2>/dev/null | zstd -3 -q -o "$DEST/rsp.tar.zst"

{
    echo "snapshot: $STAMP"
    echo "reason: $REASON"
    echo "git-head: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    echo "git-dirty: $(git -C "$ROOT" status --porcelain 2>/dev/null | grep -vc '^ m' || echo '?') tracked change(s)"
    echo "recompiledfuncs-files: $(ls "$ROOT"/RecompiledFuncs/*.c 2>/dev/null | wc -l)"
    for b in build build-debug; do
        f="$ROOT/$b/SinPunishmentRecompiled"
        [[ -f "$f" ]] && echo "$b-sha256-16: $(sha256sum "$f" | cut -c1-16)"
    done
    echo "syms-sha256-16: $(sha256sum "$ROOT/symbols/sinpunishment.syms.toml" 2>/dev/null | cut -c1-16)"
    echo "toml-sha256-16: $(sha256sum "$ROOT/sinpunishment.toml" 2>/dev/null | cut -c1-16)"
} > "$DEST/MANIFEST"

if [[ "$NOBIN" == "0" ]]; then
    for b in build build-debug; do
        f="$ROOT/$b/SinPunishmentRecompiled"
        [[ -f "$f" ]] && zstd -3 -q -o "$DEST/$b-SinPunishmentRecompiled.zst" "$f"
    done
fi

echo "[snap] $DEST"
echo "[snap] $(du -sh "$DEST" | cut -f1) — $(sed -n 's/^reason: //p' "$DEST/MANIFEST")"
sed -n 's/^\(build\|build-debug\)-sha256-16: /  binary /p' "$DEST/MANIFEST"
exit 0
