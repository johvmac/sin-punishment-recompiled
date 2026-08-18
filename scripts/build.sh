#!/usr/bin/env bash
# The only way to build. Snapshots what it is about to destroy, lints the
# probes before spending the cycle, then builds.
#
# Usage:
#   scripts/build.sh              # lint, snapshot, recompile + build
#   scripts/build.sh --no-recomp  # skip recompile.sh (C++-only changes)
#   scripts/build.sh --label NAME # name this snapshot (e.g. MILESTONE-xyz)
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

cd "$(dirname "$0")/.." || exit 1
KGB=known_good_builds
BIN=build/SinPunishmentRecompiled
KEEP=10                      # rolling snapshots; MILESTONE-labelled are exempt

RECOMP=1
LABEL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-recomp) RECOMP=0; shift ;;
        --label)     LABEL="$2"; shift 2 ;;
        *)           shift ;;
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

if [[ -f "$BIN" ]]; then
    mkdir -p "$KGB"
    STAMP=$(date +%Y-%m-%d-%H%M%S)
    NAME="${LABEL:-AUTO}-$STAMP"
    cp "$BIN"                        "$KGB/SinPunishmentRecompiled-$NAME"
    cp sinpunishment.toml            "$KGB/sinpunishment-$NAME.toml"
    cp symbols/sinpunishment.syms.toml "$KGB/syms-$NAME.toml"

    # The manifest is what makes a snapshot usable as a control: which probes
    # were compiled in, and what state the tree was in.
    PROBES=$(strings "$BIN" 2>/dev/null | grep -oE "^SNP_[A-Z_]+" | sort -u | tr '\n' ' ')
    TAGS=$(strings "$BIN" 2>/dev/null | grep -oE "^\[[a-z]{2,4}\] " | sort -u | tr -d '[] \n')
    HOOKS=$(awk '/BEGIN SCRATCH/,/END SCRATCH/' sinpunishment.toml | grep -c "patches.hook")
    {
        echo "name:      $NAME"
        echo "date:      $(date -Iseconds)"
        echo "git:       $(git rev-parse --short HEAD 2>/dev/null)"
        echo "scratch:   $HOOKS hook(s)"
        echo "env_probes: $PROBES"
        echo "log_tags:  $TAGS"
    } > "$KGB/manifest-$NAME.txt"

    if [[ ! -f "$KGB/INDEX.tsv" ]]; then
        printf 'name\tdate\tgit\tscratch_hooks\tlog_tags\n' > "$KGB/INDEX.tsv"
    fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$NAME" "$(date -Iseconds)" \
        "$(git rev-parse --short HEAD 2>/dev/null)" "$HOOKS" "$TAGS" >> "$KGB/INDEX.tsv"
    echo "==> snapshot: $NAME  ($HOOKS scratch hook(s), tags: ${TAGS:-none})"

    # Prune AUTO snapshots only -- anything labelled is kept deliberately.
    mapfile -t OLD < <(ls -1t "$KGB"/SinPunishmentRecompiled-AUTO-* 2>/dev/null | tail -n +$((KEEP + 1)))
    for f in "${OLD[@]:-}"; do
        [[ -z "$f" ]] && continue
        base=${f#"$KGB"/SinPunishmentRecompiled-}
        rm -f "$KGB/SinPunishmentRecompiled-$base" "$KGB/sinpunishment-$base.toml" \
              "$KGB/syms-$base.toml" "$KGB/manifest-$base.txt"
        echo "==> pruned old snapshot $base"
    done
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
if ! timeout 1800 cmake --build build -j"$(nproc)" 2>&1 | grep -E "error|Linking CXX executable"; then
    :
fi

if [[ -x "$BIN" ]]; then
    echo "==> built $(date +%H:%M:%S)"
else
    echo "[build] ERROR: $BIN missing after build" >&2
    exit 1
fi
