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

  --index   one line per entry: ID, status tag, claim.   ~8.5k tokens.
  --show    the full entry, verbatim, for the handful you actually need.

Measured 2026-08-19, 199 entries: the file is 216k chars / 83k tokens, the index
22k chars / ~8.5k -- about 10x. Do not trust these figures as current; run
--self-check, which asserts the index stays under 25% of the file whatever the
entry count. The point is the GROWTH RATE: ~12 words per entry against ~400, so
the index stays roughly flat as the ledger keeps growing. Every earlier attempt
bought a one-off saving instead (T54), which is why they all expired.

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
    scripts/ledger.py --chain A99          # the correction chain, chronological
    scripts/ledger.py --sowhat 6           # closing sentences of the last 6 entries
    scripts/ledger.py --self-check         # ALWAYS, before trusting output
"""
import functools
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


def _wd_re():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_route_wd", ROOT / "scripts" / "route.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.WD_RE
    except Exception:
        return re.compile(r"\s*\**WD\b", re.I)


WD_RE = _wd_re()


def parse():
    """Rows as (id, status, body, evidence, raw_line).

    Column counts vary in practice -- 3 to 10 were present on 2026-08-19 --
    because bodies contain pipe characters. So: first cell is the ID, second is
    the status, LAST is the evidence/date, and everything between is body. That
    is stable under the variation; a fixed 4-column split silently dropped 33 of
    198 rows when this was first measured.
    """
    from check_ledger import is_non_entry_section   # T131: ONE definition, not two

    rows = []
    skip_section = False
    for line in LEDGER.read_text().split("\n"):
        if line.startswith("## "):
            skip_section = is_non_entry_section(line)
        if skip_section or not ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        eid = cells[0]
        status = cells[1] if len(cells) > 1 else ""
        evidence = cells[-1] if len(cells) > 3 else ""
        body = " | ".join(cells[2:-1]) if len(cells) > 3 else (
            cells[2] if len(cells) > 2 else "")
        rows.append((eid, status, body, evidence, line))
    return rows


# Compiled once. `_plain` runs ~20,000 times per check_ledger invocation, three
# `re.sub` calls each, and it was the single hottest line in the profile at ~20%
# of a 1.27 s run that fires as a hook on EVERY ledger edit. The rest of this
# module already compiles its patterns at module level; this was the outlier.
_MARKUP = re.compile(r"[*`~]")
_WS = re.compile(r"\s+")
_SPACE_PUNCT = re.compile(r"\s+([;,.])")


# MEMOISED, and the honest numbers rather than the flattering ones: MEASURED at
# 4,820 hits against 15,500 misses -- a 24% hit rate worth about 0.03 s of a
# 1.0 s run. Kept because it is free and pure (str in, str out, so caching
# cannot change an answer), NOT because it was the win. The win in this file was
# compiling the three patterns above; the win in check_ledger.py was `is_open`'s
# missing twin. **Most of the 20,320 calls are on DISTINCT strings** -- the
# callers are not re-stripping the same cells nearly as often as the call count
# suggests, which is the thing I assumed and then checked.
# Unbounded is safe here: the key set is the ledger's own cells, already in
# memory, and the process is short-lived.
@functools.lru_cache(maxsize=None)
def _plain(s):
    s = _WS.sub(" ", _MARKUP.sub("", s)).strip()
    return _SPACE_PUNCT.sub(r"\1", s)  # markup removal leaves " ;" behind


STATUS_WORD = re.compile(r"\b(WD|OPEN|MERGED|DEAD|OUT|EST|MEASURED|INTERVENED|READ|INFERRED|NEGATIVE|RETRACTED)\b", re.I)
TAG_PREFIX = re.compile(r"^([A-Z][A-Z()+,/\w\s]{0,48}?)\s+[—-]{1,2}\s+")


def _strip_tag(st):
    """Drop a leading status tag so the claim is not 'MEASURED — MEASURED ...'.

    The prefix must have BALANCED PARENS. Status tags routinely qualify
    themselves -- "MEASURED (hardware watchpoint, 3 runs, identical -- the third
    under the display isolation added in T59)" -- and without this guard the
    match ran into the parenthetical and cut at the em-dash INSIDE it, leaving
    A123 indexed as "the third under the display isolation added in T59) — the
    value A99 dereferences...": a fragment starting mid-clause.
    """
    m = TAG_PREFIX.match(st)
    if not m:
        return st
    pre = m.group(1)
    if pre.count("(") != pre.count(")"):
        return st
    return st[m.end():].strip()


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
    add(_strip_tag(st))
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
        tag, claim = tag_of(status), claim_of(status, body)
        # The I-series puts its CLAIM in the status column rather than a tag, so
        # rendering both gave "ares poll had no posit | ares poll had no positive
        # control -- ...": half the tag column wasted repeating the claim. Blank
        # the tag when it is just the claim's opening.
        # ...but never blank a tag carrying a status keyword. A36's status is
        # "WD [cites the missing A24 — T21]", which IS its own claim, so the
        # duplication rule hid its WD. Losing a WD marking is the single worst
        # thing this index can do: "does anything rest on a withdrawn entry?" is
        # the check that caught B46 standing as fact, twice.
        if tag and claim.lower().startswith(tag.lower()[:12]) and not STATUS_WORD.search(tag):
            tag = ""
        out.append((eid, tag, claim))
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
    seen, shown = set(), []
    allids = {r[0].upper() for r in rows}
    for eid, _s, _b, _e, raw in rows:
        if eid.upper() in want:
            seen.add(eid.upper())
            shown.append(raw)
            print(raw + "\n")
    missing = want - seen
    if missing:
        print(f"[ledger] no such entry: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1

    # CITES footer (T70). On 2026-08-19 rolls #62 and #65 re-derived most of
    # A104 -- the mechanism, both branch arms, and the never-returns
    # observation -- while working A97, whose own text says "See A104, which
    # answered it". The pointer was there and was not followed, twice. A
    # visited set you have to remember to traverse is not a visited set, so
    # --show now names what these entries cite. Unprompted, every time.
    cited = set()
    for raw in shown:
        for m in re.finditer(r"\b([A-Z]{1,2}\d{1,3})\b", raw):
            c = m.group(1).upper()
            if c in allids and c not in want:
                cited.add(c)
    if cited:
        print(f"[ledger] these entries CITE {len(cited)} other(s). Read them before "
              f"deriving anything -- they may already answer it:")
        idx = {e: (t, c) for e, t, c in index_lines(rows)}
        for c in sorted(cited, key=lambda x: (x[0], int(re.sub(r"\D", "", x)))):
            t, cl = idx.get(c, ("", ""))
            print(f"   {c:6} {t:20} {cl[:88]}")
        print(f"[ledger] expand:  scripts/ledger.py --show {' '.join(sorted(cited))}")

    # CITED-BY footer (T129). The CITES footer above is structurally blind to
    # the failure that matters most when you are about to DO something: an
    # entry cannot cite the entry that supersedes it, because that one did not
    # exist yet. A181's named NEXT step was "disassemble around the failing
    # address to decide code-vs-data". A182 did exactly that ONE ROLL LATER,
    # and A207 then measured the follow-on question closed. A181's text still
    # says NEXT, unchanged, because nothing edits an entry when a later one
    # answers it.
    #
    # On 2026-08-20 (roll #136) I read A181, took its NEXT at face value and
    # re-derived A182 in full. Worse, I was heading for a conclusion -- exclude
    # the region from the text range -- that A207 had already MEASURED to be
    # wrong. `--cited-by A181` would have shown A182 on its first line.
    #
    # So the same rule T70 applied to citations applies here: a visited set you
    # have to remember to traverse is not a visited set. Unprompted, every time.
    citedby = {}
    for e in sorted(want):
        who = []
        for r_eid, _s, _b, _e, r_raw in rows:
            rid = r_eid.upper()
            if rid in want:
                continue
            if re.search(rf"\b{re.escape(e)}\b", r_raw):
                who.append(rid)
        if who:
            citedby[e] = who
    if citedby:
        print(f"[ledger] LATER ENTRIES REFER TO WHAT YOU JUST READ. A 'NEXT' step may "
              f"ALREADY BE DONE -- check before running it:")
        idx = {e: (t, c) for e, t, c in index_lines(rows)}
        for e, who in citedby.items():
            for c in who:
                t, cl = idx.get(c, ("", ""))
                print(f"   {e} <- {c:6} {t:20} {cl[:70]}")
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



# The correction verbs, in the forms the ledger actually uses. Kept as one list
# so --chain and the self-check cannot drift apart.
CHAIN_VERBS = (r"CORRECTED(?: IN PART)? by|REFUTED by|WITHDRAWN by|WD (?:IN PART )?"
               r"(?:as to [a-z ]+ )?by|SUPERSEDED by|CLOSED by|UPGRADED by|"
               r"SCOPE-FLAGGED by|ANSWERED by|corrects|refutes|supersedes")


def _roll_of(row):
    """A TOTAL order for chain output. Rolls are the project's real clock, dates
    tie-break, and the ID breaks the remaining ties.

    THE ID COMPONENT IS NOT COSMETIC. Without it, 271 of 302 entries shared a
    (roll, date) key, so `sorted` left them in set-iteration order -- which
    varies with PYTHONHASHSEED BETWEEN PROCESSES. The last-15 window then held
    different entries run to run, the recent-correction rate moved, and the
    circle warning fired or not depending on the hash seed. The self-check
    caught it as an intermittent 9/10 vs 10/10.

    **A tool whose verdict depends on the hash seed is not reproducible
    evidence.** Numeric ID ordering (A9 before A10), not lexicographic.
    """
    m = re.search(r"roll #(\d+)", row[4])
    d = re.search(r"(\d{4}-\d{2}-\d{2})", row[3] or "")
    im = re.match(r"([A-Z]+)(\d+)", row[0])
    ident = (im.group(1), int(im.group(2))) if im else (row[0], 0)
    return (int(m.group(1)) if m else -1, d.group(1) if d else "", ident)


def cmd_chain(rows, target):
    """Chronological correction/citation chain for one entry.

    WHY (T110): A99's third circle ran ~15 rolls because nobody could SEE the
    shape of the argument while it was happening -- which entry corrected which,
    in what order, and how many corrections were corrections-of-corrections.
    Reconstructing that by hand took hours in the 2026-08-20 retrospective. This
    derives the skeleton in a second, so a circle is visible while there is
    still time to break it.

    It is a SKELETON, not a narrative: it says WHO corrected WHOM and WHEN. It
    never says what was established -- same rule as --index (read the entries).
    """
    t = target.upper()
    by_id = {r[0].upper(): r for r in rows}
    if t not in by_id:
        print(f"[ledger] no entry {t}", file=sys.stderr)
        return 2
    idpat = re.compile(r"\b([ABTIL]\d{1,3}[a-z]?)\b")
    verb = re.compile(CHAIN_VERBS, re.I)

    # TRAVERSE THE CORRECTION GRAPH, NOT THE CITATION GRAPH.
    #
    # The first version followed every citation transitively and returned 267 of
    # 296 entries for A99 -- true, useless, and exactly the failure mode a new
    # checker is supposed to surprise you with on day one (T100). Nearly
    # everything cites nearly everything eventually.
    #
    # An edge exists only where a CORRECTION VERB sits within NEAR characters of
    # the citation, i.e. "X corrected/refuted/withdrew Y" -- the relationship the
    # narrative is actually made of. Same windowing principle as check_ledger's
    # withdrawn-citation exemption (T48): a verb anywhere in a 900-word row says
    # nothing about a citation at the other end of it.
    NEAR = 120

    def edges(row):
        out = set()
        for m in idpat.finditer(row[4]):
            x = m.group(1).upper()
            if x == row[0].upper() or x not in by_id:
                continue
            w = row[4][max(0, m.start() - NEAR):m.end() + NEAR]
            if verb.search(w):
                out.add(x)
        return out

    # SEED with the entries that cite the target at DEPTH 1 -- the investigation
    # OF it -- then close over correction edges only. Without the seed the chain
    # stops at entries that correct the target and misses the work done under it
    # (A99's whole 2026-08-20 cluster investigates A99 without correcting it).
    # Without the correction-only closure it returns the entire ledger.
    tpat = re.compile(rf"\b{re.escape(t)}\b")
    seed = {eid for eid, r in by_id.items() if tpat.search(r[4].upper())}
    seen = {t} | seed
    frontier = list(seen)
    while frontier:
        cur = frontier.pop()
        row = by_id.get(cur)
        if row:
            for x in edges(row) - seen:
                seen.add(x); frontier.append(x)
        for eid, r in by_id.items():          # who corrected THIS one
            if eid not in seen and cur in edges(r):
                seen.add(eid); frontier.append(eid)

    chain = sorted((by_id[e] for e in seen), key=_roll_of)
    corrections = 0
    print(f"# CHAIN for {t}: {len(chain)} entries, ordered by roll then date.")
    print(f"# A SKELETON -- who corrected whom and when. It never says what was "
          f"established; read the entries (--show).\n")
    for r in chain:
        roll, date, _ = _roll_of(r)
        tag = tag_of(r[1])[:20]
        corrected = bool(verb.search(r[1]))
        corrections += corrected
        mark = "  <-- corrected/withdrawn" if corrected else ""
        rl = f"#{roll}" if roll >= 0 else "--"
        print(f"{r[0]:6} roll {rl:>5}  {date:10}  {tag:20}{mark}")
    # A LIFETIME AVERAGE HIDES A CIRCLE. Circles are LOCAL: A99's whole chain
    # averages ~26% corrections, while its third circle (rolls #84-#103) was far
    # denser. Averaging over three days dilutes exactly the signal that matters,
    # so the recent window is reported separately and is what triggers the
    # warning. "Am I circling?" is a question about now, not about the mean.
    WIN = 15
    recent = chain[-WIN:] if len(chain) > WIN else chain
    rc = sum(1 for r in recent if verb.search(r[1]))
    print(f"\n# {corrections} of {len(chain)} entries carry a correction verb "
          f"({100*corrections//max(len(chain),1)}% lifetime).")
    print(f"# Last {len(recent)}: {rc} corrections ({100*rc//max(len(recent),1)}% recent).")
    if len(recent) >= 6 and rc * 3 >= len(recent):
        print("#\n# **A THIRD OR MORE OF THE RECENT WINDOW IS CORRECTIONS. That is the shape "
              "of a circle.**\n# Apply the IMPOSSIBLE-RESULT RULE before the next experiment: "
              "enumerate the premises\n# under the disagreement and attack the least-verified "
              "one -- do NOT run another\n# experiment under them (T107). A99's third circle "
              "cost ~15 rolls to a premise\n# that fell in two greps.")
    return 0

# Controls. Each asserts something a degenerate version of this tool would fail.
# A tool that sits between you and the evidence can lie confidently -- three did
# in one session (T61, T64, T66) -- so this is asserted, not eyeballed.
def self_check():
    rows = parse()
    idx = index_lines(rows)
    raw = LEDGER.read_text()
    checks, bad = [], 0

    # An INDEPENDENT count -- it deliberately does not call parse(), so it can
    # cross-check it. T131 made it section-aware the same way rather than by
    # importing parse()'s result, which would have made it agree by construction.
    from check_ledger import is_non_entry_section
    n_file, _skip = 0, False
    for _ln in raw.split("\n"):
        if _ln.startswith("## "):
            _skip = is_non_entry_section(_ln)
        if not _skip and re.match(r"^\|\s*[A-Z]+\d+[a-z]?\s*\|", _ln):
            n_file += 1
    checks.append(("every entry reaches the index", len(rows) == n_file == len(idx),
                   f"{len(rows)} parsed, {n_file} in file, {len(idx)} indexed"))

    # T131, AND IT IS THE DISCRIMINATING ONE FOR THAT CHANGE: the user-queue
    # rows look exactly like entries (`| U1 | LIVE ... |`) and must NOT be
    # parsed as findings, or they land in every audit denominator. Verified to
    # FAIL by making is_non_entry_section return False, which restores 405.
    q_ids = {r[0] for r in rows if re.match(r"^U\d+$", r[0])}
    checks.append(("user-queue rows are NOT parsed as ledger entries",
                   not q_ids and "## THE USER QUEUE" in raw,
                   f"{len(q_ids)} queue row(s) leaked into the entry set"
                   if q_ids else "queue section present, 0 rows leaked"))

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
    # EXACT, not a floor. This was `>= 20` and passed while A36's WD was hidden
    # by a cosmetic rule -- a control with that much slack cannot detect the
    # drift it exists to detect (T65).
    # Same anchored predicate as route.py/check_ledger.py. A bare \bWD\b search
    # counted T72 -- whose status says "A138 is the WD entry, not this one" --
    # and made this tool disagree with check_ledger about the count.
    raw_wd = {r[0] for r in rows if WD_RE.match(r[1])}
    shown = {e for e, t, _c in idx if "WD" in t.upper()}
    checks.append(("every WITHDRAWN entry is visibly WD in the index",
                   raw_wd == shown and len(raw_wd) > 0,
                   f"{len(shown)}/{len(raw_wd)} shown"
                   + (f"; HIDDEN: {', '.join(sorted(raw_wd - shown))}" if raw_wd - shown else "")))

    # The CITES footer must actually fire (T70). A97's text says "See A104,
    # which answered it"; two rolls re-derived A104 anyway. A reminder that
    # does not appear is not a reminder -- the T56 shape.
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_show(rows, ["A97"])
    out = buf.getvalue()
    # Key off the footer's OWN line, not the whole output. The first version of
    # this check split on "CITE" and searched the tail -- with the footer
    # disabled, split returns the entire string, and A97's body says "See A104",
    # so it passed either way. A control that cannot fail is not a control
    # (T65), and this one was written minutes after recording T70.
    expand = [l for l in out.splitlines() if l.startswith("[ledger] expand:")]
    ok = bool(expand) and "A104" in expand[0]
    checks.append(("--show names the entries it cites", ok,
                   "A97's footer lists A104" if ok else "footer absent or missing A104"))

    # --- --chain (T110) ----------------------------------------------------
    # THE CONTROL THAT MATTERS IS THE BOUND. The first version followed every
    # citation transitively and returned 267 of 296 entries for A99 -- true,
    # useless, and caught only because the output was obviously absurd. A chain
    # that returns most of the ledger is not a chain.
    import io as _io, contextlib as _ctx
    def _chain(tid):
        buf = _io.StringIO()
        with _ctx.redirect_stdout(buf):
            rc = cmd_chain(rows, tid)
        return rc, buf.getvalue()

    rc_c, out_c = _chain("A99")
    _m = re.search(r"CHAIN for A99: (\d+) entries", out_c)
    n_chain = int(_m.group(1)) if _m else 10**6
    checks.append((f"--chain is BOUNDED (A99 -> {n_chain} of {len(rows)})",
                   rc_c == 0 and n_chain < len(rows) * 0.5,
                   f"{n_chain} entries; one returning most of the ledger is not a chain"))

    # It must reach the RECENT work, not stop at the last entry that happens to
    # correct the target. A99's 2026-08-20 cluster investigates it without
    # correcting it, and that is the part a live reader needs.
    checks.append(("--chain reaches the most recent work on the target",
                   "roll  #10" in out_c or "roll  #9" in out_c,
                   "reaches the latest rolls" if ("roll  #10" in out_c or "roll  #9" in out_c)
                   else "stops before the latest rolls"))

    # DISCRIMINATION, both directions: the circle warning must fire on a dense
    # chain and stay silent on a sparse one. A warning that always fires is
    # noise, and noise is how a discipline stops being read (T29).
    _, out_a97 = _chain("A97")
    fires99 = "shape of a circle" in out_c
    fires97 = "shape of a circle" in out_a97
    checks.append(("circle warning fires on A99, silent on A97 (discriminates)",
                   fires99 and not fires97, f"A99={fires99}, A97={fires97}"))

    # DETERMINISM. `--chain`'s verdict must not depend on PYTHONHASHSEED. It did:
    # 271 of 302 entries shared a (roll, date) key, `sorted` left them in
    # set-iteration order, and the last-15 window -- hence the circle warning --
    # changed between processes. Caught as an intermittent 9/10 vs 10/10. A tool
    # whose verdict depends on the hash seed is not reproducible evidence.
    _keys = [_roll_of(r) for r in rows]
    checks.append(("--chain's sort key is TOTAL (no PYTHONHASHSEED dependence)",
                   len(set(_keys)) == len(_keys),
                   f"{len(_keys) - len(set(_keys))} tied keys would sort nondeterministically"))

    # An unknown ID must refuse, never return an empty chain that reads as
    # "nothing corrected this".
    rc_bad, _ = _chain("ZZ999")
    checks.append(("--chain refuses an unknown ID", rc_bad == 2, f"rc={rc_bad}, want 2"))

    # CITED-BY footer (T129). THE NEGATIVE HALF IS THE LOAD-BEARING ONE: a
    # footer that printed for every entry would be wallpaper within a day (T29)
    # and indistinguishable from one that always fires. So this asserts BOTH
    # that a superseded entry surfaces its successor AND that the newest entry
    # -- which nothing can yet refer to -- surfaces nothing.
    import io as _io
    from contextlib import redirect_stdout as _rso

    def _show(eid):
        buf = _io.StringIO()
        with _rso(buf):
            cmd_show(rows, [eid])
        return buf.getvalue()

    _a181 = _show("A181")
    checks.append(("--show surfaces LATER entries that refer to what you read",
                   "LATER ENTRIES REFER" in _a181 and "A182" in _a181,
                   "A181 must surface A182, which performed its NEXT step"))

    # An entry with NO referrers -- found by searching, not by assuming.
    #
    # This used to take the newest row on the premise that nothing can refer to
    # it yet. **That premise broke the first time an entry cited a NEWER one:**
    # I18 (in the defects table, near the end of the file) cites A264 (top of
    # the main table), so "newest" and "unreferenced" came apart and the control
    # failed on a healthy tool. Same shape as the A99 circle control T124
    # records -- an expectation frozen on a circumstance rather than computed.
    # Now it picks a genuinely unreferenced entry, and REFUSES if none exists
    # rather than quietly having nothing to test.
    _unref = next((r[0].upper() for r in rows
                   if "LATER ENTRIES REFER" not in _show(r[0].upper())), None)
    checks.append(("--show stays SILENT when nothing refers to the entry",
                   _unref is not None,
                   f"{_unref} has no referrers and produced no footer"
                   if _unref else "NO unreferenced entry exists — the control "
                                  "has nothing to discriminate against"))

    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:52} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def cmd_sowhat(rows, n):
    """Print the closing sentences of the last `n` entries, newest last.

    WHY THIS EXISTS (T124)
    ----------------------
    T120 moved the checkpoint-closing sentence INTO the entry so something
    could check it was written. It is checked, and it is written -- and on
    2026-08-20 six consecutive entries were written with good ones and NONE of
    them reached the user, because that stretch was user-directed work rather
    than a rolled checkpoint and nothing prompted a summary.

    The record was fine. The REPORTING was not, and no checker can see chat.
    What can be mechanised is the RETRIEVAL: closing any chunk of work should
    be one command, not an act of memory. Newest LAST so it reads in the order
    the work happened, and so the final line is the one to close on.
    """
    # parse() returns a LIST of (id, status, body, evidence, raw), not a dict --
    # checked rather than assumed, after assuming wrong once.
    #
    # ORDER IS FILE ORDER, NOT ID ORDER. Sorting by (prefix, number) groups all
    # the A-entries then all the T-entries, so "the last 3" returned three
    # T-entries regardless of what was actually written most recently. The
    # ledger is newest-first on disk, which is the real chronology.
    ids = [(0, 0, r) for r in rows if re.match(r"[A-Z]+\d+", r[0])]
    tail = list(reversed(ids[:n]))
    print(f"# closing sentences, last {len(tail)} entries, oldest first\n")
    missing = []
    for _pre, _num, r in tail:
        eid = r[0]
        blob = r[1] + " " + r[2]
        got = None
        for mm in re.finditer(r"SO WHAT:\s*(.+?)(?:\*\*|\||$)", blob, re.S):
            t = mm.group(1).strip()
            if t.startswith("<") or (mm.start() > 0 and blob[mm.start() - 1] == "`"):
                continue
            got = t
        if got:
            print(f"  {eid}: {got}\n")
        else:
            missing.append(eid)
    if missing:
        print(f"# NO closing sentence: {', '.join(missing)} -- check_ledger will ask.")
    return 0


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
    if cmd == "--sowhat":
        try:
            n = int(a[1]) if len(a) > 1 else 8
        except ValueError:
            print("[ledger] --sowhat takes a count", file=sys.stderr)
            return 2
        return cmd_sowhat(rows, n)
    if cmd == "--chain":
        return (cmd_chain(rows, a[1]) if len(a) > 1 else
                (print("[ledger] --chain needs an ID", file=sys.stderr) or 2))
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
    print(f"[ledger] known: --index --show --grep --open --wd --cited-by --chain "
          f"--self-check --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
