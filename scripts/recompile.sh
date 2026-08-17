#!/usr/bin/env bash
# Recompile the game (main binary + RSP microcodes) into C/C++ sources.
# Requires: ./N64Recomp, ./RSPRecomp (scripts/bootstrap.sh) and symbols/ (Phase 1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Main binary (sinpunishment.toml)"
./N64Recomp sinpunishment.toml

echo "==> RSP microcodes"
for rsp_cfg in rsp/*.toml; do
    echo "  -- $rsp_cfg"
    ./RSPRecomp "$rsp_cfg"
done

# Remove dangling "goto after_N;" from tail-call functions that end at the jal
# (delay slot belongs to the next symbol; label never emitted -> compile error).
echo "==> Post-processing dangling gotos (tail-call delay slots)"
python3 scripts/fix_dangling_gotos.py

# Make SI-manager stubs return 0 (N64Recomp stubs are empty bodies).
echo "==> Post-processing SI stubs (return 0)"
python3 scripts/patch_si_stubs.py

# Generated funcs don't include <stdio.h>; any scratch fprintf/stderr debug
# hook fails to compile without this. Must run AFTER any pass that injects
# debug prints into the generated sources.
echo "==> Ensuring <stdio.h> in generated funcs that use it"
python3 scripts/ensure_stdio.py

# Strip malformed writes to $zero (cgenerator gap; always behavior-preserving
# to remove since $zero writes are architectural no-ops on real hardware).
echo "==> Post-processing zero-register writes"
python3 scripts/fix_zero_writes.py

# Safety net: the audio-ucode SIG0 hack must survive regeneration
# (expected_c0_reg_value(SP_STATUS) = 0x80 in RSPRecomp emits "r8 = 128;").
if ! grep -q "r8 = 128;" rsp/audio.cpp; then
    echo "ERROR: SIG0 hack missing in rsp/audio.cpp (expected 'r8 = 128;')" >&2
    exit 1
fi
echo "==> SIG0 hack present (r8 = 128 in rsp/audio.cpp)"

echo "Done. Generated: RecompiledFuncs/ and rsp/*.cpp"
