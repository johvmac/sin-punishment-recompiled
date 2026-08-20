#!/usr/bin/env bash
# Controls for build_staleness.sh (T125).
#
# THE DISCRIMINATING PAIR is fires-on-stale AND silent-on-fresh. A check that
# only fired would be indistinguishable from one that fires always, and a
# warning that appears on every run is one nobody reads within a day (T29) --
# which is exactly how the probe window in events.cpp came to sit unused.
#
#   scripts/test_staleness.sh
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "${1:-}" in
    -h|--help) sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'; exit 0 ;;
esac

fails=0; n=0
chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }

# Probe against a THROWAWAY tree shaped like the repo, so the test can never
# depend on -- or disturb -- the real build state.
TD=$(mktemp -d)
trap 'rm -rf "$TD"' EXIT
mkdir -p "$TD/scripts" "$TD/src" "$TD/lib" "$TD/RecompiledFuncs" "$TD/build-debug"
cp "$ROOT/scripts/build_staleness.sh" "$TD/scripts/"

BIN="$TD/build-debug/SinPunishmentRecompiled"
SRC="$TD/src/thing.cpp"

probe() {  # $1 = extra env
    env $1 bash -c ". '$TD/scripts/build_staleness.sh'; snp_warn_if_stale '$BIN'" 2>&1
}

# --- FRESH: binary newer than every source -> silent -----------------------
echo 'int main(){}' > "$SRC"
sleep 0.05
: > "$BIN"
out=$(probe "")
chk "SILENT when the binary is newer than its sources" \
    "$([[ -z "$out" ]] && echo 1 || echo 0)" "warned on a fresh binary: $out"

# --- STALE: a source touched after the build -> warns -----------------------
sleep 0.05
: > "$SRC"
out=$(probe "")
chk "WARNS when a source is newer than the binary" \
    "$([[ "$out" == *"OLDER than"* ]] && echo 1 || echo 0)" "no warning on a stale binary"

chk "names the offending file, so it is actionable" \
    "$([[ "$out" == *"thing.cpp"* ]] && echo 1 || echo 0)" "warning does not say WHICH source"

chk "names the release-only build as the likely cause" \
    "$([[ "$out" == *"--no-recomp"* ]] && echo 1 || echo 0)" "does not point at the trap that caused it"

# --- it must be silenceable, because running an older binary is legitimate --
out=$(probe "SNP_STALE=0")
chk "SNP_STALE=0 silences it (an A/B against an old build is legitimate)" \
    "$([[ -z "$out" ]] && echo 1 || echo 0)" "cannot be silenced -- would block deliberate A/B runs"

# --- and it must never be the thing that breaks a run -----------------------
out=$(env bash -c ". '$TD/scripts/build_staleness.sh'; snp_warn_if_stale '/no/such/binary'; echo rc=\$?" 2>&1)
chk "returns 0 and stays quiet for a missing binary" \
    "$([[ "$out" == *"rc=0"* && "$out" != *"OLDER"* ]] && echo 1 || echo 0)" "would abort a caller"

out=$(env bash -c ". '$TD/scripts/build_staleness.sh'; snp_warn_if_stale ''; echo rc=\$?" 2>&1)
chk "returns 0 for an empty argument" \
    "$([[ "$out" == *"rc=0"* ]] && echo 1 || echo 0)" "would abort a caller"

# --- the runners must actually CALL it, or none of the above matters --------
#
# THE LIST WAS WRONG WHEN THIS WAS WRITTEN and the control could not tell:
# it asserted "all three" against a hardcoded three, so gdb_threads.sh -- a
# FOURTH runner that launches the binary under gdb -- was silently uncovered
# for a day. A control that counts a list it also defines cannot notice a
# missing member.
#
# So the list is now DISCOVERED, not declared: anything in scripts/ that
# launches the binary must call the check. Add a runner and this fails until
# it is wired, which is the whole point.
# Scripts that only COPY or ARCHIVE the binary cannot debug the wrong code, so
# they are exempt -- named individually, with the reason, so the exemption is
# auditable rather than a pattern that quietly grows.
exempt_copy_only="build.sh snapshot_build.sh"

unclassified=(); missing=()
for f in "$ROOT"/scripts/*.sh; do
    b="$(basename "$f")"
    grep -qE 'SinPunishmentRecompiled' "$f" 2>/dev/null || continue
    grep -q 'build_staleness.sh' "$f" 2>/dev/null && continue      # it IS the check
    case " $exempt_copy_only " in *" $b "*) continue ;; esac
    # Delegating to run_game.sh inherits its warning; no need to warn twice.
    grep -qE 'run_game\.sh|display_isolate' "$f" 2>/dev/null && continue
    grep -q 'snp_warn_if_stale' "$f" 2>/dev/null || missing+=("$b")
done
chk "every script that runs the binary or reads symbols from it calls the check" \
    "$([[ "${#missing[@]}" -eq 0 ]] && echo 1 || echo 0)" \
    "not wired: ${missing[*]:-none}"

echo
echo "$((n-fails))/$n controls pass"
[[ $fails -eq 0 ]] || exit 1
exit 0
