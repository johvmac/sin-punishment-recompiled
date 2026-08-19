#!/usr/bin/env python3
"""Two-tier reader for docs/findings-ledger.md.

WHY
---
The ledger is the VISITED SET, and the rule was "read it in full before
expanding any node". On 2026-08-19 that read cost **83k tokens** (T67) -- every
entry within the length rule, the total still unaffordable. Compression was
already spent (T54) and splitting the file by topic would recreate the journal
problem the ledger exists to solve: one file answers "has this been checked?"
precisely because you ask that question when you do NOT know where to look.

So the file does not change. This is a VIEW over it.

  --index   one line per entry: ID, status tag, claim.   ~6k tokens.
  --show    the full entry, verbatim, for the handful you actually need.

Measured on 2026-08-19: 198 entries, 34,671 words / ~85k tokens in full; the
index is ~2.4k words / ~6k tokens. The index grows ~12 words per entry against
~400 for the file, so it is roughly flat as the ledger keeps growing.

THE RULE THAT MAKES THIS SAFE
-----------------------------
**The index tells you WHETHER something was checked. It never tells you WHAT it
established.** Expand with --show before relying on anything. Citing an index
line instead of the entry would reintroduce exactly the claim-broader-than-the-
evidence failure the ledger was built to prevent -- which is how roughly a dozen
entries went wrong in a single session, all of them citing real evidence.

Usage:
    scripts/ledger.py --index              # replaces "read it in full"
    scripts/ledger.py --show A99 A122      # full entries, verbatim
    scripts/ledger.py --grep overlay       # full entries matching a term
    scripts/ledger.py --open               # the frontier, cost-ranked by route.py
    scripts/ledger.py --wd                 # withdrawn entries (index form)
    scripts/ledger.py --cited-by A54       # what rests on A54
    scripts/ledger.py --self-check         # ALWAYS, before trusting output
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "findings-ledger.md"

ROW = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|")
# An explicit index line, when the extractor cannot do better. Optional; most
# entries never need it. Put it anywhere in the body.
CLAIM_MARKER = re.compile(r"\*\*CLAIM:\*\*\s*(.+?)(?:\*\*|\||$)", re.S)


def _open_re():
    """Share route.py's OPEN predicate -- there were two and both were wrong
    the same way (T66). Fall back rather than fail closed."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_route", ROOT / "scripts" / "route.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.OPEN_RE
    except Exception:
        return re.compile(r"\s*\**OPEN\b", re.I)


OPEN_RE = _open_re()


def parse():
    """Rows as (id, status, body, evidence, raw_line).

    Column counts vary in practice -- 3 to 10 were present on 2026-08-19 --
    because bodies contain pipe characters. So: first cell is the ID, second is
    the status, LAST is the evidence/date, and everything between is body. That
    is stable under the variation; a fixed 4-column split silently dropped 33 of
    198 rows when this was first measured.
    """
    rows = []
    for line in LEDGER.read_text().split("\n"):
        if not ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        eid = cells[0]
        status = cells[1] if len(cells) > 1 else ""
        evidence = cells[-1] if len(cells) > 3 else ""
        body = " | ".join(cells[2:-1]) if len(cells) > 3 else (
            cells[2] if len(cells) > 2 else "")
        rows.append((eid, status, body, evidence, line))
    return rows


def _plain(s):
    return re.sub(r"\s+", " ", re.sub(r"[*`~]", "", s)).strip()


def tag_of(status):
    """The status TAG alone -- MEASURED, WD, OPEN, NEGATIVE(...) -- not the claim."""
    t = _plain(status)
    t = re.split(r"\s+[—-]{1,2}\s+", t)[0]
    t = re.sub(r"\[cost=\d+\]", "", t).strip(" ;,")
    return t[:22]


def claim_of(status, body):
    """One line saying what this entry claims.

    Order matters and is deliberate: an explicit marker beats a heuristic, the
    status cell beats the body (newer entries put the claim there), and a bolded
    span beats a first sentence (this file bolds its claims by habit).
    """
    cands = []

    def add(s):
        s = _plain(s)
        if s:
            cands.append(s)

    m = CLAIM_MARKER.search(body) or CLAIM_MARKER.search(status)
    if m:
        add(m.group(1))

    st = _plain(status)
    # Strip a leading tag so the claim is not "MEASURED — MEASURED ..."
    add(re.sub(r"^[A-Z][A-Z()\w\s]{0,28}?\s+[—-]{1,2}\s+", "", st).strip())
    if st.upper().startswith("MERGED INTO"):
        return st

    for src in (status, body):
        for mm in re.finditer(r"\*\*(.+?)\*\*", src, re.S):
            b = _plain(mm.group(1))
            if b.upper().startswith(("OBSERVED", "FALSIFIER", "CHECKED")):
                continue
            add(b)
            # A SHORT bolded span is a heading, not a claim -- "**The per-frame
            # reset chain.**", "**G6 / ares comparison.**" -- so also offer
            # heading-plus-what-follows. Offered as a CANDIDATE, never returned
            # outright: when the heading ends its cell there is nothing after it,
            # and returning it produced index lines like "UN-WITHDRAWN" and
            # "FIXED, cheaply" that name a topic and assert nothing.
            add(b + " " + _first_words(src[mm.end():], 22))
    # NOT split on ';' -- T4 reads "Overlays share VRAM; the same func_ ... exists
    # in several files", and cutting at the semicolon left three useless words.
    add(re.split(r"(?<=\.)\s+(?=[A-Z*])", _plain(body))[0])
    add(_first_words(body, 22))

    for c in cands:
        if len(c.split()) >= 5:
            return c
    return max(cands, key=len) if cands else st


def _first_words(s, n):
    return " ".join(_plain(s).split()[:n])


def index_lines(rows):
    out = []
    for eid, status, body, _ev, _raw in rows:
        out.append((eid, tag_of(status), claim_of(status, body)))
    return out


def cmd_index(rows, width=118):
    print(f"# findings-ledger INDEX — {len(rows)} entries. "
          f"Tells you WHETHER something was checked, never WHAT it established.")
    print(f"# Expand before relying on anything:  scripts/ledger.py --show <ID> [<ID>...]\n")
    for eid, tag, claim in index_lines(rows):
        print(f"{eid:6} {tag:22} {claim[:width]}")
    return 0


def cmd_show(rows, ids):
    want = {i.upper() for i in ids}
    seen = set()
    for eid, _s, _b, _e, raw in rows:
        if eid.upper() in want:
            seen.add(eid.upper())
            print(raw + "\n")
    missing = want - seen
    if missing:
        print(f"[ledger] no such entry: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    return 0


def cmd_grep(rows, term):
    hits = [r for r in rows if term.lower() in r[4].lower()]
    for r in hits:
        print(r[4] + "\n")
    print(f"[ledger] {len(hits)} entr{'y' if len(hits)==1 else 'ies'} matching {term!r}",
          file=sys.stderr)
    return 0


def cmd_cited_by(rows, target):
    t = target.upper()
    pat = re.compile(rf"\b{re.escape(t)}\b")
    hits = [(eid, tag, claim) for (eid, tag, claim), r in zip(index_lines(rows), rows)
            if eid.upper() != t and pat.search(r[4].upper())]
    print(f"# {len(hits)} entr{'y' if len(hits)==1 else 'ies'} cite {t}. "
          f"If {t} is WITHDRAWN, every one of these needs re-checking.\n")
    for eid, tag, claim in hits:
        print(f"{eid:6} {tag:22} {claim[:110]}")
    return 0


# Controls. Each asserts something a degenerate version of this tool would fail.
# A tool that sits between you and the evidence can lie confidently -- three did
# in one session (T61, T64, T66) -- so this is asserted, not eyeballed.
def self_check():
    rows = parse()
    idx = index_lines(rows)
    raw = LEDGER.read_text()
    checks, bad = [], 0

    n_file = len(re.findall(r"^\|\s*[A-Z]+\d+[a-z]?\s*\|", raw, re.M))
    checks.append(("every entry reaches the index", len(rows) == n_file == len(idx),
                   f"{len(rows)} parsed, {n_file} in file, {len(idx)} indexed"))

    thin = [e for e, _t, c in idx if len(c.split()) < 5
            and not c.upper().startswith("MERGED INTO")]
    checks.append(("no entry indexes to an unusable claim", not thin,
                   f"{len(thin)} thin: {', '.join(thin[:8])}" if thin else "all usable"))

    iw = sum(len(c.split()) + 4 for _e, _t, c in idx)
    fw = len(raw.split())
    checks.append(("index is actually a summary (<25% of the file)", iw < fw * 0.25,
                   f"{iw} words vs {fw} — {100*iw/fw:.1f}%"))

    # Expansion must ADD information. If --show returned the same text as the
    # index, the two tiers would be one tier and this file would be pointless.
    body_only = [r for r in rows if r[0] == "A123"]
    idx_a123 = dict((e, c) for e, _t, c in idx).get("A123", "")
    adds = bool(body_only) and "watch1.log" in body_only[0][4] and "watch1.log" not in idx_a123
    checks.append(("--show adds what --index omits", adds,
                   "A123's evidence path is in the entry, not the index"))

    # The tag must survive into the index. It is the highest-value signal in the
    # file: an entry resting on a WITHDRAWN one is the check that caught B46
    # standing as fact, twice.
    wd = [e for e, t, _c in idx if "WD" in t.upper()]
    checks.append(("WITHDRAWN entries are visibly WD in the index", len(wd) >= 20,
                   f"{len(wd)} marked WD"))

    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:52} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    if not LEDGER.exists():
        print("[ledger] no ledger", file=sys.stderr)
        return 1
    rows = parse()
    cmd = a[0]
    if cmd == "--index":
        return cmd_index(rows)
    if cmd == "--show":
        return cmd_show(rows, a[1:]) if len(a) > 1 else (
            print("[ledger] --show needs at least one ID", file=sys.stderr) or 2)
    if cmd == "--grep":
        return cmd_grep(rows, a[1]) if len(a) > 1 else (
            print("[ledger] --grep needs a term", file=sys.stderr) or 2)
    if cmd == "--cited-by":
        return cmd_cited_by(rows, a[1]) if len(a) > 1 else (
            print("[ledger] --cited-by needs an ID", file=sys.stderr) or 2)
    if cmd == "--open":
        return cmd_index([r for r in rows if OPEN_RE.match(r[1])])
    if cmd == "--wd":
        return cmd_index([r for r in rows if "WD" in tag_of(r[1]).upper()])
    # An unrecognised flag must never fall through to a default action. It did
    # once in route.py and consumed a routing roll (T37).
    print(f"[ledger] unknown argument: {cmd}", file=sys.stderr)
    print(f"[ledger] known: --index --show --grep --open --wd --cited-by "
          f"--self-check --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
