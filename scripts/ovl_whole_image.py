#!/usr/bin/env python3
"""WHICH overlay is resident in an RDRAM snapshot? Whole-image, not a fingerprint.

WHY THIS EXISTS (A729, built as A746's execution of A739's NEXT)
---------------------------------------------------------------
All 27 `.ovlfileNN` sections load at the SAME vram, `0x800E4780`, so an address
there names a LOCATION, not a function. The existing instrument,
`a604-ovl-resident.py`, answers residency by matching **sixteen bytes** — four
instructions at one vram — and A729 caught it returning True for a window whose
first 7.4 KB were a different overlay entirely. A739 then measured the blast
radius: 73 ledger rows read an address in that window, and **every residency
verdict this project has ever recorded rests on those sixteen bytes.**

A729 named whole-image matching as the fix and the tool was never built. This is
it. It compares a section's ROM image against the snapshot at its own vram, word
by word, over the WHOLE image — and it reports the per-block map, so a window
holding two overlays stacked shows up as two overlays stacked instead of one
confident True.

THE BYTE CONVENTION IS MEASURED, NOT ASSUMED
--------------------------------------------
The ROM is big-endian z64; the snapshot's word order is a property of whatever
wrote it. Rather than hardcode a guess, `.boot` — which is present in EVERY
healthy snapshot at a known rom/vram pair — is compared under both conventions
and the tool REFUSES unless exactly one wins decisively. A tool that silently
picks a convention can report "not resident" for every overlay in the game and
look like a finding.

CONTROLS (T65 — verified to FAIL, not merely to pass)
-----------------------------------------------------
  C1 POSITIVE   `.boot` must match >=99% under the chosen convention. Ground
                truth: it is the same bytes in ROM and RAM in any healthy dump,
                and it is NOT in the overlay window, so it tests the ROM read,
                the snapshot read and the byte convention without touching the
                thing under test.
  C2 NEGATIVE   `.boot` compared at a deliberately WRONG offset (+0x100) must
                collapse to near zero. Fails if the comparison is broken open.
  C3 DISCRIMINATION  the overlay scores in one snapshot must not be all-equal;
                a matcher that cannot separate 27 candidates is not a matcher.

Usage:
  ovl_whole_image.py SNAPSHOT [--top N] [--map] [--dry-run]
  ovl_whole_image.py SNAPSHOT --self-check
"""
import re
import sys
from pathlib import Path

ROM = Path("rom/sinpunishment.z64")
SYMS = Path("symbols/sinpunishment.syms.toml")
KSEG0 = 0x80000000
WIN_LO, WIN_HI = 0x800E4780, 0x800E7F30


def sections():
    """[(name, rom, vram, size)] from the syms toml, in file order."""
    out, cur = [], {}
    for line in SYMS.read_text(errors="replace").split("\n"):
        s = line.strip()
        if s == "[[section]]":
            cur = {}
            continue
        m = re.match(r'(name|rom|vram|size)\s*=\s*(.+)', s)
        if not m or not isinstance(cur, dict):
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == "name":
            cur = {"name": v.strip('"')}
        else:
            try:
                cur[k] = int(v, 0)
            except ValueError:
                continue
        if all(x in cur for x in ("name", "rom", "vram", "size")):
            out.append((cur["name"], cur["rom"], cur["vram"], cur["size"]))
            cur = {}
    return out


def words(b):
    return [b[i:i + 4] for i in range(0, len(b) - 3, 4)]


def score(rom_b, snap_b, swap):
    """(matching words, total words, per-64-byte-block match flags)."""
    rw, sw = words(rom_b), words(snap_b)
    n = min(len(rw), len(sw))
    hits, blocks, cur = 0, [], [0, 0]
    for i in range(n):
        s = sw[i][::-1] if swap else sw[i]
        ok = rw[i] == s
        hits += ok
        cur[0] += ok
        cur[1] += 1
        if cur[1] == 16:
            blocks.append(cur[0] == 16)
            cur = [0, 0]
    if cur[1]:
        blocks.append(cur[0] == cur[1])
    return hits, n, blocks


def load(snap):
    return snap.read_bytes()


def compare(raw, rom, sec, swap, vram_shift=0):
    _n, r, v, sz = sec
    a = v - KSEG0 + vram_shift
    return score(rom[r:r + sz], raw[a:a + sz], swap)


def pick_convention(raw, rom, secs, verbose=True):
    """Measure the byte convention on .boot. Returns swap flag, or None."""
    boot = next((s for s in secs if s[0] == ".boot"), None)
    if boot is None:
        if verbose:
            print("REFUSING: no .boot section in the syms toml.")
        return None
    res = {}
    for swap in (False, True):
        h, n, _ = compare(raw, rom, boot, swap)
        res[swap] = (h, n, 100.0 * h / n if n else 0.0)
    if verbose:
        for swap in (False, True):
            h, n, p = res[swap]
            print(f"  .boot, swap={str(swap):<5} : {h}/{n} words ({p:.2f}%)")
    good = [s for s in (False, True) if res[s][2] >= 99.0]
    if len(good) != 1:
        if verbose:
            print("REFUSING: the byte convention is not decided by .boot "
                  f"({len(good)} convention(s) above 99%). A guess here would "
                  "make every overlay look absent.")
        return None
    return good[0]


def self_check(snap):
    raw, rom = load(snap), ROM.read_bytes()
    secs = sections()
    ok = True
    print(f"  fixtures: {len(secs)} sections from {SYMS}, "
          f"{len(raw)} B snapshot, {len(rom)} B rom")

    swap = pick_convention(raw, rom, secs)
    c1 = swap is not None
    print(f"  C1 POSITIVE  .boot matches >=99% under exactly one convention   "
          f"{'PASS' if c1 else 'FAIL — the walk or the convention is broken'}")
    ok &= c1
    if not c1:
        print("\nSELF-CHECK FAIL")
        return 1

    boot = next(s for s in secs if s[0] == ".boot")
    h, n, _ = compare(raw, rom, boot, swap, vram_shift=0x100)
    pct = 100.0 * h / n if n else 0.0
    c2 = pct < 5.0
    print(f"  C2 NEGATIVE  .boot at a WRONG offset collapses ({pct:.2f}%)      "
          f"{'PASS' if c2 else 'FAIL — the comparison is broken OPEN'}")
    ok &= c2

    ovl = [s for s in secs if s[0].startswith(".ovlfile")]
    scores = []
    for s in ovl:
        h, n, _ = compare(raw, rom, s, swap)
        scores.append(100.0 * h / n if n else 0.0)
    spread = max(scores) - min(scores) if scores else 0.0
    c3 = spread > 10.0
    print(f"  C3 DISCRIM   {len(ovl)} overlays span {spread:.1f} percentage points  "
          f"{'PASS' if c3 else 'FAIL — cannot separate candidates'}")
    ok &= c3

    print(f"\nSELF-CHECK {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 0
    snap = Path(a[0])
    if "--dry-run" in a:
        print("DRY RUN -- what this would do, and nothing else:")
        print(f"  1. parse [[section]] blocks from {SYMS} (name/rom/vram/size)")
        print(f"  2. read {ROM} and the snapshot {snap}")
        print( "  3. MEASURE the byte convention on .boot under both orders and")
        print( "     REFUSE unless exactly one exceeds 99%")
        print( "  4. for every .ovlfileNN, compare its ROM image against the")
        print( "     snapshot at its own vram, word by word, WHOLE IMAGE")
        print( "  5. print each overlay's match %, and with --map the per-64-byte")
        print( "     block map so a window holding two overlays shows as two")
        print( "  It writes nothing, runs no subprocess, and launches nothing.")
        return 0
    if not snap.exists():
        print(f"REFUSING: no such snapshot {snap}", file=sys.stderr)
        return 2
    if "--self-check" in a:
        return self_check(snap)

    raw, rom = load(snap), ROM.read_bytes()
    secs = sections()
    print(f"snapshot: {snap.name}  ({len(raw)} B)")
    swap = pick_convention(raw, rom, secs)
    if swap is None:
        return 2
    print(f"  byte convention: {'word-swapped' if swap else 'direct'} "
          f"(MEASURED on .boot, not assumed)\n")

    rows = []
    for s in secs:
        if not s[0].startswith(".ovlfile"):
            continue
        h, n, blocks = compare(raw, rom, s, swap)
        rows.append((100.0 * h / n if n else 0.0, h, n, s, blocks))
    rows.sort(reverse=True, key=lambda r: r[0])

    top = int(a[a.index("--top") + 1]) if "--top" in a else 6
    print(f"{'section':<14} {'match':>8}  {'words':>12}   size")
    for pct, h, n, s, _ in rows[:top]:
        print(f"{s[0]:<14} {pct:7.2f}%  {h:5d}/{n:<6d}   0x{s[3]:X}")
    if len(rows) > top:
        print(f"  ... {len(rows) - top} more, lowest {rows[-1][0]:.2f}%")

    if "--map" in a:
        print("\nPER-BLOCK MAP — 64 bytes per cell, '#' = all 16 words match")
        print("(this is the thing a fingerprint cannot show: a window holding")
        print(" two overlays stacked appears here as two overlays stacked)")
        for pct, h, n, s, blocks in rows[:top]:
            line = "".join("#" if b else "." for b in blocks)
            print(f"\n{s[0]}  vram 0x{s[2]:X}..0x{s[2]+s[3]:X}  ({pct:.1f}%)")
            for i in range(0, len(line), 100):
                print(f"  +0x{i*64:05X} {line[i:i+100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
