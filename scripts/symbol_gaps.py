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

    scripts/symbol_gaps.py                    # histogram + top candidates
    scripts/symbol_gaps.py --all              # every non-alignment candidate
    scripts/symbol_gaps.py --skip ovlfile12   # withhold a section (repeatable)

`--skip` exists because 13 of the top 20 are `.ovlfile12`, which T11's own plan
calls the wrong place to spend the budget (it does not load at runtime -- T11,
A127). The withheld COUNT is always printed, per T76: a quiet flag may hide a
candidate's content, never its existence. Reaching for `grep -v` here instead
is what CLAUDE.md forbids -- a missing flag on the script is the fix.
"""
import re
import sys
from collections import Counter
from pathlib import Path

KNOWN = {"--all", "--help", "-h", "--skip"}


def check_argv():
    """Arg validation, called from main() -- NOT at import time.

    It used to run at import, which made `import symbol_gaps` validate the
    IMPORTER's argv and reject its flags. gap_classify.py imports the parser
    from here (one copy, per T199/T200), so this has to be inert on import.
    """
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)
    skipvals = {sys.argv[i + 1] for i, a in enumerate(sys.argv)
                if a == "--skip" and i + 1 < len(sys.argv)}
    unknown = [a for a in sys.argv[1:]
               if a.startswith("-") and a not in KNOWN and a not in skipvals]
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


def parse_sections():
    """[(section_name, [(func_name, vram, size), ...]), ...] from the syms file.

    SHARED, DELIBERATELY. gap_classify.py imports this rather than carrying its
    own regexes -- a second parser is a copy that goes stale, which is exactly
    what T199/T200 cost when `gist()` was duplicated into status_page.py.
    """
    sections = []
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
    return sections


def find_gaps(sections):
    """-> (padding_sizes, candidates); candidate = (gap, sec, name, vram, size, next_vram)."""
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
    return padding, candidates


def main():
    if not SYMS.exists():
        print(f"[gaps] no {SYMS}", file=sys.stderr)
        return 1

    sections = parse_sections()
    total_funcs = sum(len(f) for _, f in sections)
    padding, candidates = find_gaps(sections)

    n_all = len(candidates)
    skip = set()
    for i, a in enumerate(sys.argv):
        if a == "--skip" and i + 1 < len(sys.argv):
            skip.add(sys.argv[i + 1].lstrip("."))
    if skip:
        candidates = [c for c in candidates if c[1].lstrip(".") not in skip]

    print(f"symbols parsed:        {total_funcs} across {len(sections)} sections")
    print(f"gaps total:            {len(padding) + n_all}")
    print(f"  alignment padding:   {len(padding)}   <- expected, needs no human")
    print(f"  REAL candidates:     {n_all}   <- the actual T11 triage list")
    if skip:
        # T76: --skip may hide a candidate's CONTENT, never its EXISTENCE.
        print(f"  withheld by --skip:  {n_all - len(candidates)}   "
              f"<- section(s) {' '.join(sorted(skip))}; {len(candidates)} shown below")

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
    check_argv()
    sys.exit(main())
