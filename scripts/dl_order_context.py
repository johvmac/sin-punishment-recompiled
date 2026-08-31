#!/usr/bin/env python3
"""dl_order_context.py -- resolve [dlgeom] texture bindings and print what our
build does BETWEEN two of them.

WHY THIS EXISTS (A776, 2026-08-31).
    A772, A774 and A775 compared our binding ORDER against the reference's and
    found six inversions, five of them in 0x29Bxxx.  Every one of those three
    entries did its segment-base walk in a throwaway snippet: `ls scripts/`
    shows no tool, and A739 recorded exactly this failure mode for residency --
    "73 ledger rows rest on a method with no preserved tool".  This is that tool
    for the ordering work, built before the fourth entry rests on it.

WHAT IT READS
    OURS       a616-style [dlgeom] log.
                 `[dlgeom] s <seg> <base>`        sets a segment base
                 `[dlgeom] x <cmdword> <segaddr>` binds a texture image
                 `[dlgeom] task=NNNN BEGIN|END`   frame boundaries
                 `[dlgeom] m <seg> ...`           matrix load
                 `[dlgeom] v|t|r ...`             geometry
    REFERENCE  an a610-style ares RDP trace, split on `=== frame N (...) ===`,
               with `Tex Image ... addr=0x00XXXXXX` lines.

    Greps over [dlgeom] logs must be case-insensitive (T240); this parser lower-
    cases the tag before matching, so it does not have that hole.

ADDRESS CONVENTION -- MEASURED, NOT ASSUMED
    A binding word whose top byte is >= 0x80 is DIRECT: addr = word & 0xFFFFFF.
    Otherwise it is SEGMENTED: seg = word >> 24, addr = (base[seg] + (word &
    0xFFFFFF)) & 0xFFFFFF.  --self-check verifies this convention reproduces the
    published distinct-binding counts on both sides; if it does not, the
    convention is wrong and nothing downstream may be trusted.

CONTROLS (T71)
    C1  --dry-run          prints the plan and exits without reading either log.
    C2  --self-check       POSITIVE: reproduces A772's 103 distinct bindings in
                           our log and A775's 286 per reference frame.  This
                           FAILS if the segment walk is broken -- verified by
                           deliberately disabling the walk (--break-segments),
                           which drops ours to a different count.
    C3  --self-check       NEGATIVE: a pair the two sides agree on must come back
                           NOT inverted through the same comparison code that
                           reports the inversions.
    C4  --break-segments   the deliberate break C2 is verified against.

    A control that cannot fail is not a control (T65), and one that greps its own
    file is how they stop discriminating (T100) -- C2's needle is assembled from
    the two logs' own contents, never from this file.
"""

import argparse
import collections
import os
import re
import sys

DLGEOM = re.compile(r"^\[dlgeom\]\s+(\S+)\s*(.*)$", re.IGNORECASE)
TASK = re.compile(r"^task=(\d+)$", re.IGNORECASE)
REF_FRAME = re.compile(r"^===\s+frame\s+(\d+)\s")
REF_ADDR = re.compile(r"addr=0x([0-9A-Fa-f]{8})")

MASK = 0xFFFFFF


class Binding:
    __slots__ = ("line", "task", "cmd", "word", "seg", "off", "base", "addr")

    def __init__(self, line, task, cmd, word, seg, off, base, addr):
        self.line, self.task, self.cmd, self.word = line, task, cmd, word
        self.seg, self.off, self.base, self.addr = seg, off, base, addr

    def how(self):
        if self.seg is None:
            return "direct"
        return "seg%02X+%06X base=%06X" % (self.seg, self.off, self.base)


def parse_ours(path, break_segments=False, reset_per_task=False,
               count_unresolved=False):
    """Return (bindings, lines).  `lines` is the raw file, 0-indexed.

    With count_unresolved, returns (bindings, n_unresolved) instead -- used by
    C5 to compare the two segment-scope conventions.
    """
    with open(path, "r", errors="replace") as fh:
        lines = fh.read().splitlines()

    bases = {}
    task = None
    out = []
    unresolved = 0
    for i, raw in enumerate(lines):
        m = DLGEOM.match(raw)
        if not m:
            continue
        kind, rest = m.group(1), m.group(2)
        t = TASK.match(kind)
        if t:
            if rest.upper().startswith("BEGIN"):
                task = int(t.group(1))
                if reset_per_task:
                    bases = {}
            else:
                task = None
            continue
        k = kind.lower()
        if k == "s":
            f = rest.split()
            if len(f) >= 2 and not break_segments:
                try:
                    bases[int(f[0], 16)] = int(f[1], 16)
                except ValueError:
                    pass
            continue
        if k != "x":
            continue
        f = rest.split()
        if len(f) < 2:
            continue
        try:
            cmd, word = f[0].upper(), int(f[1], 16)
        except ValueError:
            continue
        top = word >> 24
        if top >= 0x80:
            seg, off, base, addr = None, None, None, word & MASK
        else:
            seg, off = top, word & MASK
            base = bases.get(seg)
            if base is None:
                unresolved += 1
                continue  # binding before its segment was ever set
            addr = (base + off) & MASK
        out.append(Binding(i, task, cmd, word, seg, off, base, addr))
    return (out, unresolved) if count_unresolved else (out, lines)


def parse_reference(path):
    """Return {frame: [(index, addr, text)]} in emission order."""
    frames = collections.OrderedDict()
    cur = None
    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            fm = REF_FRAME.match(raw)
            if fm:
                cur = int(fm.group(1))
                frames[cur] = []
                continue
            if cur is None or "Tex Image" not in raw:
                continue
            am = REF_ADDR.search(raw)
            if am:
                frames[cur].append((len(frames[cur]), int(am.group(1), 16) & MASK,
                                    raw.rstrip("\n")))
    return frames


def reference_units(frames):
    """Group the reference's frame-1 distinct bindings into TEXTURE UNITS.

    A743 measured that FD1xxxxxx is followed by `Load Tex LUT` in 327/327 and
    FD5xxxxx by `Load Block` in 328/328 -- palette and indexed image.  A unit is
    a consecutive (FD1, FD5) pair in the reference's own emission order; anything
    that does not pair that way stays a singleton rather than being forced.

    Returns (units, unit_of, order) where `order` is [(addr, cmdword), ...].
    """
    seen, order = set(), []
    for _, addr, txt in list(frames.values())[0]:
        if addr in seen:
            continue
        seen.add(addr)
        order.append((addr, txt.rstrip().split("\t")[-1][:8].upper()))

    units, unit_of, i = [], {}, 0
    while i < len(order):
        addr, cmd = order[i]
        if (i + 1 < len(order) and cmd.startswith("FD1")
                and order[i + 1][1].startswith("FD5")):
            partner = order[i + 1][0]
            units.append((addr, partner))
            unit_of[addr] = unit_of[partner] = len(units) - 1
            i += 2
        else:
            units.append((addr,))
            unit_of[addr] = len(units) - 1
            i += 1
    return units, unit_of, order


def first_appearance(seq):
    seen, out = set(), []
    for a in seq:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def inversions(ours_order, ref_order):
    """Pairs (a, b) where we bind a before b but the reference binds b before a.

    Restricted to addresses BOTH sides bind, which is the comparison A772/A774
    made.  Returns the list, so an empty list is a real negative result.
    """
    pos = {a: i for i, a in enumerate(ref_order)}
    shared = [a for a in ours_order if a in pos]
    bad = []
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            if pos[shared[i]] > pos[shared[j]]:
                bad.append((shared[i], shared[j]))
    return bad, shared


# ----------------------------------------------------------------- controls

def self_check(ours_path, ref_path, break_segments=False):
    """C2 positive + C3 negative.  Returns exit status."""
    ok = True
    binds, _ = parse_ours(ours_path, break_segments=break_segments)
    ours_order = first_appearance([b.addr for b in binds])
    frames = parse_reference(ref_path)

    # C2 POSITIVE -- A772's 103 and A775's 286, from the logs, not from here.
    print("C2 ours: %d bindings, %d distinct (A772 published 103)"
          % (len(binds), len(ours_order)))
    if len(ours_order) != 103:
        print("C2 FAIL: distinct binding count is not A772's 103")
        ok = False
    else:
        print("C2 PASS (ours)")

    ref_counts = {f: len(first_appearance([a for _, a, _ in v]))
                  for f, v in frames.items()}
    print("C2 reference: %d frames, distinct per frame %s (A775 published 286)"
          % (len(frames), sorted(set(ref_counts.values()))))
    if len(frames) != 8 or set(ref_counts.values()) != {286}:
        print("C2 FAIL: reference is not 8 frames of 286 distinct")
        ok = False
    else:
        print("C2 PASS (reference)")

    # C3 NEGATIVE -- the reference against ITSELF must show zero inversions,
    # through the same comparison code that reports ours.
    ref0 = first_appearance([a for _, a, _ in list(frames.values())[0]])
    for f, v in list(frames.items())[1:]:
        bad, _ = inversions(first_appearance([a for _, a, _ in v]), ref0)
        if bad:
            print("C3 FAIL: reference frame %d inverts against frame %d: %d pair(s)"
                  % (f, list(frames)[0], len(bad)))
            ok = False
            break
    else:
        print("C3 PASS: all %d reference frames agree with frame 1, zero inversions"
              % len(frames))

    # C5 -- THE PLAYBOOK AND A774 DISAGREE ABOUT SEGMENT SCOPE, so check it.
    # docs/diagnostic-playbook.md (A616) says "segment state must be reset at each
    # task boundary"; A774 walked the bases across the whole log.  If any binding
    # in a task used a base set in an EARLIER task, the two would differ.  On this
    # log they do not -- but that is a property of the log and must be re-checked
    # on any other, which is why this is a control and not a comment.
    carried, _ = parse_ours(ours_path, break_segments=break_segments)
    reset, unresolved = parse_ours(ours_path, break_segments=break_segments,
                                   reset_per_task=True, count_unresolved=True)
    same = ([(b.task, b.addr) for b in carried] == [(b.task, b.addr) for b in reset])
    print("C5 segment scope: carried-across vs reset-per-task %s, %d unresolved under reset"
          % ("IDENTICAL" if same else "DIFFER", unresolved))
    if not same:
        print("C5 FAIL: the two segment-scope conventions disagree on this log -- "
              "resolve which is right before believing any address")
        ok = False
    else:
        print("C5 PASS")

    print("SELF-CHECK %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ----------------------------------------------------------------- reporting

def show_context(ours_path, ref_path, addr_a, addr_b, task, pad):
    binds, lines = parse_ours(ours_path)
    frames = parse_reference(ref_path)
    ref0 = first_appearance([a for _, a, _ in list(frames.values())[0]])

    sel = [b for b in binds if task is None or b.task == task]
    hits_a = [b for b in sel if b.addr == addr_a]
    hits_b = [b for b in sel if b.addr == addr_b]
    print("task=%s  0x%06X bound %d time(s)   0x%06X bound %d time(s)"
          % (task, addr_a, len(hits_a), addr_b, len(hits_b)))
    if not hits_a or not hits_b:
        print("one of the two is never bound in this task -- nothing to show")
        return 1

    for label, hs in (("0x%06X" % addr_a, hits_a), ("0x%06X" % addr_b, hits_b)):
        for h in hs:
            print("  %s at line %d  cmd=%s word=%08X  %s"
                  % (label, h.line + 1, h.cmd, h.word, h.how()))

    try:
        pa, pb = ref0.index(addr_a), ref0.index(addr_b)
        print("reference frame-1 positions: 0x%06X at %d, 0x%06X at %d -- reference binds %s first"
              % (addr_a, pa, addr_b, pb, "0x%06X" % (addr_a if pa < pb else addr_b)))
    except ValueError:
        print("at least one address is not in the reference's frame-1 order")

    lo, hi = hits_a[0].line, hits_b[0].line
    if lo > hi:
        lo, hi = hi, lo
    print("\n--- our log, lines %d..%d (%d lines between the two bindings) ---"
          % (lo + 1 - pad, hi + 1 + pad, hi - lo - 1))
    kinds = collections.Counter()
    for i in range(max(0, lo - pad), min(len(lines), hi + pad + 1)):
        mark = ">>" if i in (lo, hi) else "  "
        print("%s %6d  %s" % (mark, i + 1, lines[i]))
        if lo < i < hi:
            m = DLGEOM.match(lines[i])
            if m:
                kinds[m.group(1).lower()] += 1
    print("\nBETWEEN the two bindings, [dlgeom] line kinds: %s"
          % (dict(kinds) or "none"))
    return 0


def show_units(ours_path, ref_path):
    """Per task: our binding order expressed as reference TEXTURE UNIT indices.

    This is the view that separates two very different faults -- our build
    emitting a unit's palette and image out of order (INTRA-unit), versus
    emitting whole units in a different order (INTER-unit).  Both are visible
    here, so a zero on one of them is a real negative and not a blind spot.
    """
    binds, _ = parse_ours(ours_path)
    frames = parse_reference(ref_path)
    units, unit_of, order = reference_units(frames)
    pos = {a: i for i, (a, _) in enumerate(order)}
    pairs = sum(1 for u in units if len(u) == 2)
    print("reference frame 1: %d distinct -> %d units (%d palette+image pairs, %d singletons)"
          % (len(order), len(units), pairs, len(units) - pairs))

    for t in [x for x in dict.fromkeys(b.task for b in binds) if x is not None]:
        ours = [a for a in first_appearance([b.addr for b in binds if b.task == t])
                if a in pos]
        inv, _ = inversions(ours, [a for a, _ in order])
        intra = [(x, y) for x, y in inv if unit_of[x] == unit_of[y]]
        useq = first_appearance([unit_of[a] for a in ours])
        runs = []
        for u in useq:
            if runs and u == runs[-1][1] + 1:
                runs[-1][1] = u
            else:
                runs.append([u, u])
        desc = [(useq[i], useq[i + 1]) for i in range(len(useq) - 1)
                if useq[i] > useq[i + 1]]
        print("\ntask %d: %d shared bindings, %d units" % (t, len(ours), len(useq)))
        print("  inverted address pairs %d, of which INTRA-UNIT %d" % (len(inv), len(intra)))
        print("  unit sequence: %s" % useq)
        print("  contiguous runs of reference units: %s"
              % ", ".join("%d-%d" % (a, b) if a != b else str(a) for a, b in runs))
        if desc:
            lo, hi = min(min(d) for d in desc), max(max(d) for d in desc)
            print("  disorder confined to reference units %d..%d" % (lo, hi))
        for x, y in desc:
            print("    ours emits unit %d then %d (reference distance %d): %s before %s"
                  % (x, y, x - y,
                     "/".join("0x%06X" % v for v in units[x]),
                     "/".join("0x%06X" % v for v in units[y])))
        if not desc:
            print("  no descents -- this frame is in exact reference order")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ours", default="a616-tutorial-timg.log")
    ap.add_argument("--reference", default="a610-tutorial-rdp.txt")
    ap.add_argument("--dry-run", action="store_true", help="C1: print the plan and exit")
    ap.add_argument("--self-check", action="store_true", help="C2 + C3")
    ap.add_argument("--break-segments", action="store_true",
                    help="C4: deliberately disable the segment walk, to verify C2 can fail")
    ap.add_argument("--context", nargs=2, metavar=("A", "B"),
                    help="two hex addresses; print our log between their bindings")
    ap.add_argument("--task", type=int, default=None)
    ap.add_argument("--pad", type=int, default=6)
    ap.add_argument("--inversions", action="store_true",
                    help="list our inversions against reference frame 1, per task")
    ap.add_argument("--units", action="store_true",
                    help="per task, our order as reference texture-unit indices")
    a = ap.parse_args()

    if a.dry_run:
        print("DRY RUN -- would do the following and read no log:")
        print("  1. parse %s: walk `s <seg> <base>`, tag `x` bindings by task" % a.ours)
        print("  2. parse %s: split on `=== frame N`, take Tex Image addr=" % a.reference)
        print("  3. --self-check: C2 expects 103 distinct ours / 286 per ref frame;")
        print("     C3 expects zero inversions of the reference against itself;")
        print("     C4 (--break-segments) is the deliberate break C2 must fail on")
        print("  4. --context A B: print our raw log lines between the two bindings")
        print("  5. --inversions: per-task inversion pairs vs reference frame 1")
        return 0

    for p in (a.ours, a.reference):
        if not os.path.exists(p):
            print("missing: %s" % p, file=sys.stderr)
            return 2

    if a.self_check:
        return self_check(a.ours, a.reference, break_segments=a.break_segments)

    if a.inversions:
        binds, _ = parse_ours(a.ours, break_segments=a.break_segments)
        frames = parse_reference(a.reference)
        ref0 = first_appearance([x for _, x, _ in list(frames.values())[0]])
        tasks = [t for t in dict.fromkeys(b.task for b in binds) if t is not None]
        for t in tasks:
            order = first_appearance([b.addr for b in binds if b.task == t])
            bad, shared = inversions(order, ref0)
            print("task %d: %d distinct, %d shared with reference, %d inversion pair(s)"
                  % (t, len(order), len(shared), len(bad)))
            for x, y in bad:
                print("    0x%06X -> 0x%06X" % (x, y))
        return 0

    if a.units:
        return show_units(a.ours, a.reference)

    if a.context:
        return show_context(a.ours, a.reference,
                            int(a.context[0], 16) & MASK,
                            int(a.context[1], 16) & MASK, a.task, a.pad)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
