#!/usr/bin/env bash
# Removes everything between the "BEGIN/END SCRATCH DEBUG HOOKS" markers in
# sinpunishment.toml, leaving the markers themselves in place. Run this
# before committing -- temporary debug [[patches.hook]] entries added during
# an investigation should never land in a real commit.
set -euo pipefail
cd "$(dirname "$0")/.."

TOML="sinpunishment.toml"
BEGIN="# ===== BEGIN SCRATCH DEBUG HOOKS ====="
END="# ===== END SCRATCH DEBUG HOOKS ====="

if ! grep -qF "$BEGIN" "$TOML" || ! grep -qF "$END" "$TOML"; then
    echo "ERROR: scratch-hooks markers not found in $TOML -- did they get edited/removed?" >&2
    exit 1
fi

python3 - "$TOML" "$BEGIN" "$END" << 'PYEOF'
import sys
path, begin, end = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    lines = f.readlines()

out = []
in_scratch = False
removed = 0
for line in lines:
    stripped = line.rstrip("\n")
    if stripped == begin:
        out.append(line)
        in_scratch = True
        continue
    if stripped == end:
        in_scratch = False
        out.append(line)
        continue
    if in_scratch:
        removed += 1
        continue
    out.append(line)

with open(path, "w") as f:
    f.writelines(out)

print(f"Stripped {removed} line(s) between the scratch-hooks markers.")
PYEOF
