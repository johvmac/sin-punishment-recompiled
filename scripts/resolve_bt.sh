#!/usr/bin/env bash
# Resolve the raw addresses in [taskbt] lines to game function names.
#
# SNP_TASK_BT=1 prints raw return addresses rather than symbol names, because
# backtrace_symbols() resolves only dynamic symbols and this binary is linked
# without -rdynamic. Recompiled functions ARE global symbols in the static
# symbol table, so nm can name them; this maps each address to the nearest
# preceding symbol.
#
# Usage: scripts/resolve_bt.sh <logfile> [binary]
set -uo pipefail

LOG="${1:?usage: resolve_bt.sh <logfile> [binary]}"
BIN="${2:-./build/SinPunishmentRecompiled}"

cd "$(dirname "$0")/.." || exit 1

[[ -r "$LOG" ]] || { echo "[resolve_bt] ERROR: cannot read $LOG" >&2; exit 1; }
[[ -x "$BIN" ]] || { echo "[resolve_bt] ERROR: $BIN not found" >&2; exit 1; }

SYMS=$(mktemp)
trap 'rm -f "$SYMS"' EXIT
# Sorted "address name" table of every function symbol (T/t/W).
nm -n "$BIN" 2>/dev/null | awk '$2 ~ /^[TtWw]$/ { print $1, $3 }' > "$SYMS"

if [[ ! -s "$SYMS" ]]; then
    echo "[resolve_bt] ERROR: no symbols in $BIN (stripped?)" >&2
    exit 1
fi

python3 - "$LOG" "$SYMS" <<'PY'
import bisect, re, sys

log_path, syms_path = sys.argv[1], sys.argv[2]

addrs, names = [], []
with open(syms_path) as f:
    for line in f:
        a, n = line.split(None, 1)
        addrs.append(int(a, 16))
        names.append(n.strip())

def resolve(addr):
    i = bisect.bisect_right(addrs, addr) - 1
    if i < 0:
        return f"0x{addr:x} <?>"
    return f"{names[i]}+0x{addr - addrs[i]:x}"

# The binary is PIE: runtime addresses are slid. Derive the slide from the
# anchor line the probe prints (a known symbol's runtime address).
slide = 0
sym_index = {n: a for a, n in zip(addrs, names)}
for line in open(log_path):
    m = re.match(r"\[taskbt\] anchor (\w+)=(0x[0-9a-fA-F]+)", line)
    if m and m.group(1) in sym_index:
        slide = int(m.group(2), 16) - sym_index[m.group(1)]
        print(f"# load slide = 0x{slide:x} (from {m.group(1)})")
        break
else:
    print("# WARNING: no anchor line found -- addresses may resolve wrongly",
          file=sys.stderr)

for line in open(log_path):
    if not line.startswith("[taskbt]") or " anchor " in line:
        continue
    head, _, tail = line.partition(":")
    print(head + ":")
    for tok in re.findall(r"0x[0-9a-fA-F]+", tail):
        print("    " + resolve(int(tok, 16) - slide))
PY
