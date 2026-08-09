#!/bin/sh
# Shader tool wrapper (dxc / spirv-cross) for macOS arm64.
#
# WHY: the repo directory contains '&' (sin&punishmentrecomp). CMake's Ninja
# generator emits commands via /bin/sh; an env-assignment prefix like
# `DYLD_LIBRARY_PATH=/path/sin&punishmentrecomp/...` is split by the shell at
# the '&' (or, if quoted, treated as a program name), so the rule fails with
# code 127. Resolving the tool and its lib path from this script's own
# location keeps the command line free of env assignments.
#
# Usage: snp-shader-tool.sh dxc <dxc args...>
#        snp-shader-tool.sh spirv-cross <spirv-cross args...>
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$1"
shift

case "$TOOL" in
    dxc)
        export DYLD_LIBRARY_PATH="$ROOT/lib/rt64/src/contrib/dxc/lib/arm64"
        exec "$ROOT/lib/rt64/src/contrib/dxc/bin/arm64/dxc-macos" "$@"
        ;;
    spirv-cross)
        export DYLD_LIBRARY_PATH="$ROOT/lib/rt64/src/contrib/spirv-cross/lib/arm64"
        exec "$ROOT/lib/rt64/src/contrib/spirv-cross/bin/arm64/spirv-cross" "$@"
        ;;
    *)
        echo "snp-shader-tool.sh: unknown tool '$TOOL'" >&2
        exit 1
        ;;
esac
