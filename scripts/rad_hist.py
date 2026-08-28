#!/usr/bin/env python3
"""Aggregate the A668 [rad] per-task radius lines into scene bands.

Usage:
  scripts/rad_hist.py <run.log>          aggregate and print the table
  scripts/rad_hist.py --self-check       synthetic input, known answers
  scripts/rad_hist.py --help             this text

WHAT IT READS
  [rad] task=N n=.. neg=.. z=.. bad=.. maxexp=.. max=.. b=c0,..,c7 tot=..
  emitted once per graphics task by snp_radius_seen/snp_rw_task (A668). Band k
  covers floor(log2 r) in [4k-16, 4k-12); band 0 is r < 2^-12, band 7 r >= 2^12.

WHY IT IS A SCRIPT WITH A SELF-CHECK AND NOT AN awk ONE-LINER
  T71 gate 2 and T209. Three confident wrong numbers in two days came from
  ad-hoc analysis whose instrument could not have shown a different answer --
  T207 (a grep blind to client-side buttons), A455 (a pattern blind to
  main_func_), A461 (a correlator that assumed a constant lag). None was caught
  by a control; two were caught by the user. An aggregation script that decides
  a ledger claim is a TOOL, so it carries a control that FAILS when it is
  broken, not merely one that passes when it works.

THE CONTROL THAT CAN FAIL
  --self-check builds synthetic [rad] lines whose band totals and medians are
  known by hand, asserts the aggregation reproduces them, AND asserts the
  consistency check FIRES on a line whose b= counts do not sum to n. A checker
  that only ever passes would not discriminate (T65).

SCOPE
  Task-number bands are NOT confirmed scene identity (T101: scene identity has
  been wrong twice from sampling). They are the inherited task ranges A660
  used, and are reported as ranges.
"""
import re
import sys

# A660's bands, inherited verbatim so the two measurements are comparable.
BANDS = [
    (0, 1000, "early/attract"),
    (1000, 2000, "attract"),
    (2000, 3000, "cutscene/transition"),
    (3000, 4000, "transition"),
    (4000, 5000, "tutorial onset"),
    (5000, 6200, "STEADY TUTORIAL"),
]

LINE = re.compile(
    r"^\[rad\] task=(\d+) n=(\d+) neg=(\d+) z=(\d+) bad=(\d+) "
    r"maxexp=(-?\d+) max=(\S+) b=([\d,]+) tot=(\d+)"
)


def parse(lines):
    """-> list of dicts, plus a list of consistency problems."""
    rows, problems = [], []
    for ln in lines:
        m = LINE.match(ln)
        if not m:
            continue
        task, n, neg, z, bad, maxexp, mx, bs, tot = m.groups()
        b = [int(x) for x in bs.split(",")]
        row = dict(task=int(task), n=int(n), neg=int(neg), z=int(z),
                   bad=int(bad), maxexp=int(maxexp), max=float(mx), b=b)
        # The bands are a partition of the positive normals, so they must sum
        # to n exactly. A mismatch means the C side and this parser disagree
        # about what is being counted -- report it, never average over it.
        if sum(b) != row["n"]:
            problems.append(
                f"task {row['task']}: b= sums to {sum(b)} but n={row['n']}")
        rows.append(row)
    return rows, problems


def median(xs):
    if not xs:
        return None
    s = sorted(xs)
    k = len(s) // 2
    return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2


def aggregate(rows, bands=BANDS):
    out = []
    for lo, hi, name in bands:
        sel = [r for r in rows if lo <= r["task"] < hi]
        if not sel:
            out.append(dict(name=name, lo=lo, hi=hi, tasks=0))
            continue
        tot = [0] * 8
        for r in sel:
            for i in range(8):
                tot[i] += r["b"][i]
        n_all = sum(tot)
        out.append(dict(
            name=name, lo=lo, hi=hi, tasks=len(sel),
            med_n=median([r["n"] for r in sel]),
            med_max=median([r["max"] for r in sel]),
            peak_max=max(r["max"] for r in sel),
            med_maxexp=median([r["maxexp"] for r in sel]),
            bands=tot, n_all=n_all,
            # The upper tail is the question A614 poses: the deficit is at the
            # LARGE end, so the share of objects in bands 5-7 (r >= 2^4 = 16)
            # is the number to compare across scenes.
            big=sum(tot[5:]),
            big_pct=(100.0 * sum(tot[5:]) / n_all) if n_all else 0.0,
            zero=sum(r["z"] for r in sel),
            bad=sum(r["bad"] for r in sel),
            neg=sum(r["neg"] for r in sel),
        ))
    return out


def report(agg):
    print(f"{'task range':<13} {'scene (inherited)':<21} {'tasks':>5} "
          f"{'med n':>6} {'med max':>9} {'peak max':>10} {'b5-7':>8} {'b5-7%':>6}")
    for a in agg:
        if not a["tasks"]:
            print(f"{a['lo']}-{a['hi']:<8} {a['name']:<21} {'0':>5}  (no tasks)")
            continue
        print(f"{str(a['lo'])+'-'+str(a['hi']):<13} {a['name']:<21} "
              f"{a['tasks']:>5} {a['med_n']:>6} {a['med_max']:>9.1f} "
              f"{a['peak_max']:>10.1f} {a['big']:>8} {a['big_pct']:>5.1f}%")
    print()
    print("band counts (band k = floor(log2 r) in [4k-16, 4k-12); "
          "b4 = r in [1,16), b5 = [16,256), b6 = [256,4096), b7 = >=4096)")
    print(f"{'scene':<21} " + " ".join(f"{'b'+str(i):>8}" for i in range(8))
          + f" {'zero':>7} {'bad':>5} {'neg':>5}")
    for a in agg:
        if not a["tasks"]:
            continue
        print(f"{a['name']:<21} " + " ".join(f"{c:>8}" for c in a["bands"])
              + f" {a['zero']:>7} {a['bad']:>5} {a['neg']:>5}")


def self_check():
    ok = True

    # (1) KNOWN ANSWER. Two tasks in "attract", one in "STEADY TUTORIAL".
    #     attract:  b totals = [0,0,0,0,3,2,1,0] -> n_all 6, big (b5-7) = 3, 50.0%
    #               med n over (3, 3) = 3; med max over (100.0, 200.0) = 150.0
    #     tutorial: b totals = [0,0,0,0,4,0,0,0] -> n_all 4, big = 0, 0.0%
    syn = [
        "[rad] task=1100 n=3 neg=0 z=1 bad=0 maxexp=6 max=100.0 b=0,0,0,0,2,1,0,0 tot=3",
        "[rad] task=1200 n=3 neg=0 z=0 bad=0 maxexp=9 max=200.0 b=0,0,0,0,1,1,1,0 tot=6",
        "[rad] task=5100 n=4 neg=0 z=0 bad=0 maxexp=2 max=7.0 b=0,0,0,0,4,0,0,0 tot=10",
        "irrelevant line that must be ignored",
    ]
    rows, problems = parse(syn)
    if len(rows) != 3:
        print(f"[self-check] FAIL: parsed {len(rows)} rows, expected 3"); ok = False
    if problems:
        print(f"[self-check] FAIL: clean input reported problems: {problems}"); ok = False

    agg = {a["name"]: a for a in aggregate(rows)}
    checks = [
        ("attract bands", agg["attract"]["bands"], [0, 0, 0, 0, 3, 2, 1, 0]),
        ("attract big", agg["attract"]["big"], 3),
        ("attract big_pct", round(agg["attract"]["big_pct"], 1), 50.0),
        ("attract med n", agg["attract"]["med_n"], 3),
        ("attract med max", agg["attract"]["med_max"], 150.0),
        ("attract peak max", agg["attract"]["peak_max"], 200.0),
        ("attract zero", agg["attract"]["zero"], 1),
        ("tutorial bands", agg["STEADY TUTORIAL"]["bands"], [0, 0, 0, 0, 4, 0, 0, 0]),
        ("tutorial big", agg["STEADY TUTORIAL"]["big"], 0),
        ("tutorial big_pct", agg["STEADY TUTORIAL"]["big_pct"], 0.0),
        ("empty band tasks", agg["transition"]["tasks"], 0),
    ]
    for name, got, want in checks:
        if got != want:
            print(f"[self-check] FAIL: {name}: got {got!r}, want {want!r}"); ok = False

    # (2b) A673: THE STALE-PROBE TRAP MUST BE DETECTED. A log whose [rad] lines
    #      are all zero AND which lacks the unconditional FIRST OBSERVATION line
    #      was recorded without the probe compiled in. Parsing must still yield
    #      rows (so the refusal is main()'s job, not parse()'s), but a caller
    #      relying on totals must be able to see the emptiness.
    stale = ["[rad] task=%d n=0 neg=0 z=0 bad=0 maxexp=0 max=0 "
             "b=0,0,0,0,0,0,0,0 tot=0" % i for i in (1100, 5100)]
    srows, sprob = parse(stale)
    if len(srows) != 2:
        print("[self-check] FAIL: stale-probe lines did not parse"); ok = False
    if sum(r["n"] for r in srows) != 0:
        print("[self-check] FAIL: stale-probe lines should total zero"); ok = False
    if "[rad] FIRST OBSERVATION" in "\n".join(stale):
        print("[self-check] FAIL: the stale fixture must NOT contain the marker, "
              "or it does not exercise the trap"); ok = False

    # (2) THE CONTROL MUST FIRE ON BROKEN INPUT. b= sums to 5, n says 3.
    #     If this passes silently the consistency check is decorative (T65).
    bad_syn = ["[rad] task=1100 n=3 neg=0 z=0 bad=0 maxexp=6 max=100.0 "
               "b=0,0,0,0,4,1,0,0 tot=3"]
    _, problems = parse(bad_syn)
    if not problems:
        print("[self-check] FAIL: inconsistent b= vs n was NOT reported -- "
              "the consistency check cannot fail, so it is not a control")
        ok = False

    # (3) A DELIBERATELY WRONG EXPECTATION MUST NOT PASS. Guards against the
    #     comparison itself being vacuous (e.g. comparing None to None).
    if agg["attract"]["big"] == 999:
        print("[self-check] FAIL: comparison is vacuous"); ok = False

    n_asserts = len(checks) + 6
    print(f"[self-check] {'PASS' if ok else 'FAIL'} "
          f"({n_asserts} assertions: {len(checks)} known-answer, "
          f"1 must-fire-on-broken-input, 3 stale-probe-trap, 2 structural)")
    return 0 if ok else 1


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[1] == "--self-check":
        return self_check()
    with open(argv[1], errors="replace") as fh:
        text = fh.read()
    rows, problems = parse(text.splitlines())
    # A673. THE STALE-PROBE TRAP, found by accident on a672-scene.log. The [rad]
    # line is printed unconditionally by snp_rw_task, so a log recorded with the
    # probe REMOVED from RecompiledFuncs/ still carries 6,169 of them -- all
    # zeros. This tool used to print a full table of 0.0 and exit 0, which reads
    # as "the tutorial submits no objects at any size". That is a confidently
    # wrong answer manufactured by the analysis, which is the T65 failure class.
    # The probe's own FIRST OBSERVATION line is unconditional and independent of
    # both env switches, so its ABSENCE is the discriminator.
    if rows and "[rad] FIRST OBSERVATION" not in text:
        print("[rad_hist] REFUSING: this log has [rad] per-task lines but NO "
              "'[rad] FIRST OBSERVATION' line.\n"
              "  That means the probe was NOT compiled in when the log was recorded "
              "-- the call in RecompiledFuncs/funcs_3.c is absent (it is a generated "
              "file; recompile.sh deletes it, and it is removed after each use).\n"
              "  The per-task lines are printed unconditionally by snp_rw_task and "
              "are ALL ZERO. Reporting them as a distribution would say 'no objects "
              "at any size' when the truth is 'no instrument'.\n"
              "  Re-add the probe, build --no-recomp, and re-run.", file=sys.stderr)
        return 2
    if not rows:
        print("[rad_hist] NO [rad] task= LINES. The run is VOID, not empty of "
              "large objects -- check for the '[rad] FIRST OBSERVATION' line: "
              "if it is absent too, the probe was not compiled in "
              "(recompile.sh regenerates RecompiledFuncs/ and deletes it).",
              file=sys.stderr)
        return 2
    if problems:
        print(f"[rad_hist] {len(problems)} CONSISTENCY PROBLEM(S) -- "
              "band counts disagree with n. Reported, not averaged over:",
              file=sys.stderr)
        for p in problems[:10]:
            print(f"  {p}", file=sys.stderr)
    print(f"[rad_hist] {len(rows)} per-task lines, "
          f"{sum(r['n'] for r in rows)} positive-normal radii")
    report(aggregate(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
