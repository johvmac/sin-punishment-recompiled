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
wired=0
for f in gdb_fault.sh gdb_trace.sh run_game.sh; do
    grep -q 'snp_warn_if_stale' "$ROOT/scripts/$f" 2>/dev/null && wired=$((wired+1))
done
chk "all three runners call it (a check nobody invokes is decoration)" \
    "$([[ "$wired" -eq 3 ]] && echo 1 || echo 0)" "only $wired/3 runners wired"

echo
echo "$((n-fails))/$n controls pass"
[[ $fails -eq 0 ]] || exit 1
exit 0
