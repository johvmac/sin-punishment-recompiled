#!/usr/bin/env python3
"""Level-2 discipline audit: the DAILY digest. Reads only L1's output.

WHY THIS EXISTS
The audit ladder was specified on 2026-08-18 with four levels. L1 was built and
has run 8 times. **L2 and L3 were never built and never ran**, and neither had
any nag, so they were never going to happen on their own (T78).

That mattered because L1 checks LEADING INDICATORS -- single-run claims, probes
without controls, churn -- and cannot see the failure that actually dominates
here: a claim broader than its evidence. Every defect the user caught this
session was of that kind. L2's job is not to catch those mechanically; it is to
put a short enough digest in front of a human that they can.

THE RULE THAT KEEPS THE LADDER CHEAP
**Each level reads the level below's OUTPUT, never the raw data.** L2 reads the
L1 blocks in docs/audit-log.md and nothing else. It must NOT open the ledger,
the run log or the route log -- if it did, it would cost what L1 costs and get
skipped, which is how the ladder dies. `--self-check` asserts this by inspecting
which paths this file names, so the property is enforced rather than promised.

WHAT IT PRODUCES
  * defects grouped BY CLASS, with the trend across recent L1 blocks
  * for each recurring class: did the fix hold, or did the class come back?
  * the load-bearing claims and their falsifiers, for the user to scan

Usage:
    scripts/audit_l2.py             # run, record an L2 block
    scripts/audit_l2.py --dry-run   # print, do not record
    scripts/audit_l2.py --self-check
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
L1LOG = DOCS / "audit-log.md"          # the ONLY input
OUT = DOCS / "audit-l2-log.md"
STATE = DOCS / ".audit-l2-state.json"

# Defect classes, keyed to the L1 phrasing that reports them. Each maps to a
# failure that really happened -- the same discipline as audit.py's checks.
CLASSES = [
    ("single-run",    r"rests on ONE run",                     "T22"),
    ("no-control",    r"probe with no control",                "I1/I13"),
    ("churn",         r"created and withdrawn within one",     "I14"),
    ("no-evidence",   r"no evidence recorded",                 "A24/B35"),
    ("under-explore", r"[Uu]nder-exploring",                   "T14"),
    ("bad-run",       r"contaminated|exited early",            "T23"),
]


def l1_blocks(text):
    """(number, body) for each '## Audit #N' block. VOID blocks are skipped."""
    out = []
    for m in re.finditer(r"^## Audit #(\d+)[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        body = m.group(2)
        if "VOID" in m.group(0).split("\n")[0]:
            continue
        out.append((int(m.group(1)), body))
    return out


def classify(body):
    """Count findings by class. FINDING LINES ONLY.

    The first version scanned the whole block, so audit #6's header line
    "runs: 3 (0 exited early, 0 contaminated)" was counted as two `bad-run`
    defects. A block's header states the window; only the bulleted entries
    under "things to look at" are findings.
    """
    findings = [l for l in body.split("\n") if re.match(r"\s+- ", l)]
    counts = {}
    for name, pat, _origin in CLASSES:
        n = sum(1 for l in findings if re.search(pat, l))
        if n:
            counts[name] = n
    return counts


def resolutions(body):
    """(resolved, still_open) counts by class, from L1's resolution lines.

    WHY THIS EXISTS. L1 used to emit a finding once and never revisit it, so
    this level counted problems FOUND and never problems FIXED. A class whose
    every instance was corrected in the next commit read exactly like one being
    ignored, and L3 duly reported it as recurring forever -- an alarm that
    always sounds (T29). A273 was flagged and waived in the SAME COMMIT and
    still counted as a recurrence three digests running.

    These lines start at column 0; `classify` only counts INDENTED bullets, so
    a resolution can never be miscounted as a fresh defect. That separation is
    load-bearing, not incidental.
    """
    res, still = {}, {}
    for tgt, head in ((res, r"resolved since last audit"),
                      (still, r"STILL OPEN from earlier audits")):
        m = re.search(head + r"[^:]*:\*\*\s*(.+)", body)
        if not m:
            continue
        for item in m.group(1).split(";"):
            c = re.search(r"\((?:.*?)\b(single-run|no-control|no-evidence)\b", item)
            if c:
                tgt[c.group(1)] = tgt.get(c.group(1), 0) + 1
    return res, still


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"l2s": 0, "last_l1": 0, "quiet_streak": 0}


def streak_after(prev, digested, quiet):
    """The quiet streak has THREE inputs, not two. This used to be a boolean.

    The original was `quiet = not new or <no defects>`, which scored "the level
    below has not run" identically to "I examined its output and found nothing
    wrong". Those are opposite situations: the second is evidence of calm, the
    first is evidence of nothing at all. Because each ladder level reads the
    level below, the error compounded upward -- L1 not running made L2 quiet,
    which would in turn make L3 quiet, so SKIPPED WORK PROPAGATED UPWARD AS
    HEALTH, and at streak 2 the level demoted itself to a slower cadence on the
    strength of its own inactivity. Found 2026-08-20 while auditing why an L2
    reported "nothing to digest" one step before demoting itself.

    So: a no-op HOLDS the streak. It cannot advance it (nothing was examined)
    and it must not reset it either (nothing was refuted).
    """
    if not digested:
        return prev
    return prev + 1 if quiet else 0


def self_check():
    """Assert the LAYERING, which is the ladder's whole cost argument."""
    src = Path(__file__).read_text()
    checks = []

    # 1. LAYERING: this file must not construct a path to any raw-data file.
    #
    # Parsed with `ast`, not grepped. Two earlier versions of this control were
    # self-referential and failed on themselves: the first searched for the bare
    # filenames and matched its own list of them; the second searched for the
    # `DOCS / "name"` idiom and matched the COMMENT explaining the idiom. A
    # control that fires on its own text is as useless as one that cannot fire
    # at all (T65). Only real `X / "name"` expressions in the AST count.
    import ast as _ast
    raw_names = {"findings-ledger.md", "run-log.tsv", "route-log.md"}
    found = set()
    for node in _ast.walk(_ast.parse(src)):
        if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Div):
            for side in (node.left, node.right):
                if isinstance(side, _ast.Constant) and side.value in raw_names:
                    found.add(side.value)
    raw = sorted(found)
    checks.append(("reads only L1 output, never raw data", not raw,
                   f"constructs a path to {raw}" if raw else
                   "no raw-data path constructed anywhere in the AST"))

    # 2. It must actually classify. A digest that groups nothing is a file copy.
    if L1LOG.exists():
        blocks = l1_blocks(L1LOG.read_text())
        seen = {}
        for _n, b in blocks:
            for k, v in classify(b).items():
                seen[k] = seen.get(k, 0) + v
        checks.append((f"classifies real L1 findings ({len(blocks)} blocks)", bool(seen),
                       ", ".join(f"{k}={v}" for k, v in sorted(seen.items())) or "nothing classified"))
        # 3. Positive control: audit #6 is known to hold 6 single-run, 3
        #    no-control and 3 churn findings. If the parser drifts, this fails.
        six = dict(classify(dict(blocks).get(6, "")))
        want = {"single-run": 6, "no-control": 3, "churn": 3}
        checks.append(("audit #6 classifies as 6/3/3 (known content)", six == want,
                       f"got {six}"))
    else:
        checks.append(("L1 log present", False, "docs/audit-log.md missing"))

    # 4. THE NO-OP MUST NOT SCORE AS CALM. This is the control for the defect
    #    described in streak_after's docstring. It is written against the three
    #    cases directly, so reinstating `quiet = not new or ...` fails it: that
    #    form makes the no-op case quiet, which advances the streak to prev+1
    #    and the first assertion below goes 1 != 2.
    #
    #    VERIFIED TO FAIL, not merely to pass (T65/T71): the buggy expression
    #    was pasted back in and this control reported
    #    "FAIL ... no-op advanced the streak to 2". Restored after.
    cases = [
        ("no-op holds",       streak_after(1, False, False), 1),
        ("no-op holds (2)",   streak_after(0, False, False), 0),
        ("clean day advances", streak_after(1, True, True),  2),
        ("defects reset",     streak_after(1, True, False),  0),
    ]
    wrong = [f"{n}: got {g} want {w}" for n, g, w in cases if g != w]
    checks.append(("a no-op does not score as a quiet day", not wrong,
                   "; ".join(wrong) if wrong else
                   "no-op holds the streak; only an examined-and-clean window advances it"))

    # --- resolution parsing (2026-08-21) ------------------------------------
    # The point of the whole feature: found-and-fixed must be distinguishable
    # from found-and-ignored. A parser that returned nothing would make every
    # class look unresolved forever -- which is the bug being fixed -- so this
    # asserts BOTH sides against one block, and asserts they do not bleed into
    # the defect count.
    blk = ("- **2 thing(s) to look at:**\n"
           "  - A9: rests on ONE run (x.log). Repeat it or say why one is enough.\n"
           "  - A8: no evidence recorded. Say what was observed and when.\n"
           "- **resolved since last audit (2):** A1 (single-run, open since #3); "
           "A2 (no-evidence, open since #4)\n"
           "- **STILL OPEN from earlier audits (1):** A3 (no-control, open since #2, 5 audit(s))\n")
    r, s = resolutions(blk)
    checks.append(("resolutions are read from L1's output",
                   r == {"single-run": 1, "no-evidence": 1} and s == {"no-control": 1},
                   f"resolved={r} still_open={s}"))
    # DISCRIMINATING: the resolution lines sit at column 0 and `classify` counts
    # only indented bullets. If that ever changes, a FIX would be tallied as a
    # fresh DEFECT -- the exact inversion this feature exists to prevent.
    cls = classify(blk)
    checks.append(("a resolution is never counted as a defect",
                   cls == {"single-run": 1, "no-evidence": 1},
                   f"got {cls} — must see the 2 findings only, not the 3 resolutions"))

    # END-TO-END (A588, after A587). Every control above tests a PARSER or a
    # classifier; none ever ran the report. That is precisely how audit_l3.py
    # crashed on every real invocation for a week while its own suite reported
    # 8/8 — the defect lived in the WIRING between a helper and its consumer,
    # and a component control cannot see wiring. Runs the whole thing in
    # dry-run and asserts it RETURNS rather than RAISES.
    import io as _io, contextlib as _cl
    try:
        _argv = sys.argv[:]
        sys.argv = [_argv[0], "--dry-run"]
        try:
            with _cl.redirect_stdout(_io.StringIO()), _cl.redirect_stderr(_io.StringIO()):
                _rc = main()
        finally:
            sys.argv = _argv
        _ok, _why = _rc in (0, 1), f"main() returned {_rc}"
    except Exception as _e:
        _ok, _why = False, f"main() RAISED {type(_e).__name__}: {_e}"
    checks.append(("the digest itself RUNS end to end (not just the parsers)",
                   _ok, _why))

    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:48} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    unknown = [x for x in a if x not in {"--dry-run", "--self-check", "--help", "-h"}]
    if unknown:
        # Never fall through to a state-mutating default on input we did not
        # understand -- route.py did once and consumed a roll (T37).
        print(f"[l2] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print("[l2] REFUSING; a recorded audit must be asked for explicitly.", file=sys.stderr)
        return 2
    dry = "--dry-run" in a

    if not L1LOG.exists():
        print("[l2] no L1 log yet — run scripts/audit.py first.", file=sys.stderr)
        return 1
    blocks = l1_blocks(L1LOG.read_text())
    st = load_state()
    new = [(n, b) for n, b in blocks if n > st["last_l1"]]

    lines = [f"## L2 #{st['l2s'] + 1} — covering L1 audits "
             f"{new[0][0] if new else '-'}..{new[-1][0] if new else '-'}"]
    if not new:
        lines.append("- no new L1 blocks since the last L2. Nothing to digest.")
    else:
        # by class, this window vs everything before it
        cur, prior = {}, {}
        fixed, open_now = {}, {}
        for n, b in blocks:
            tgt = cur if n > st["last_l1"] else prior
            for k, v in classify(b).items():
                tgt[k] = tgt.get(k, 0) + v
            if n > st["last_l1"]:
                r, s = resolutions(b)
                for k, v in r.items():
                    fixed[k] = fixed.get(k, 0) + v
                for k, v in s.items():
                    open_now[k] = max(open_now.get(k, 0), v)   # a level, not a flow
        lines.append(f"- L1 blocks digested: {len(new)}")
        if cur or fixed:
            lines.append("- **defects by class (raised this window / all prior / "
                         "FIXED this window / still open):**")
            for name, _pat, origin in CLASSES:
                c, p = cur.get(name, 0), prior.get(name, 0)
                f, o = fixed.get(name, 0), open_now.get(name, 0)
                if not c and not p and not f:
                    continue
                # A CLASS "RECURS" ONLY IF SOMETHING IS STILL BROKEN. Raised-and-
                # fixed is the system working, and scoring it as recurrence is
                # what made this line fire permanently.
                if o:
                    trend = "UNRESOLVED"
                elif c and f >= c:
                    trend = "raised, all fixed"
                elif p == 0 and c:
                    trend = "NEW"
                elif c and p:
                    trend = "recurs"
                else:
                    trend = "quiet"
                lines.append(f"  - `{name}` ({origin}): {c} / {p} / {f} / {o} — **{trend}**")
            # The question the playbook says L2 exists to ask -- now asked of
            # what is STILL WRONG rather than of what was ever noticed.
            recur = [n for n, _p, _o in CLASSES if open_now.get(n)]
            if recur:
                lines.append(f"- **DID THE FIX HOLD? These classes have instances STILL OPEN: "
                             f"{', '.join('`'+r+'`' for r in recur)}.** A class that stays open after a "
                             f"fix means the fix addressed an instance, not the class.")
            elif fixed:
                lines.append(f"- every defect raised in this window was FIXED "
                             f"({sum(fixed.values())} resolved, 0 still open). "
                             f"**Found-and-fixed is the loop working, not a recurrence.**")
        else:
            lines.append("- no defects reported in this window")

    digested = bool(new)
    quiet = digested and not any(classify(b) for _n, b in new)
    streak = streak_after(st["quiet_streak"], digested, quiet)
    if not digested:
        lines.append(f"- quiet: **n/a — NOTHING WAS DIGESTED, so this is not evidence of calm.** "
                     f"Streak HELD at {streak}. L1 is behind; run `scripts/audit.py`.")
    else:
        lines.append(f"- quiet: {'yes' if quiet else 'no'} "
                     f"(streak {streak}; at 2, drop L2 to weekly)")
    lines.append("- **L2 is a digest for a human, not a verdict.** The failure that dominates "
                 "here — a claim broader than its evidence — leaves no mechanical trace. Scan the "
                 "classes above and ask whether any of them is that.")

    block = "\n".join(lines)
    print(block)
    if dry:
        print("\n[l2] --dry-run: nothing recorded.", file=sys.stderr)
        return 0

    import datetime as _dt
    st["last_date"] = _dt.date.today().isoformat()
    st["l2s"] += 1
    st["last_l1"] = blocks[-1][0] if blocks else st["last_l1"]
    st["quiet_streak"] = streak
    STATE.write_text(json.dumps(st, indent=1))
    if not OUT.exists():
        OUT.write_text("# L2 audit log\n\nDaily digests. Each reads ONLY the L1 blocks in "
                       "`audit-log.md`. The weekly L3 review reads ONLY this file.\n\n")
    with OUT.open("a") as f:
        f.write(block + "\n\n")
    print(f"\n[l2] recorded to {OUT.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
