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

echo "Done. Generated: RecompiledFuncs/ and rsp/*.cpp"
