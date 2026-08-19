#!/usr/bin/env bash
# Commit and push the day's work to the `fork` remote. Safe to run repeatedly;
# does nothing if nothing changed.
#
# WHY THIS IS AN ALLOW-LIST
# -------------------------
# The standing rule on this project is "nothing proprietary in commits, review
# the real diff every time". An unattended `git add -A` cannot honour that: one
# stray ROM copy, one session handoff, and it is public and in the history
# forever. So this stages ONLY known-safe paths by name. Anything new lands
# outside the allow-list and is simply not committed until someone adds it
# deliberately -- the failure mode is "forgot to publish", never "published a
# ROM".
#
# Three refusals, all of which have a real incident behind them:
#   * scratch debug hooks left in sinpunishment.toml (committed once already)
#   * a ledger that fails its own structural checks
#   * any staged path matching a proprietary/local pattern (belt and braces)
#
# Usage: scripts/daily_push.sh [--dry-run]
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

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

say() { printf '[daily-push] %s\n' "$*"; }
die() { printf '[daily-push] REFUSING: %s\n' "$*" >&2; exit 1; }

# --- refusal 1: scratch hooks must be stripped -------------------------------
if [[ -f sinpunishment.toml ]]; then
    n=$(sed -n '/BEGIN SCRATCH DEBUG HOOKS/,/END SCRATCH DEBUG HOOKS/p' sinpunishment.toml | wc -l)
    if [[ "$n" -gt 2 ]]; then
        die "sinpunishment.toml still has scratch debug hooks ($((n - 2)) lines). Run scripts/strip_scratch_hooks.sh"
    fi
fi

# --- refusal 2: ledger must pass its structural checks -----------------------
if [[ -x scripts/check_ledger.py ]]; then
    if ! python3 scripts/check_ledger.py --strict > /tmp/.ledger_check 2>&1; then
        cat /tmp/.ledger_check >&2
        die "ledger check failed (see above). Fix the entries, not the checker."
    fi
fi

# --- stage the allow-list ----------------------------------------------------
ALLOW=(
    README.md .gitignore CMakeLists.txt
    docs scripts patches symbols src include .claude
    sinpunishment.toml
)
for p in "${ALLOW[@]}"; do
    [[ -e "$p" ]] && git add -- "$p" 2>/dev/null
done

# --- refusal 3: nothing proprietary or local may be staged -------------------
BAD=$(git diff --cached --name-only | grep -Ei '\.(z64|n64|v64|rom|bin)$|^rom/|HANDOFF-|boot-debugging-|route-state' || true)
[[ -n "$BAD" ]] && die "proprietary/local paths staged:"$'\n'"$BAD"

if git diff --cached --quiet; then
    say "nothing to commit — tree already matches HEAD."
    exit 0
fi

say "staged changes:"
git diff --cached --stat | sed 's/^/    /'

if [[ "$DRY" -eq 1 ]]; then
    say "--dry-run: not committing."
    git reset -q
    exit 0
fi

DATE=$(date +%Y-%m-%d)
FILES=$(git diff --cached --name-only | wc -l)
git commit -q -m "Daily sync ${DATE}: ${FILES} file(s)

Automated by scripts/daily_push.sh (allow-list staging; session handoffs and
the raw journal are excluded by design).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" || die "commit failed"

say "committed $(git rev-parse --short HEAD)"

# BatchMode so a passphrase prompt fails fast instead of hanging a cron job
if GIT_SSH_COMMAND="ssh -o BatchMode=yes" git push -q fork HEAD:main; then
    say "pushed to fork/main"
else
    say "PUSH FAILED (commit is safe locally). If run from cron, the SSH key"
    say "probably needs an agent or a passphrase-free deploy key."
    exit 1
fi
