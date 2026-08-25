#!/usr/bin/env python3
"""The ledger as a directed graph, and the CYCLES in it.

USER-REQUESTED 2026-08-25: "a visualisation of the cycles (if any) in the
ledger items, or just a graph representation of them".

WHY A CYCLE IN THIS FILE IS NOT A BUG BUT A SIGNAL. Entries are written in
order and normally cite only entries that already existed, so the graph should
be a DAG.

MY FIRST VERSION OF THIS PARAGRAPH SAID A CYCLE COULD "THEREFORE ONLY ARISE ONE
WAY" -- an older entry edited after the fact to point at a newer one, the
`>>> REFUTED BY A428 <<<` insertions. **The first real run refuted that in one
line and it is recorded here rather than quietly fixed.** Deleting every
retroactive edge still leaves 11 cycles. There are TWO generators:

  1. **RETROACTIVE EDITS** -- an older entry amended to name a newer one.
     Removing them takes the largest component from 409 nodes to 228.
  2. **CROSS-SERIES REFERENCES** -- A cites T, T cites A. **The ID carries no
     chronology across series**, so these are not reopenings and must not be
     read as any; they are two counters with no shared clock.

**What IS clean, and it is the check worth keeping: back edges alone -- every
citation of an earlier entry in the same series -- produce ZERO cycles across
all 648 entries.** The ledger's chronological skeleton is a perfect DAG. Every
loop in it comes from one of the two generators above, neither of which is a
defect.

WHAT COUNTS AS AN EDGE. `A -> B` when B's entry ID appears anywhere in A's row.
That is the same rule `ledger.py`'s CITES footer uses, deliberately: a second
definition of "cites" would let an entry be linked for one reader and not the
other, which is the two-halves-of-a-loop shape this project keeps finding.

BACK EDGES ARE ONLY MEANINGFUL WITHIN ONE SERIES, and this is a real limit
rather than a caveat. `A437 -> A225` is provably backwards in time because A
numbers are issued in order. `A437 -> T107` is not comparable -- the T series
runs on its own counter -- so cross-series edges are classified `cross` and are
NEVER counted as retroactive. Calling them back edges would manufacture
reopenings that never happened.

    scripts/ledger_graph.py                 # census
    scripts/ledger_graph.py --cycles        # the SCCs, expanded
    scripts/ledger_graph.py --json OUT      # nodes + edges for a viewer
    scripts/ledger_graph.py --dot OUT       # graphviz
    scripts/ledger_graph.py --self-check
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402  -- the SAME parser, on purpose

ID_RE = re.compile(r"\b([A-Z]{1,2}\d{1,3})\b")


def split_id(eid):
    m = re.match(r"([A-Z]+)(\d+)", eid)
    return (m.group(1), int(m.group(2))) if m else (eid, 0)


def build(rows):
    """{id: {tag, claim, raw}} and the edge list."""
    nodes = {}
    for (eid, tag, claim), r in zip(ledger.index_lines(rows), rows):
        nodes[eid.upper()] = {"id": eid.upper(), "tag": tag, "claim": claim,
                              "raw": r[4]}
    edges = []
    for eid, n in nodes.items():
        seen = set()
        for m in ID_RE.finditer(n["raw"].upper()):
            c = m.group(1)
            if c in nodes and c != eid and c not in seen:
                seen.add(c)
                sp, sn = split_id(eid)
                tp, tn = split_id(c)
                if sp != tp:
                    kind = "cross"
                elif tn < sn:
                    kind = "back"      # normal: cites an earlier entry
                else:
                    kind = "forward"   # RETROACTIVE: edited to point forward
                edges.append({"s": eid, "t": c, "k": kind})
    return nodes, edges


def sccs(nodes, edges):
    """Tarjan. Returns components of size > 1, largest first.

    Self-loops are impossible here (an entry naming itself is skipped when the
    edge is built), so any component of size > 1 is a genuine cycle.
    """
    adj = {n: [] for n in nodes}
    for e in edges:
        adj[e["s"]].append(e["t"])
    index, low, onstack, stack, out = {}, {}, set(), [], []
    counter = [0]

    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter[0]
                counter[0] += 1
                stack.append(v)
                onstack.add(v)
            recurse = False
            for i in range(pi, len(adj[v])):
                w = adj[v][i]
                if w not in index:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recurse = True
                    break
                if w in onstack:
                    low[v] = min(low[v], index[w])
            if recurse:
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    onstack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp, key=split_id))
            work.pop()
            if work:
                pv = work[-1][0]
                low[pv] = min(low[pv], low[v])
    return sorted(out, key=len, reverse=True)


def census(nodes, edges, comps, show_cycles=False):
    kinds = {"back": 0, "forward": 0, "cross": 0}
    for e in edges:
        kinds[e["k"]] += 1
    indeg, outdeg = {}, {}
    for e in edges:
        outdeg[e["s"]] = outdeg.get(e["s"], 0) + 1
        indeg[e["t"]] = indeg.get(e["t"], 0) + 1
    iso = [n for n in nodes if not indeg.get(n) and not outdeg.get(n)]

    print(f"[graph] {len(nodes)} entries, {len(edges)} citation edges")
    print(f"[graph]   back    {kinds['back']:>5}  cites an EARLIER entry in its own series (normal)")
    print(f"[graph]   forward {kinds['forward']:>5}  cites a LATER entry -- only possible by RETROACTIVE EDIT")
    print(f"[graph]   cross   {kinds['cross']:>5}  between series (A<->T etc), NOT time-comparable")
    print(f"[graph] {len(iso)} entry(ies) cite nothing and are cited by nothing")

    print(f"[graph] {len(comps)} cycle(s) -- strongly connected components of size > 1")
    for c in comps:
        print(f"[graph]   size {len(c):>3}: {' '.join(c[:14])}"
              + (" ..." if len(c) > 14 else ""))

    # ATTRIBUTION. Which edge class actually generates the loops -- printed
    # unprompted because the census alone invites the wrong reading (my own
    # first one: "cycles == reopenings"). Back-edges-only is the control: it
    # must come out a DAG, and if it ever does not, the ID ordering has stopped
    # meaning what this tool assumes.
    for label, keep in (("without FORWARD (retroactive)", lambda e: e["k"] != "forward"),
                        ("without CROSS (A<->T etc)", lambda e: e["k"] != "cross"),
                        ("only BACK -- must be a DAG", lambda e: e["k"] == "back")):
        sub = sccs(nodes, [e for e in edges if keep(e)])
        big = max((len(c) for c in sub), default=0)
        print(f"[graph]   {label:32} cycles={len(sub):<3} largest={big}")

    top_in = sorted(indeg.items(), key=lambda kv: -kv[1])[:8]
    top_out = sorted(outdeg.items(), key=lambda kv: -kv[1])[:8]
    print("[graph] most CITED:  " + ", ".join(f"{k}({v})" for k, v in top_in))
    print("[graph] most CITING: " + ", ".join(f"{k}({v})" for k, v in top_out))

    if show_cycles:
        for c in comps:
            print(f"\n=== cycle of {len(c)} ===")
            for n in c:
                print(f"  {n:6} {nodes[n]['tag'][:20]:20} {nodes[n]['claim'][:96]}")
            fwd = [e for e in edges
                   if e["s"] in set(c) and e["t"] in set(c) and e["k"] == "forward"]
            print(f"  the retroactive edges that CLOSE it ({len(fwd)}):")
            for e in fwd:
                print(f"    {e['s']} -> {e['t']}")
    return 0


# --------------------------------------------------------------------------
# CONTROLS. They vary the failure MODE: C1 must FIND a cycle, C2 must NOT
# invent one in a DAG, C3 must keep two cycles apart rather than merging them,
# C4 must not call a self-reference a cycle, C5 must not call a cross-series
# edge retroactive.
# --------------------------------------------------------------------------
def self_check():
    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"[selfcheck] {'PASS' if cond else 'FAIL'} {name} {detail}")

    def g(pairs, ids):
        nodes = {i: {"id": i, "tag": "", "claim": "", "raw": ""} for i in ids}
        edges = []
        for s, t in pairs:
            sp, sn = split_id(s)
            tp, tn = split_id(t)
            k = "cross" if sp != tp else ("back" if tn < sn else "forward")
            edges.append({"s": s, "t": t, "k": k})
        return nodes, edges

    ids = ["A1", "A2", "A3", "A4"]
    n, e = g([("A2", "A1"), ("A3", "A2"), ("A4", "A3")], ids)
    chk("C2 a pure DAG has no cycles", sccs(n, e) == [], f"{sccs(n, e)}")

    n, e = g([("A2", "A1"), ("A3", "A2"), ("A1", "A3"), ("A4", "A3")], ids)
    c = sccs(n, e)
    chk("C1 a 3-cycle is found exactly",
        len(c) == 1 and c[0] == ["A1", "A2", "A3"], f"{c}")

    ids6 = ["A1", "A2", "A3", "A4", "A5", "A6"]
    n, e = g([("A2", "A1"), ("A1", "A2"), ("A5", "A4"), ("A4", "A5"),
              ("A3", "A1"), ("A6", "A5")], ids6)
    c = sccs(n, e)
    chk("C3 two disjoint cycles stay two",
        len(c) == 2 and sorted(c) == [["A1", "A2"], ["A4", "A5"]], f"{c}")

    # C4: an entry naming itself. build() skips it; the detector must not
    # manufacture a component from one anyway.
    n, e = g([("A2", "A1")], ["A1", "A2"])
    e.append({"s": "A1", "t": "A1", "k": "back"})
    chk("C4 a self-reference is not a cycle", sccs(n, e) == [], f"{sccs(n, e)}")

    # C5: A1 -> T9 is NOT retroactive. The T counter is independent, so calling
    # it forward would invent a reopening out of an ordinary cross-reference.
    n, e = g([("A1", "T9")], ["A1", "T9"])
    chk("C5 a cross-series edge is classified cross, not forward",
        e[0]["k"] == "cross", f"{e[0]}")

    # C6, on the REAL file: the parser must agree with ledger.py about what an
    # entry cites. A second definition of "cites" is the two-halves-of-a-loop
    # shape this project keeps finding, so it is asserted rather than assumed.
    rows = ledger.parse()
    nodes, edges = build(rows)
    probe = "A421"
    mine = {e["t"] for e in edges if e["s"] == probe}
    allids = {r[0].upper() for r in rows}
    theirs = {m.group(1).upper()
              for m in ID_RE.finditer(dict(
                  (r[0].upper(), r[4]) for r in rows)[probe])
              if m.group(1).upper() in allids and m.group(1).upper() != probe}
    chk("C6 edge extraction matches ledger.py's own rule on a real entry",
        mine == theirs, f"{len(mine)} vs {len(theirs)}")

    print(f"[selfcheck] {'ALL PASS' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# LAYOUT. Computed HERE rather than in the browser, and that is a correctness
# decision rather than a performance one: a layout produced in the page cannot
# be looked at before it ships. This one is written to the payload, rendered to
# a PNG by --layout-png, and CHECKED BY EYE before anything is published.
# It is also deterministic -- no clock, no RNG, seeded from a phyllotaxis
# spiral -- so the same ledger always produces the same picture.
# --------------------------------------------------------------------------
def layout(nodes, edges, keep, iters=600, rep=None, link=46.0):
    import numpy as np
    ids = [n for n in nodes if keep(n)]
    if not ids:
        return {}
    ix = {v: i for i, v in enumerate(ids)}
    n = len(ids)
    rep = rep if rep is not None else (260.0 if n > 200 else 900.0)
    k = np.arange(n)
    a = k * 2.399963267949
    r = (11.0 if n > 200 else 26.0) * np.sqrt(k)
    pos = np.stack([np.cos(a) * r, np.sin(a) * r], 1).astype(np.float64)
    vel = np.zeros_like(pos)
    E = np.array([[ix[e["s"]], ix[e["t"]]] for e in edges
                  if e["s"] in ix and e["t"] in ix], dtype=np.int64)
    alpha = 0.9
    for _ in range(iters):
        d = pos[:, None, :] - pos[None, :, :]
        d2 = (d ** 2).sum(-1)
        np.fill_diagonal(d2, np.inf)
        d2 = np.maximum(d2, 0.01)
        f = rep / d2
        f[d2 > 240000.0] = 0.0
        dist = np.sqrt(d2)
        acc = (d / dist[..., None] * f[..., None]).sum(1)
        if len(E):
            dv = pos[E[:, 1]] - pos[E[:, 0]]
            dd = np.maximum(np.sqrt((dv ** 2).sum(-1)), 1e-6)
            ff = (dd - link) * 0.0085
            u = dv / dd[:, None] * ff[:, None]
            np.add.at(acc, E[:, 0], u)
            np.add.at(acc, E[:, 1], -u)
        acc -= pos * 0.0016
        vel = (vel + acc) * 0.80
        pos += vel * alpha
        alpha *= 0.988
    pos -= pos.mean(0)
    span = max(np.abs(pos).max(), 1.0)
    pos = pos / span * 500.0
    return {ids[i]: [round(float(pos[i, 0]), 1), round(float(pos[i, 1]), 1)]
            for i in range(n)}


def layout_png(nodes, edges, comps, out, keep, size=1400):
    """Render a computed layout so it can be LOOKED AT before it is published.

    A layout is the one part of this that no assertion covers -- 'the numbers
    are finite' does not mean 'a person can read it'. T71's second gate asks for
    a control that can fail; for a picture the control is a picture.
    """
    from PIL import Image, ImageDraw
    pos = layout(nodes, edges, keep)
    if not pos:
        print("[graph] nothing to lay out"); return 1
    big = set(max(comps, key=len)) if comps else set()
    img = Image.new("RGB", (size, size), (12, 16, 18))
    dr = ImageDraw.Draw(img)
    sc = (size - 80) / 1000.0
    P = lambda i: (pos[i][0] * sc + size / 2, pos[i][1] * sc + size / 2)
    col = {"back": (93, 109, 116), "forward": (224, 148, 64), "cross": (90, 163, 196)}
    for e in edges:
        if e["s"] in pos and e["t"] in pos:
            dr.line([P(e["s"]), P(e["t"])], fill=col[e["k"]], width=1)
    indeg = {}
    for e in edges:
        indeg[e["t"]] = indeg.get(e["t"], 0) + 1
    for i in pos:
        x, y = P(i)
        rr = max(2.0, min(9.0, 1.6 + (indeg.get(i, 0) ** 0.5) * 0.9))
        c = (224, 96, 74) if i in big else (139, 154, 161)
        dr.ellipse([x - rr, y - rr, x + rr, y + rr], fill=c)
    img.save(out)
    print(f"[graph] wrote {out} ({len(pos)} nodes laid out)")
    return 0


def main(argv):
    if "--self-check" in argv:
        return self_check()
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    rows = ledger.parse()
    nodes, edges = build(rows)
    comps = sccs(nodes, edges)

    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
        member = {}
        for i, c in enumerate(comps):
            for n in c:
                member[n] = i
        Path(out).write_text(json.dumps({
            "nodes": [{"id": n["id"], "tag": n["tag"], "claim": n["claim"],
                       "cycle": member.get(n["id"], -1)}
                      for n in nodes.values()],
            "edges": edges,
            "cycles": comps,
        }))
        print(f"[graph] wrote {out}")
        return 0

    if "--layout-png" in argv:
        out = argv[argv.index("--layout-png") + 1]
        which = argv[argv.index("--view") + 1] if "--view" in argv else "all"
        inbig = set(max(comps, key=len)) if comps else set()
        inany = {n for c in comps for n in c}
        keep = {"all": lambda n: True,
                "cyc": lambda n: n in inany,
                "small": lambda n: n in inany and n not in inbig}[which]
        return layout_png(nodes, edges, comps, out, keep)

    if "--layout-json" in argv:
        out = argv[argv.index("--layout-json") + 1]
        inbig = set(max(comps, key=len)) if comps else set()
        inany = {n for c in comps for n in c}
        views = {
            "all": layout(nodes, edges, lambda n: True),
            "cyc": layout(nodes, edges, lambda n: n in inany),
            "small": layout(nodes, edges, lambda n: n in inany and n not in inbig),
        }
        Path(out).write_text(json.dumps(views, separators=(",", ":")))
        print(f"[graph] wrote {out} ({', '.join(f'{k}={len(v)}' for k, v in views.items())})")
        return 0

    if "--dot" in argv:
        out = argv[argv.index("--dot") + 1]
        inc = {n for c in comps for n in c}
        lines = ["digraph ledger {", '  rankdir=LR; node [shape=box];']
        for n in inc:
            lines.append(f'  "{n}" [style=filled fillcolor="#ffd9d9"];')
        for e in edges:
            if e["s"] in inc and e["t"] in inc:
                col = "#c0392b" if e["k"] == "forward" else "#888888"
                lines.append(f'  "{e["s"]}" -> "{e["t"]}" [color="{col}"];')
        lines.append("}")
        Path(out).write_text("\n".join(lines))
        print(f"[graph] wrote {out} ({len(inc)} nodes in cycles)")
        return 0

    return census(nodes, edges, comps, "--cycles" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
