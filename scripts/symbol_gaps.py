#!/usr/bin/env python3
"""T11 triage aid: classify the unclaimed gaps between consecutive function symbols.

A "gap" is `vram + size < next_vram` within the same section -- bytes that no
symbol claims. Two very different things produce one:

  * ALIGNMENT PADDING. Functions are padded to a 16-byte boundary, so a gap of
    1..15 bytes that lands exactly on an alignment boundary is expected and
    means nothing. This is the overwhelming majority.
  * A TRUNCATED SYMBOL. The declared size is smaller than the real function, so
    the generated C stops early. This is the L1/L7 class (BC-2): `0x14` declared
    against a real `0x8C`, and `0x54` against a real `0x118`. Both were real
    bugs that cost days.

The point of this script is COSTING, not fixing. "296 gaps" is only a scary
number if they all need a human; if most are alignment noise, the triage list is
whatever remains. It prints a size histogram and the non-alignment candidates,
ranked, so T11 can be priced instead of guessed at.

Read-only: parses symbols/sinpunishment.syms.toml and prints. Changes nothing.

    scripts/symbol_gaps.py            # histogram + top candidates
    scripts/symbol_gaps.py --all      # every non-alignment candidate
"""
import re
import sys
from collections import Counter
from pathlib import Path

if "--help" in sys.argv or "-h" in sys.argv:
    print(__doc__)
    sys.exit(0)

KNOWN = {"--all", "--help", "-h"}
unknown = [a for a in sys.argv[1:] if a.startswith("-") and a not in KNOWN]
if unknown:
    print(f"[gaps] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
    print(f"[gaps] known: {', '.join(sorted(KNOWN))}", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SYMS = ROOT / "symbols" / "sinpunishment.syms.toml"

SECTION = re.compile(r'^\s*name\s*=\s*"([^"]+)"')
FUNC = re.compile(
    r'\{\s*name\s*=\s*"([^"]+)"\s*,\s*vram\s*=\s*(0x[0-9A-Fa-f]+)\s*,'
    r'\s*size\s*=\s*(0x[0-9A-Fa-f]+)\s*\}'
)

# Alignment: a gap is "expected padding" if the symbol's end is not on a 16-byte
# boundary and the gap is exactly what it takes to reach the next one.
ALIGN = 16


def main():
    if not SYMS.exists():
        print(f"[gaps] no {SYMS}", file=sys.stderr)
        return 1

    sections = []          # (section_name, [(name, vram, size), ...])
    cur_name, cur_funcs = "?", []
    for line in SYMS.read_text().splitlines():
        m = SECTION.match(line)
        if m:
            if cur_funcs:
                sections.append((cur_name, cur_funcs))
            cur_name, cur_funcs = m.group(1), []
            continue
        m = FUNC.search(line)
        if m:
            cur_funcs.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
    if cur_funcs:
        sections.append((cur_name, cur_funcs))

    total_funcs = sum(len(f) for _, f in sections)
    padding, candidates = [], []

    for sec, funcs in sections:
        funcs = sorted(funcs, key=lambda t: t[1])
        for (name, vram, size), (_, nxt_vram, _) in zip(funcs, funcs[1:]):
            end = vram + size
            gap = nxt_vram - end
            if gap <= 0:
                continue           # overlap or exact fit; a different defect class
            if gap < ALIGN and (end % ALIGN) != 0 and (end + gap) % ALIGN == 0:
                padding.append(gap)
            else:
                candidates.append((gap, sec, name, vram, size, nxt_vram))

    print(f"symbols parsed:        {total_funcs} across {len(sections)} sections")
    print(f"gaps total:            {len(padding) + len(candidates)}")
    print(f"  alignment padding:   {len(padding)}   <- expected, needs no human")
    print(f"  REAL candidates:     {len(candidates)}   <- the actual T11 triage list")

    if candidates:
        print("\ngap-size histogram (candidates only):")
        buckets = Counter()
        for gap, *_ in candidates:
            if gap < 0x10:
                buckets["<0x10"] += 1
            elif gap < 0x40:
                buckets["0x10-0x3F"] += 1
            elif gap < 0x100:
                buckets["0x40-0xFF"] += 1
            elif gap < 0x400:
                buckets["0x100-0x3FF"] += 1
            else:
                buckets[">=0x400"] += 1
        for k in ("<0x10", "0x10-0x3F", "0x40-0xFF", "0x100-0x3FF", ">=0x400"):
            if buckets[k]:
                print(f"  {k:>12}: {buckets[k]:4d}  {'#' * min(buckets[k], 60)}")

        show = sorted(candidates, reverse=True)
        if "--all" not in sys.argv:
            show = show[:20]
        print(f"\ntop {len(show)} by gap size "
              f"(check each against splat's endlabel before touching):")
        print(f"  {'gap':>7}  {'section':<10} {'symbol':<32} {'vram':>10} {'size':>7}")
        for gap, sec, name, vram, size, _ in show:
            print(f"  {gap:>#7x}  {sec:<10} {name:<32} {vram:>#10x} {size:>#7x}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
