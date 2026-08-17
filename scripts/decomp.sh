#!/usr/bin/env bash
# Decompile one ROM function to readable C with m2c.
#
# Usage: scripts/decomp.sh <func_name_or_address> [more names...]
#   scripts/decomp.sh func_8002AA90
#   scripts/decomp.sh 8002AA90            # bare address, func_ prefix added
#   scripts/decomp.sh boot_func_8002AA90  # recomp naming, prefix stripped
#
# WHY: the recompiler's output in RecompiledFuncs/ is a literal instruction-by-
# instruction transliteration -- 60 lines of `ctx->r2 = SUB32(...)` for what is
# actually three subtractions. Reading it by hand is slow and, worse, easy to
# truncate: a hand-read of boot_func_8002AA90 on 2026-08-18 stopped early and
# missed an entire fourth list being rewound after the sort call. m2c emitted
# the whole function in six lines and did not miss it.
#
# Input is splat's per-function assembly, NOT the ROM -- so this needs no MIPS
# toolchain (there is none on this machine) and no ROM access. m2c parses the
# assembly as text.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

SPLAT="${SNP_SPLAT_DIR:-$(cd .. && pwd)/splat-project}"
M2C_DIR="${SNP_M2C_DIR:-$(cd .. && pwd)/tools/m2c}"
M2C_PY="${SNP_M2C_PYTHON:-$(cd .. && pwd)/tools/m2c-venv/bin/python3}"
TARGET="${SNP_M2C_TARGET:-mips-ido-c}"

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <func_name_or_address> [more...]" >&2
    exit 1
fi
for req in "$SPLAT/asm" "$M2C_DIR/m2c.py" "$M2C_PY"; do
    if [[ ! -e "$req" ]]; then
        echo "ERROR: missing $req" >&2
        echo "  splat asm: SNP_SPLAT_DIR   m2c: SNP_M2C_DIR   python: SNP_M2C_PYTHON" >&2
        exit 1
    fi
done

for raw in "$@"; do
    # Accept boot_func_X / ovlfileN_func_X / func_X / bare X. splat names
    # everything func_<ADDR>, so reduce to that.
    addr="${raw##*func_}"
    addr="${addr#0x}"
    addr="$(echo "$addr" | tr '[:lower:]' '[:upper:]')"
    fn="func_${addr}"

    # Locate the one .s holding it. Matching the label definition rather than
    # any mention, so a call site in another file doesn't win.
    src="$(grep -rlE "^[[:space:]]*(glabel|\.globl)[[:space:]]+${fn}\b|^${fn}:" "$SPLAT/asm" 2>/dev/null | head -1)"
    if [[ -z "$src" ]]; then
        src="$(grep -rl "\b${fn}\b" "$SPLAT/asm" 2>/dev/null | head -1)"
    fi
    if [[ -z "$src" ]]; then
        echo "=== ${fn}: NOT FOUND in $SPLAT/asm ===" >&2
        continue
    fi

    echo "=== ${fn}   (from $(basename "$src")) ==="
    "$M2C_PY" "$M2C_DIR/m2c.py" --target "$TARGET" -f "$fn" "$src" 2>&1
    echo
done
