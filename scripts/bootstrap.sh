#!/usr/bin/env bash
# Bootstrap the Sin & Punishment Recompiled toolchain (macOS / Linux).
# Installs system deps, initializes submodules and builds the N64Recomp tools.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> [1/4] System dependencies"
if [[ "$(uname)" == "Darwin" ]]; then
    brew install cmake ninja sdl2
    # RT64 builds Metal shaders at compile time: the 'metal' compiler ships with
    # Xcode.app (Command Line Tools alone is NOT enough).
    if ! xcrun --find metal >/dev/null 2>&1; then
        echo "ERROR: 'metal' compiler not found. Install full Xcode:" >&2
        echo "  sudo xcode-select --install   # CLT only - NOT enough" >&2
        echo "  # Use the App Store (search 'Xcode') or https://developer.apple.com/download/all/" >&2
        echo "  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
        echo "  xcodebuild -runFirstLaunch" >&2
        exit 1
    fi
elif [[ -f /etc/debian_version ]]; then
    sudo apt-get install -y cmake ninja-build libsdl2-dev libgtk-3-dev lld llvm clang
else
    echo "Unsupported OS — install cmake, ninja, SDL2 manually." >&2
fi

echo "==> [2/4] Submodules"
git submodule update --init --recursive

# Sin & Punishment's custom audio ucode polls SP_STATUS for the SIG0 flag
# before proceeding; upstream RSPRecomp hardcodes that read as always 0
# (real hardware/coprocessor state isn't tracked statically), which leaves
# the recompiled polling loop unable to ever observe the signal. Not a TOML
# option -- it's a literal value in RSPRecomp's own source, so it's patched
# here rather than configured. See scripts/recompile.sh's sanity check for
# "r8 = 128;" in the generated rsp/audio.cpp.
if ! grep -q "return 0x80;" external/N64Recomp/RSPRecomp/src/rsp_recomp.cpp; then
    echo "==> Patching RSPRecomp (SIG0 hack, patches/upstream/N64Recomp-rsp-sig0-fix.patch)"
    git -C external/N64Recomp apply "$ROOT/patches/upstream/N64Recomp-rsp-sig0-fix.patch"
fi

# Startup race: is_game_started() flips true the instant the game is launched
# (SP_AUTOSTART or the launcher's "start" button), before the game's own MIPS
# code has run far enough to call osViSetMode -- and once it's true, the VI
# thread's set_dummy_vi() fallback stops populating a mode, leaving
# ViState::mode null with no default initializer. Without this guard,
# update_vi() dereferences it and crashes on startup.
if ! grep -q "next_mode == nullptr" lib/N64ModernRuntime/ultramodern/src/events.cpp; then
    echo "==> Patching N64ModernRuntime (VI null-mode startup race, patches/upstream/N64ModernRuntime-vi-null-mode-fix.patch)"
    git -C lib/N64ModernRuntime apply "$ROOT/patches/upstream/N64ModernRuntime-vi-null-mode-fix.patch"
fi

echo "==> [3/4] Building N64Recomp + RSPRecomp"
cmake -S external/N64Recomp -B build-n64recomp -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-n64recomp --parallel

echo "==> [4/4] Installing tools at repo root (expected by recompile.sh and CMake)"
cp build-n64recomp/N64Recomp ./N64Recomp
cp build-n64recomp/RSPRecomp ./RSPRecomp

echo "Done. Next: ./scripts/recompile.sh  (needs symbols/ from Phase 1)"
