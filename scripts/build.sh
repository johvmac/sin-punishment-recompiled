#!/usr/bin/env bash
# The only way to build. Snapshots what it is about to destroy, lints the
# probes before spending the cycle, then builds.
#
# Usage:
#   scripts/build.sh              # lint, snapshot, recompile + build
#   scripts/build.sh --no-recomp  # skip recompile.sh (C++-only changes)
#   scripts/build.sh --label NAME # name the build this run PRODUCES
#
# Every run snapshots the OUTGOING binary as `AUTO-<stamp>` (see 2 below).
# `--label NAME` additionally snapshots the binary this run BUILDS, as
# `NAME-<stamp>`, after the build succeeds. So a labelled run leaves two
# snapshots and the label always names the NEW one.
#
# To label a build after the fact -- the milestone flow, where the user has to
# watch it work before it can be called good -- re-run with the label and no
# source changes; the build no-ops and the label lands on that same binary:
#   SNP_USER_CONFIRMED=1 scripts/build.sh --no-recomp --label MILESTONE-xyz
#
# WHY THIS EXISTS
# ---------------
# Two failures, both from the same root: a discipline that lived in a document
# and depended on remembering it at the moment of maximum haste.
#
# 1. SNAPSHOTS (T25, 2026-08-18). The playbook said to cache a build "whenever a
#    new verified-stable milestone is reached". Milestones are rare and need the
#    user to confirm on screen; the builds actually worth comparing against are
#    the ordinary ones. So when an early gfx stall appeared (A86), the question
#    "is it the build or the environment?" was unanswerable -- every healthy
#    binary from that day had been overwritten by the next `cmake --build`. The
#    older cached binary was no substitute: it predated the heartbeat probe and
#    carried no comparable liveness signal.
#    => Snapshotting is no longer a decision. It happens on every build, and it
#       captures the INSTRUMENT SET alongside the binary, because a cached build
#       without matching probes cannot serve as the control it was kept for.
#
# 2. PROBE DEFECTS (I1, I4, I5, I7, I8, I13). Five instrument defects were text
#    patterns visible in the hook body, each caught only after a ~3 minute
#    recompile, a build and a run -- twice after a wrong conclusion had already
#    been written down.
#    => scripts/lint_hooks.py runs FIRST, so those cost seconds instead.
#
# The general rule this encodes: every discipline left to memory on this project
# has failed at least once; every one wired into a script has held.
set -uo pipefail

# --- help (T37) ------------------------------------------------------------
# Prints this script's own header block. Added after `route.py --help` was
# silently ignored and fell through to a state-mutating default.
case "${1:-}" in
    -h|--help)
        sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'
        exit 0 ;;
esac

cd "$(dirname "$0")/.." || exit 1
KGB=known_good_builds
BIN=build/SinPunishmentRecompiled
KEEP=10                      # rolling snapshots; MILESTONE-labelled are exempt

RECOMP=1
LABEL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-recomp) RECOMP=0; shift ;;
        --label)
            # A bare `--label` used to consume the next arg blindly; with set -u
            # an absent value aborts with an unhelpful "unbound variable".
            if [[ $# -lt 2 || "$2" == --* ]]; then
                echo "[build] --label needs a NAME (e.g. --label VI-REPRO-reverted)" >&2
                exit 2
            fi
            LABEL="$2"; shift 2 ;;
        # This used to be `*) shift ;;` -- unknown arguments were silently
        # dropped. That is the same defect class as T37 in route.py: a typo like
        # `--lable X` would build and snapshot with NO label and say nothing,
        # and `--no-recomp-typo` would silently do a FULL recompile. A build is
        # expensive and mutates known_good_builds/; it must not proceed on input
        # it did not understand.
        -h|--help)   ;;   # handled above, before any work
        *)
            echo "[build] unknown argument: $1" >&2
            echo "[build] known: --no-recomp, --label NAME, --help" >&2
            echo "[build] REFUSING to build on input I did not understand." >&2
            exit 2 ;;
    esac
done

# --- 0. milestone guard ----------------------------------------------------
# Standing rule: a milestone / known-good / "best build" is never declared
# alone -- the user confirms it on screen first. That rule lived only in prose,
# so this makes the label itself require the confirmation.
if [[ "$LABEL" == *MILESTONE* && -z "${SNP_USER_CONFIRMED:-}" ]]; then
    echo "[build] REFUSING to label a build MILESTONE without user confirmation." >&2
    echo "[build]   A milestone means the user watched it work. Ask them, then re-run" >&2
    echo "[build]   with SNP_USER_CONFIRMED=1 once they have confirmed on screen." >&2
    exit 1
fi

# --- 1. lint the probes BEFORE spending a build ----------------------------
echo "==> linting scratch hooks"
scripts/lint_hooks.py || true

# --- 2. snapshot what is about to be overwritten ---------------------------
# The binary being replaced is the one that becomes unrecoverable. Capturing it
# after the build would capture the wrong thing.
#
# But note what that means for NAMING (I16, 2026-08-19): this snapshot holds the
# OUTGOING binary, so a label passed on the command line must NOT land on it.
# It did, once: `--label VI-REPRO-reverted` was passed to the build that
# *produced* the reverted binary, and archived the PATCHED one under that name
# -- a snapshot whose label stated the exact opposite of its contents, which is
# worse than no snapshot because it reads as usable. Proven by hash, not by
# reading: the "reverted" snapshot was byte-identical to the patched build.
# => The pre-build snapshot is ALWAYS `AUTO`. `--label` is applied in step 4,
#    to the binary this run actually produces.
# The archive lives on a second drive via a symlink (the root fs runs ~92% full
# and snapshots are ~24MB each). If that drive is not mounted the symlink
# dangles -- and a snapshot that silently does not happen is precisely the
# failure this script exists to prevent (T25). So: fail loudly, never quietly.
if [[ -L "$KGB" && ! -d "$KGB/" ]]; then
    echo "[build] ERROR: $KGB is a dangling symlink -- the snapshot drive is not mounted." >&2
    echo "[build]   target: $(readlink "$KGB")" >&2
    echo "[build]   Mount it, or snapshots are silently lost. Refusing to build." >&2
    exit 1
fi

# snapshot <name> <role>
#   role=outgoing -- the binary this run is about to REPLACE
#   role=built    -- the binary this run has just PRODUCED
# The role goes in the manifest and the index, so a snapshot can never again be
# ambiguous about which side of a build it came from.
snapshot() {
    local NAME="$1" ROLE="$2"
    local PROBES TAGS HOOKS DRIFT
    mkdir -p "$KGB"
    cp "$BIN"                          "$KGB/SinPunishmentRecompiled-$NAME"
    cp sinpunishment.toml              "$KGB/sinpunishment-$NAME.toml"
    cp symbols/sinpunishment.syms.toml "$KGB/syms-$NAME.toml"

    # The manifest is what makes a snapshot usable as a control: which probes
    # were compiled in, and what state the tree was in.
    PROBES=$(strings "$BIN" 2>/dev/null | grep -oE "^SNP_[A-Z_]+" | sort -u | tr '\n' ' ')
    TAGS=$(strings "$BIN" 2>/dev/null | grep -oE "^\[[a-z]{2,4}\] " | sort -u | tr -d '[] \n')
    HOOKS=$(awk '/BEGIN SCRATCH/,/END SCRATCH/' sinpunishment.toml | grep -c "patches.hook")

    # The .toml and .syms copied here are the CURRENT tree state. For an
    # `outgoing` snapshot they can POSTDATE the binary -- edit symbols, then
    # build, and the old binary gets archived beside the new syms that did not
    # build it. That is the same "label disagrees with contents" trap as I16,
    # one level down, so measure it rather than hope. (A `built` snapshot is
    # taken after the build, so its sidecars always match.)
    DRIFT=""
    if [[ "$ROLE" == "outgoing" ]]; then
        DRIFT=$(find sinpunishment.toml symbols -newer "$BIN" -type f 2>/dev/null | head -3 | tr '\n' ' ')
    fi
    {
        echo "name:      $NAME"
        echo "role:      $ROLE"
        echo "contents:  the binary this build $([[ "$ROLE" == outgoing ]] && echo REPLACED || echo PRODUCED)"
        echo "date:      $(date -Iseconds)"
        echo "git:       $(git rev-parse --short HEAD 2>/dev/null)"
        echo "scratch:   $HOOKS hook(s)"
        echo "env_probes: $PROBES"
        echo "log_tags:  $TAGS"
        echo "sha256:    $(sha256sum "$BIN" 2>/dev/null | cut -d' ' -f1)"
        if [[ -n "$DRIFT" ]]; then
            echo "SIDECAR_DRIFT: $DRIFT"
            echo "  ^ these postdate the binary -- the .toml/.syms archived here are NOT what built it"
        fi
    } > "$KGB/manifest-$NAME.txt"

    if [[ ! -f "$KGB/INDEX.tsv" ]]; then
        printf 'name\trole\tdate\tgit\tscratch_hooks\tlog_tags\n' > "$KGB/INDEX.tsv"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$NAME" "$ROLE" "$(date -Iseconds)" \
        "$(git rev-parse --short HEAD 2>/dev/null)" "$HOOKS" "$TAGS" >> "$KGB/INDEX.tsv"
    echo "==> snapshot: $NAME  [$ROLE — the binary this build $([[ "$ROLE" == outgoing ]] && echo REPLACED || echo PRODUCED)]  ($HOOKS scratch hook(s), tags: ${TAGS:-none})"
    [[ -n "$DRIFT" ]] && echo "==>   NOTE: .toml/.syms postdate this binary and are not what built it: $DRIFT"

    # Prune AUTO snapshots only -- anything labelled is kept deliberately.
    local f base
    mapfile -t OLD < <(ls -1t "$KGB"/SinPunishmentRecompiled-AUTO-* 2>/dev/null | tail -n +$((KEEP + 1)))
    for f in "${OLD[@]:-}"; do
        [[ -z "$f" ]] && continue
        base=${f#"$KGB"/SinPunishmentRecompiled-}
        rm -f "$KGB/SinPunishmentRecompiled-$base" "$KGB/sinpunishment-$base.toml" \
              "$KGB/syms-$base.toml" "$KGB/manifest-$base.txt"
        echo "==> pruned old snapshot $base"
    done
}

if [[ -f "$BIN" ]]; then
    snapshot "AUTO-$(date +%Y-%m-%d-%H%M%S)" outgoing
fi

# --- 3. build --------------------------------------------------------------
if [[ "$RECOMP" == "1" ]]; then
    echo "==> recompile.sh"
    if ! timeout 900 scripts/recompile.sh > /tmp/recomp.$$.log 2>&1; then
        echo "[build] recompile FAILED — tail:" >&2
        tail -15 /tmp/recomp.$$.log >&2
        rm -f /tmp/recomp.$$.log
        exit 1
    fi
    rm -f /tmp/recomp.$$.log
fi

echo "==> cmake --build"
# T226 (opened by A631, fixed 2026-08-28). This used to read:
#     if ! timeout 1800 cmake --build build ... 2>&1 | grep -E "..."; then : ; fi
# which threw cmake's exit status away TWICE. The pipeline reported grep's
# status rather than cmake's, and the `if ! ...; then :; fi` then swallowed
# even that. A build that failed to compile and link fell straight through to
# the `-x $BIN` test below -- which PASSED, because the STALE binary from the
# previous build was still sitting there and still executable. The script
# printed "==> built <time>" and returned 0.
#
# Why that mattered more here than in most projects: every measurement on this
# project runs build/SinPunishmentRecompiled. A silent build failure means the
# next run measures the PREVIOUS binary while the log says the change was
# applied -- a confidently wrong answer produced by the one tool standing
# between every code change and every number we take.
#
# The log is written to a file rather than piped, so the filter below cannot
# drop anything we then fail to read (T163): on failure the whole log is KEPT
# and its path printed, and the tail is shown without being the only copy.
BUILD_LOG=/tmp/snpbuild.$$.log
timeout 1800 cmake --build build -j"$(nproc)" > "$BUILD_LOG" 2>&1
BUILD_RC=$?
grep -E "error|Linking CXX executable" "$BUILD_LOG" || true
if [[ $BUILD_RC -ne 0 ]]; then
    echo "[build] ERROR: cmake --build FAILED (rc=$BUILD_RC)." >&2
    echo "[build]   $BIN on disk is STALE -- it is the PREVIOUS build, not this one." >&2
    echo "[build]   DO NOT RUN OR MEASURE IT. Full log kept at: $BUILD_LOG" >&2
    echo "[build] --- last 30 lines of the build log ---" >&2
    tail -30 "$BUILD_LOG" >&2
    exit 1
fi
rm -f "$BUILD_LOG"

if [[ -x "$BIN" ]]; then
    echo "==> built $(date +%H:%M:%S)"
else
    echo "[build] ERROR: $BIN missing after build" >&2
    exit 1
fi

# --- 4. label the binary this run PRODUCED (I16) ---------------------------
# Only after a successful build, so a label can never name a binary that does
# not exist or a build that failed halfway.
if [[ -n "$LABEL" ]]; then
    snapshot "$LABEL-$(date +%Y-%m-%d-%H%M%S)" built
fi
