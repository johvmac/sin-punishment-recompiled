# shellcheck shell=bash
# Sourceable: warn when a binary is older than the sources it was built from.
#
#   . "$(dirname "$0")/build_staleness.sh"
#   snp_warn_if_stale "build-debug/SinPunishmentRecompiled"
#
# Self-test: scripts/test_staleness.sh
#
# WHY THIS EXISTS (T125)
# ----------------------
# On 2026-08-20 a one-line change went into `ultramodern/src/events.cpp` and was
# built with `scripts/build.sh --no-recomp`, which builds the RELEASE tree only.
# `build/` then carried the change and `build-debug/` did not -- and BOTH
# debuggers, `gdb_fault.sh` and `gdb_trace.sh`, default to `build-debug`.
# Nothing said anything. **Two binaries silently differing in source is how you
# spend an afternoon debugging last week's code.**
#
# WHY NOT JUST BUILD BOTH EVERY TIME
# ----------------------------------
# The debug binary is ~247 MB with full symbols and costs minutes. Paying that
# on every build -- including the many that only feed a 25-second smoke test --
# is a permanent tax to prevent an occasional mistake, and taxes like that get
# worked around. Someone adds a --fast flag and the trap comes straight back.
#
# So the check lives where the staleness MATTERS: at the moment a binary is
# about to be run, not at the moment one is built.
#
# THE TEST IS THRESHOLD-FREE, WHICH IS THE POINT
# ----------------------------------------------
# It does NOT compare the two binaries to each other -- "how much drift between
# them is acceptable" is a judgement nobody can defend. It asks whether THIS
# binary is older than any source it was built from, which is a fact. That also
# catches the mirror case (rebuild debug, leave release stale) that a
# compare-the-pair rule would not notice at all.
#
# IT WARNS, IT DOES NOT REFUSE, and that is deliberate. Running an older binary
# on purpose is a legitimate and frequent act here -- every A/B against a build
# snapshot is exactly that. A refusal would block the comparisons this project
# most depends on, and a rule that discards the runs you most need has already
# been recorded once (A220). Set SNP_STALE=0 to silence it entirely.

snp_warn_if_stale() {
    local bin="${1:-}"
    [ "${SNP_STALE:-1}" = "0" ] && return 0
    [ -n "$bin" ] && [ -f "$bin" ] || return 0

    local root
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

    # -quit on the first hit: this answers "is ANY source newer", so it stops
    # at the first one rather than walking 137 generated files plus the runtime.
    local newer
    newer=$(find "$root/src" "$root/lib" "$root/RecompiledFuncs" \
                 -type f \( -name '*.c' -o -name '*.cpp' -o -name '*.h' \
                            -o -name '*.hpp' \) \
                 -newer "$bin" -print -quit 2>/dev/null)

    [ -n "$newer" ] || return 0

    echo "[stale] WARNING: $bin is OLDER than at least one source it was built from." >&2
    echo "[stale]   newer: ${newer#$root/}" >&2
    echo "[stale] You may be about to debug code that is not what you just changed." >&2
    echo "[stale] scripts/build.sh --no-recomp builds the RELEASE tree ONLY;" >&2
    echo "[stale] refresh the debug tree with: ninja -C build-debug" >&2
    echo "[stale] (Deliberate? An A/B against an older build is legitimate --" >&2
    echo "[stale]  SNP_STALE=0 silences this.)" >&2
    return 0
}
