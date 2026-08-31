#!/usr/bin/env python3
"""ovl_burst.py -- did an archive land on an overlay while the game was RUNNING?

WHY THIS EXISTS (A779, 2026-08-31).
    A767 found nine Yay0 archives DMA'd to the shared overlay window 0x800E4780
    and quoted the probe's own 2026-08-18 comment about the hazard: an overlay
    partially overwritten leaves indirect calls resolving into whatever is still
    mapped.  A773 then deflated A767's 84% headline and left ONE live question:
    "whether any of them is loaded while the overlay it lands on is still
    executing."

    The SNP_OVL logs carry `[heartbeat] t=Ns` lines.  That is the only execution
    signal in them, and it is enough to partition the DMA stream into BURSTS
    separated by observed execution.  A collision inside one burst is part of a
    single load sequence; a collision spanning a heartbeat is the hazard.

WHAT IT MEASURES
    For each log: split `[ovl]` lines on heartbeats, keep those targeting the
    window, and report every case where a no-match transfer lands on an overlay
    (a "1 section" transfer) loaded EARLIER IN THE SAME BURST -- and separately
    the state each burst LEAVES the window in, which is what the following
    execution interval actually runs against.

WHAT IT CANNOT SHOW (T209), stated before the result is read
    * Heartbeats are ONE SECOND apart.  "No heartbeat between two DMAs" bounds
      the gap at under a second; it does NOT mean zero instructions ran.  The
      loader is itself code.  So this can never prove an overlay was NOT
      executing -- only that no observed execution interval was crossed.
    * It sees DMA, not execution.  An overlay left half-overwritten is a hazard
      only if something calls into the damaged span, and this says nothing about
      that.
    * "1 section" is the probe's own matcher.  A767 recorded that most window
      traffic matches nothing; a mislabelled overlay would be invisible here.

CONTROLS (T71)
    C1  --dry-run     prints the plan and reads no log.
    C2  --self-check  POSITIVE, and its needle comes from the logs rather than
                      this file (T100): the parse must reproduce A767's
                      PUBLISHED 151 total [ovl] lines and 44 window-targeting
                      ones.  A wrong regex changes both.
    C3  --self-check  the two long logs (ovl1, ovl2) are separate runs of the
                      same sequence; their window burst structure must agree.
                      Two runs agreeing is the reproducibility check A767 and
                      A773 never had -- and it can fail.
    C4  --break-heartbeats  the deliberate break: ignore heartbeats entirely, so
                      everything collapses to ONE burst.  C3 still passes but the
                      burst count must change, proving the partition is real and
                      not an artefact of the file order.
"""

import argparse
import os
import re
import sys

WINDOW = 0x800E4780
OVL = re.compile(r"^\[ovl\] rom=0x([0-9A-Fa-f]+) ram=0x([0-9A-Fa-f]+) "
                 r"size=0x([0-9A-Fa-f]+) -> (\d+) section")
HEARTBEAT = re.compile(r"^\[heartbeat\] t=(\d+)s")

LOGS = ("ovl.log", "ovl1.log", "ovl2.log")


def parse(path, ignore_heartbeats=False):
    """Return (bursts, n_ovl_lines, n_window, n_heartbeats).

    A burst is (writes, t_start, t_end) where writes are window-targeting
    transfers as (rom, size, sections).
    """
    bursts, cur, hb, t = [], [], 0, 0
    start_t = 0
    n_ovl = n_win = 0
    with open(path, errors="replace") as fh:
        for raw in fh:
            m = HEARTBEAT.match(raw)
            if m:
                hb += 1
                t = int(m.group(1))
                if not ignore_heartbeats:
                    if cur:
                        bursts.append((cur, start_t, t))
                        cur = []
                    # start_t MUST advance on EVERY heartbeat, not only when a
                    # burst is flushed.  The first version left it stale through
                    # quiet heartbeats, so a burst preceded by six idle seconds
                    # reported the start of the PREVIOUS burst -- which made the
                    # gap between two bursts read as 0s when it was ~6s.
                    start_t = t
                continue
            m = OVL.match(raw)
            if not m:
                continue
            n_ovl += 1
            rom = int(m.group(1), 16)
            ram = int(m.group(2), 16)
            size = int(m.group(3), 16)
            sec = int(m.group(4))
            if ram == WINDOW:
                n_win += 1
                cur.append((rom, size, sec))
    if cur:
        bursts.append((cur, start_t, t))
    return bursts, n_ovl, n_win, hb


def collisions(writes):
    """Data landing on an overlay loaded EARLIER IN THE SAME BURST."""
    out = []
    for i, (r1, s1, c1) in enumerate(writes):
        if not c1:
            continue
        for r2, s2, c2 in writes[i + 1:]:
            if not c2 and s2 <= s1:
                out.append(((r1, s1), (r2, s2)))
    return out


def resting_state(writes):
    """Bytes of the window owned by each transfer after the burst, top-down.

    Later transfers overwrite earlier ones from the base, so walking the burst
    backwards and taking the first writer that still reaches each offset gives
    the layout the following execution interval runs against.
    """
    layout, covered = [], 0
    for rom, size, sec in reversed(writes):
        if size > covered:
            layout.append((covered, size, rom, sec))
            covered = size
    return layout


def report(paths, ignore_heartbeats=False):
    for p in paths:
        bursts, n_ovl, n_win, hb = parse(p, ignore_heartbeats)
        live = [b for b in bursts if b[0]]
        print("=== %s: %d [ovl] lines, %d to the window, %d heartbeats, %d burst(s) with window writes"
              % (os.path.basename(p), n_ovl, n_win, hb, len(live)))
        # THE RESTING INTERVAL IS TO THE NEXT BURST, NOT THE BURST'S OWN LENGTH.
        # The first version printed `t1 - t0` here, which is how long the burst
        # itself spanned -- not how long its layout survives.  Caught before the
        # number was quoted anywhere; the two differ by 6x on the burst that
        # matters, which is precisely the shape T209 exists to stop.
        for i, (writes, t0, t1) in enumerate(live):
            nxt = live[i + 1][1] if i + 1 < len(live) else None
            print("  burst t=%ds..%ds, %d window write(s)" % (t0, t1, len(writes)))
            for rom, size, sec in writes:
                print("     rom=0x%08X size=0x%-6X %s"
                      % (rom, size, "OVERLAY" if sec else "no match"))
            for (r1, s1), (r2, s2) in collisions(writes):
                print("     >>> 0x%08X (0x%X) LANDS ON overlay 0x%08X (0x%X), same burst"
                      % (r2, s2, r1, s1))
            held = ("%ds (until the next window burst at t=%ds)" % (max(0, nxt - t1), nxt)
                    if nxt is not None else "to the end of the log")
            print("     this layout then rests for %s:" % held)
            for lo, hi, rom, sec in resting_state(writes):
                print("       +0x%06X..+0x%06X  0x%08X  %s"
                      % (lo, hi, rom, "OVERLAY" if sec else "no match"))
        print()


def self_check(paths, ignore_heartbeats=False):
    ok = True
    tot_ovl = tot_win = 0
    per = {}
    for p in paths:
        bursts, n_ovl, n_win, _ = parse(p, ignore_heartbeats)
        tot_ovl += n_ovl
        tot_win += n_win
        per[os.path.basename(p)] = [(w, ) for w, _, _ in bursts if w]

    # C2 POSITIVE -- A767's published totals, from the logs not from this file.
    print("C2 totals: %d [ovl] lines (A767 published 151), %d window-targeting (published 44)"
          % (tot_ovl, tot_win))
    if (tot_ovl, tot_win) != (151, 44):
        print("C2 FAIL: does not reproduce A767's census")
        ok = False
    else:
        print("C2 PASS")

    # C3 -- the two long logs are separate runs of the same sequence.
    a, b = per.get("ovl1.log"), per.get("ovl2.log")
    if a is None or b is None:
        print("C3 SKIP: ovl1.log / ovl2.log not both present")
    elif a == b:
        print("C3 PASS: ovl1 and ovl2 have identical window burst structure (%d bursts)" % len(a))
    else:
        print("C3 FAIL: the two runs disagree — %d vs %d bursts" % (len(a), len(b)))
        ok = False

    print("burst counts per log: %s"
          % {k: len(v) for k, v in sorted(per.items())})
    print("SELF-CHECK %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="*", default=list(LOGS))
    ap.add_argument("--dry-run", action="store_true", help="C1")
    ap.add_argument("--self-check", action="store_true", help="C2 + C3")
    ap.add_argument("--break-heartbeats", action="store_true",
                    help="C4: ignore heartbeats so everything collapses to one burst")
    a = ap.parse_args()

    if a.dry_run:
        print("DRY RUN -- would do the following and read no log:")
        print("  1. parse [ovl] and [heartbeat] lines from %s" % ", ".join(a.logs))
        print("  2. split window (0x%08X) transfers into heartbeat-separated bursts" % WINDOW)
        print("  3. report collisions (data over an overlay in the SAME burst) and the")
        print("     resting layout each burst leaves for the following execution interval")
        print("  4. --self-check: C2 expects 151 / 44 (A767's published census);")
        print("     C3 expects ovl1 and ovl2 to have identical burst structure;")
        print("     C4 --break-heartbeats collapses to one burst and must CHANGE the count")
        return 0

    missing = [p for p in a.logs if not os.path.exists(p)]
    if missing:
        print("missing: %s" % ", ".join(missing), file=sys.stderr)
        return 2

    if a.self_check:
        return self_check(a.logs, a.break_heartbeats)
    report(a.logs, a.break_heartbeats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
