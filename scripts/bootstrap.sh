#!/usr/bin/env bash
# Bootstrap the Sin & Punishment Recompiled toolchain (macOS / Linux).
# Installs system deps, initializes submodules and builds the N64Recomp tools.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> [1/4] System dependencies"
if [[ "$(uname)" == "Darwin" ]]; then
    brew install cmake ninja sdl2
elif [[ -f /etc/debian_version ]]; then
    sudo apt-get install -y cmake ninja-build libsdl2-dev libgtk-3-dev lld llvm clang
else
    echo "Unsupported OS — install cmake, ninja, SDL2 manually." >&2
fi

echo "==> [2/4] Submodules"
git submodule update --init --recursive

echo "==> [3/4] Building N64Recomp + RSPRecomp"
cmake -S external/N64Recomp -B build-n64recomp -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-n64recomp --parallel

echo "==> [4/4] Installing tools at repo root (expected by recompile.sh and CMake)"
cp build-n64recomp/N64Recomp ./N64Recomp
cp build-n64recomp/RSPRecomp ./RSPRecomp

echo "Done. Next: ./scripts/recompile.sh  (needs symbols/ from Phase 1)"
