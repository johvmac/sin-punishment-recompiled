#!/usr/bin/env python3
"""Structural checks on docs/findings-ledger.md.

WHY
---
About a dozen ledger entries were wrong in a single session on 2026-08-18. None
failed for lack of evidence -- every one cited real evidence, correctly
gathered. They failed because the CLAIM WAS BROADER THAN THE EVIDENCE.

This script cannot check that. No script can: a required field forces presence,
never truth, and "falsifier: none obvious" passes any validator. What it CAN do
is catch the STRUCTURAL half, which was a real chunk of the damage and needs no
judgement at all:

  1. Negatives with no stated scope.  "nothing calls this" was true of splat's
     asm and false of the ROM. Four failures, including a day spent believing a
     working probe was broken.
  2. Load-bearing claims missing a field.  Observed / Falsifier / Checked.
  3. Entries resting on a WITHDRAWN entry.  The highest-value check and the one
     that is not about discipline at all: B46 rested on B41, B41 was withdrawn,
     and B46 stayed standing as fact until someone happened to notice. Twice.
  4. Duplicate IDs.  Incremental edits produced six of them in one session.

Findings are WARNINGS, not gates. This is an attention-director; the judgement
stays with the reader. Exit 1 only with --strict.

Usage:
    scripts/check_ledger.py                 # check, print, exit 0
    scripts/check_ledger.py --strict        # exit 1 if anything is flagged
    scripts/check_ledger.py --hook          # read a Claude Code hook payload on
                                            # stdin; run only if the edited file
                                            # was the ledger. Exits 2 with the
                                            # report on stderr so it is surfaced.
"""
import datetime as _dt
import json
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "docs" / "findings-ledger.md"


# WHAT MAKES A CLOSING SENTENCE "PLAIN" (T120/T121).
#
# MODULE LEVEL, AND IMPORTED BY `session.py` RATHER THAN COPIED. Two definitions
# of the same rule is the failure the single-run check already warns about --
# entries would pass one checker and fail the other, and nobody would be able to
# say which was authoritative. One list, one meaning.
PLAIN_LANGUAGE_JARGON = [
    (r"0[xX][0-9A-Fa-f]{2,}", "an address"),
    (r"\b[ATBI]\d{1,3}\b", "an entry ID"),
    (r"scripts/|\.py\b|\.sh\b|\.log\b|\.toml\b|\.c:\d|\bgdb\b", "a tool or filename"),
    (r"ctx->|\$[a-z]\d|\$sp\b|\$ra\b", "a register or generated-code expression"),
]


# WHAT COUNTS AS ONE ENTRY CORRECTING ANOTHER (T123).
#
# MODULE LEVEL AND SHARED, for the same reason `not_plain` is: audit.py needs
# the identical vocabulary to decide whether a flagged entry has been
# superseded, and two definitions of "corrected" would let an entry be live for
# one checker and dead for the other.
SUPERSEDES_RE = re.compile(
    r"(supersed|replaces|corrects|refut|retract|too coarse|withdr|~~"
    r"|upgraded by|reframed by|split by|closed by|vindicat)", re.I)


def superseded_by_later(eid, rows):
    """Does a LATER entry name `eid` next to a correction word?

    `rows` is check_ledger's {id: (tag, body, line)}. Order is by ID number
    within a prefix -- the ledger is newest-first, so "later" means a HIGHER
    number, which is how every other check here reads succession.
    """
    m = re.match(r"([A-Z]+)(\d+)", eid)
    if not m:
        return None
    pre, num = m.group(1), int(m.group(2))
    for other, val in rows.items():
        om = re.match(r"([A-Z]+)(\d+)", other)
        if not om or om.group(1) != pre or int(om.group(2)) <= num:
            continue
        blob = val[0] + " " + val[1]
        for hit in re.finditer(re.escape(eid) + r"\b", blob):
            lo = max(0, hit.start() - 220)
            if SUPERSEDES_RE.search(blob[lo:hit.end() + 220]):
                return other
    return None


def not_plain(sentence):
    """Return what makes `sentence` jargon, or None if it reads as plain language."""
    for pat, what in PLAIN_LANGUAGE_JARGON:
        if re.search(pat, sentence):
            return what
    return None


def is_open(tag):
    """Is this status cell tagged OPEN -- as opposed to merely containing the word?

    ONE definition, imported from route.py, because there were two and they were
    both wrong in the same way (T66). route.py put A124 on the frontier for
    saying "answers A99's open question"; this script then flagged T66 as an
    unpriced OPEN row for saying route.py "decided which items were OPEN by
    substring". The tool that ranks the work and the tool that checks the ledger
    must agree on what OPEN means, or the checker reports defects in rows the
    ranker never sees.

    Falls back to a local copy if route.py is unavailable -- this script runs as
    a git hook and must not fail closed on an import.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_route", Path(__file__).resolve().parent / "route.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        globals()["is_open"] = lambda t: bool(mod.OPEN_RE.match(t))
    except Exception:
        globals()["is_open"] = lambda t: bool(re.match(r"\s*\**OPEN\b", t, re.I))
    return globals()["is_open"](tag)

_WD_MATCH = None


def is_withdrawn(tag):
    """Is this status cell TAGGED withdrawn, as opposed to mentioning "WD"?

    Anchored for the same reason `is_open` is (T66). A status may legitimately
    discuss withdrawal -- "withdraws A138's claim", "A138 is the WD entry" --
    without itself being withdrawn.
    """
    # RESOLVED ONCE, like its sibling `is_open` above. This re-executed route.py
    # from disk on EVERY call -- 1,764 times per run over a 441-entry ledger --
    # while `is_open` rebinds itself in globals() after the first. The asymmetry
    # was invisible because both return the right answer; only the profile shows
    # it. Same fallback, same semantics, one load.
    global _WD_MATCH
    if _WD_MATCH is None:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_route_wd", Path(__file__).resolve().parent / "route.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _WD_MATCH = mod.WD_RE.match
        except Exception:
            _WD_MATCH = re.compile(r"\s*\**WD\b", re.I).match
    return bool(_WD_MATCH(tag))


# A claim asserting an absence. These are the phrasings that actually burned us.
NEGATIVE = re.compile(
    r"\b(nothing|never|no other|zero (?:callers|hits|writes|gaps|matches)|"
    r"unreferenced|not called|does not exist|no such|none of)\b", re.I)

# A scope marker: says WHERE the search looked. Deliberately generous -- the aim
# is to catch claims with NO scope at all, not to police wording.
SCOPE = re.compile(
    r"(\bin\b|\bacross\b|\bwithin\b|\bthroughout\b|ROM-wide|`[^`]+`|"
    r"between t=|scope:)", re.I)

TAG_RE = re.compile(r"^\|\s*([A-Z]+\d+[a-z]?)\s*\|\s*([^|]+?)\s*\|(.*)$")
LB_RE = re.compile(r"^### (L\d+)\s+—\s+(.*)$")

# T131: the user queue lives in the ledger file, but its rows are WORK ITEMS,
# not findings. Parsing them as entries puts phantom findings into every audit
# denominator -- caught on the very edit that added them, 398 -> 405.
#
# ONE DEFINITION, imported by ledger.py and user_queue.py rather than copied,
# because two definitions would let a row be an entry for one tool and not for
# another and nobody could say which was authoritative (T121, and the same
# reason audit.py imports SUPERSEDES_RE from here rather than restating it).
NON_ENTRY_SECTIONS = ("## THE USER QUEUE",)


def is_non_entry_section(heading):
    """True if this `## ` heading introduces rows that are not ledger entries."""
    return bool(heading) and heading.startswith(NON_ENTRY_SECTIONS)


# T155, the user's rule 2026-08-22: "rolling is a way of making sure the NON
# user-directed work is well distributed, but user directed work will always be
# highly focused." So user-directed entries must not accumulate toward the
# "you have not rolled" nag. They were never routed and were never going to be
# -- the user picked the target -- so counting them implies a drift into
# self-chosen work that did not happen.
#
# ONE DEFINITION, imported by route.py rather than copied (T131, and T149 is
# what copying this kind of predicate costs).
def is_user_directed(body):
    """True if this entry records work the USER directed, not a roll."""
    return "user-directed" in (body or "").lower()
REQUIRED_LB = ("Claim", "Observed", "Falsifier", "Checked")


def parse(text):
    """Return (rows, load_bearing). rows: id -> (tag, body, line). lb: id -> (fields, line)."""
    rows, lb = {}, {}
    dupes = []
    cur_lb = None
    skip_section = False          # T131: inside a non-entry section
    for n, line in enumerate(text.split("\n"), 1):
        if line.startswith("## "):
            skip_section = is_non_entry_section(line)
        m = LB_RE.match(line)
        if m:
            cur_lb = m.group(1)
            lb[cur_lb] = {"fields": set(), "body": [], "line": n, "title": m.group(2)}
            continue
        if cur_lb and line.startswith("- **"):
            f = re.match(r"- \*\*(\w+)", line)
            if f:
                lb[cur_lb]["fields"].add(f.group(1))
            lb[cur_lb]["body"].append(line)
            continue
        if line.startswith("###") or line.startswith("## "):
            cur_lb = None
        m = None if skip_section else TAG_RE.match(line)
        if m:
            eid, tag, body = m.group(1), m.group(2), m.group(3)
            if eid in rows:
                dupes.append((eid, n, rows[eid][2]))
            else:
                rows[eid] = (tag, body, n)
    return rows, lb, dupes


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    hook = "--hook" in sys.argv
    if hook:
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return 0
        path = (payload.get("tool_input") or {}).get("file_path", "")
        if "findings-ledger" not in str(path):
            return 0

    if not LEDGER.exists():
        return 0
    text = LEDGER.read_text()
    rows, lb, dupes = parse(text)

    # ANCHORED, not substring. `"WD" in tag` classified T72 as withdrawn because
    # its status says "A138 is the WD entry, not this one" -- an entry was marked
    # withdrawn by *explaining* that something else was. Everything citing it was
    # then flagged, and a reader would discount a live rule. Exactly T66's defect
    # in a second predicate: the tag must OPEN the cell, not merely appear in it.
    withdrawn = {i for i, (tag, _, _) in rows.items() if is_withdrawn(tag)}
    problems = []

    # 1. negatives without a scope
    for eid, (tag, body, n) in rows.items():
        if is_withdrawn(tag) or is_open(tag):
            continue
        if NEGATIVE.search(body) and not SCOPE.search(body):
            problems.append(
                (n, f"{eid}: asserts an absence with no stated scope. "
                    f"Say WHERE you looked, inside the claim."))

    # 2. load-bearing completeness
    for lid, d in lb.items():
        missing = [f for f in REQUIRED_LB if f not in d["fields"]]
        if missing:
            problems.append(
                (d["line"], f"{lid}: load-bearing claim missing {', '.join(missing)}."))

    # 3. resting on a withdrawn entry.
    # An entry that IS the replacement legitimately names what it replaced, so
    # a correction-word excuses the citation it sits beside.
    #
    # T48: that exemption used to be tested against the WHOLE ROW. Rows here run
    # to thousands of characters, so one "refuted" anywhere -- or a `~~` used as
    # plain strikethrough -- switched the check off for every citation in the
    # row, permanently. 62 of 185 rows were exempt, including the B46 case this
    # check's own docstring cites as its reason for existing. Found the same way
    # as T40: an honest annotation on T17 silenced the alarm, and the words that
    # did it were prose, not a claim the checker understood.
    #
    # So the word must sit NEAR the citation it excuses. Same fix as T40's --
    # narrow the scope of the predicate to the thing it describes. The window is
    # deliberately generous (a long sentence) but is a small fraction of a row.
    supersedes = re.compile(
        r"(supersed|replaces|corrects|refut|retract|too coarse|withdr|~~)", re.I)
    NEAR = 150

    # CITING A WITHDRAWN ENTRY AS A CAUTIONARY EXAMPLE (T126).
    #
    # Six findings in one day were all this shape: entries naming A161 or A196
    # as "the mistake this is an instance of". None RESTED on the withdrawn
    # claim being true -- a withdrawn entry is the BEST example of its own error
    # class, and its withdrawal strengthens the citation rather than weakening
    # it. The correction-word exemption above does not cover it, because
    # nothing is being corrected.
    #
    # THE WAIVER IS DELIBERATE AND NAMES THE ENTRY, for the reason the comment
    # above gives: an entry-level match on ordinary prose once exempted 62 of
    # 185 rows, including the very case this check exists for. `CITED AS
    # PRECEDENT` is a token nobody writes by accident, and it must appear
    # within 200 characters of the ID it excuses -- so it waives ONE named
    # citation, not every withdrawn entry a row happens to mention.
    #
    # Same shape as the single-run waiver: you may do it, but you must say you
    # thought about it, and say which one.
    # THE MARKER MUST NAME THE ENTRY IMMEDIATELY, not merely nearby. The first
    # version allowed the ID anywhere within 200 characters, and its own control
    # caught it: a marker reading "CITED AS PRECEDENT: ZZ8 ..." silenced a
    # separate citation of ZZ9 further along the same row, because ZZ9 fell
    # inside the window. That is a blanket off-switch on the highest-value
    # check here -- the exact failure this waiver was written to avoid.
    def _precedent(body_text, w):
        return re.search(rf"CITED AS PRECEDENT[:\s]*\**\s*(?<![\w./]){w}(?![\w./])",
                         body_text, re.S) is not None

    for eid, (tag, body, n) in rows.items():
        if is_withdrawn(tag):
            continue
        for w in sorted(withdrawn):
            if _precedent(body, w):
                continue
            for m in re.finditer(rf"(?<![\w./]){w}(?![\w./])", body):
                window = body[max(0, m.start() - NEAR):m.end() + NEAR]
                if supersedes.search(window):
                    continue
                problems.append(
                    (n, f"{eid}: cites {w}, which is WITHDRAWN. "
                        f"Re-check whether {eid} still stands on its own."))
                break
    for lid, d in lb.items():
        joined = "\n".join(d["body"])
        for w in sorted(withdrawn):
            if re.search(rf"(?<![\w./]){w}(?![\w./])", joined):
                problems.append(
                    (d["line"], f"{lid}: load-bearing claim cites WITHDRAWN {w}."))

    # 3b. citing an entry that DOES NOT EXIST.
    # B36 rested on "B35's derived unpack addresses" for its whole life; the only
    # occurrence of B35 in the ledger was that citation. A dangling reference is
    # worse than a withdrawn one -- a withdrawn entry at least records what was
    # believed and why it fell, whereas this looks like support and is nothing.
    # Bare IDs only (A12, B7, T3, I9, L2); anything with other text around it,
    # like a hex address, is left alone.
    # ROADMAP.md defines its own IDs (A26, B31, T11 ...) and the ledger legitimately
    # cross-references them, so those are not dangling.
    known = set(rows) | set(lb)
    roadmap = LEDGER.parent / "ROADMAP.md"
    if roadmap.exists():
        known |= set(re.findall(r"^\*\*([ABTIL]\d{1,3}[a-z]?)\s+—",
                                roadmap.read_text(), re.M))
    # Archived entries still exist -- they just live elsewhere. Counting them as
    # known is what makes archiving safe; without this the first archive pass
    # would manufacture dozens of dangling citations (T21).
    for arch in LEDGER.parent.glob("findings-archive-*.md"):
        known |= set(re.findall(r"^\|\s*([ABTIL]\d{1,3}[a-z]?)\s*\|",
                                arch.read_text(), re.M))
    ref_re = re.compile(r"(?<![\w./])([ABTIL]\d{1,3}[a-z]?)(?![\w./])")
    # An entry that RECORDS a dangling reference has to name it; don't flag that.
    names_gap = re.compile(r"(does not exist|never existed|has never existed|dangling)", re.I)
    for eid, (tag, body, n) in rows.items():
        if names_gap.search(body):
            continue
        for ref in set(ref_re.findall(body)):
            if ref != eid and ref not in known:
                problems.append(
                    (n, f"{eid}: cites {ref}, which DOES NOT EXIST in this ledger. "
                        f"Either the entry was never written or the ID is wrong."))

    # 3c. malformed cost annotation in the STATUS column.
    #
    # scripts/route.py ranks open work by parsing exactly `[cost=N]`. Anything
    # else silently drops the row OUT of the ranking. On 2026-08-19 a re-cost was
    # written `[cost=3, was 4]` -- readable to a human, invisible to the parser --
    # and T11 vanished from the cost ranking while THIS script still said "OK".
    # route.py noticed and said UNPRICED; the automatic gate did not. That is the
    # wrong way round: the hook fires on every ledger edit, route.py only when
    # someone runs it.
    #
    # Only the status column is inspected, never the body -- prose legitimately
    # says "cost days" or "re-costed", and policing that would be noise.
    cost_ok = re.compile(r"\[cost=\d+\]")
    mentions_cost = re.compile(r"cost", re.I)
    for eid, (tag, body, n) in rows.items():
        # Only OPEN rows are ranked, so only OPEN rows can be mis-priced. This
        # used to run over every row and fired on T67, whose status says the
        # ledger "costs 83k tokens" -- prose, in a MEASURED entry route.py will
        # never rank. Same shape as T66: a word matched where a tag was meant.
        if not is_open(tag):
            continue
        if mentions_cost.search(tag) and not cost_ok.search(tag):
            problems.append(
                (n, f"{eid}: malformed cost in the status column -> '{tag.strip()}'. "
                    f"route.py parses exactly [cost=N] (digits only); anything else "
                    f"drops this row out of the ranking as UNPRICED, silently. "
                    f"Use [cost=N] and put any history in the finding text."))
        elif not cost_ok.search(tag):
            problems.append(
                (n, f"{eid}: OPEN but carries no [cost=N], so route.py cannot rank "
                    f"it and sorts it last. Price it, or the ordering is not a ranking."))

    # 3b. entries that cannot be indexed.
    #
    # Since T67 the ledger is READ VIA `scripts/ledger.py --index` -- 198 entries
    # for ~8.5k tokens instead of 83k. That only works while every entry yields a
    # claim that stands on its own, so an entry whose claim collapses to a topic
    # heading ("UN-WITHDRAWN", "G6 / ares comparison") is INVISIBLE in the only
    # view anyone reads end to end. Flagged at write time, because the index
    # rotting is silent by construction: the entry is still there, still correct,
    # and simply says nothing.
    try:
        import importlib.util
        _s = importlib.util.spec_from_file_location(
            "_ledger", Path(__file__).resolve().parent / "ledger.py")
        _m = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(_m)
        for eid, (tag, body, n) in rows.items():
            c = _m.claim_of(tag, body)
            if len(c.split()) < 5 and not c.upper().startswith("MERGED INTO"):
                problems.append(
                    (n, f"{eid}: indexes to {c!r}, which asserts nothing. "
                        f"scripts/ledger.py --index is how this file is read now; "
                        f"an entry that indexes to a heading is invisible there. "
                        f"Put the claim in the status column, or add **CLAIM:** to the body."))
    except Exception as e:  # never fail closed -- this runs as a git hook
        problems.append((0, f"could not run the index check ({e.__class__.__name__}: {e}); "
                            f"scripts/ledger.py may be broken"))

    # 4. routing decision overdue. This is what makes the explore/exploit roll
    # actually happen: findings accumulate constantly, so the nag surfaces on
    # its own rather than depending on remembering to roll.
    # Kept OUT of `problems`: this is a reminder, not a structural defect, and
    # --strict is used by daily_push.sh as a publish gate. A nag must never
    # block a push -- that conflates "you owe a routing roll" with "the ledger
    # is malformed", and the fix for the former is not to edit the ledger.
    reminders = []

    # 3c-bis. MERGED rows must point somewhere real.
    #
    # Merging two entries that record the same lesson is allowed (T53), but it
    # is the one edit here that can destroy structure rather than prose, so it
    # carries its own rules:
    #
    #   * the merged-away ID is NEVER deleted -- it stays as a stub, so every
    #     existing citation still resolves and the visited set is preserved;
    #   * the stub must name its target, and the target must exist.
    #
    # Without this check a stub could name a typo'd or later-archived ID and the
    # content would be unreachable from the citation -- which is T21's dangling
    # citation, manufactured deliberately by our own housekeeping.
    for eid, (tag, body, n) in rows.items():
        if "MERGED" not in tag:
            continue
        m = re.search(r"MERGED into ([A-Z]+\d+[a-z]?)", tag)
        if not m:
            problems.append(
                (n, f"{eid}: status says MERGED but names no target. "
                    f"Write 'MERGED into <ID>' so the citation still resolves."))
        elif m.group(1) not in rows:
            problems.append(
                (n, f"{eid}: MERGED into {m.group(1)}, which does not exist. "
                    f"The stub is a dead end -- exactly the T21 defect."))

    # 3d. entry LENGTH. This is the one that actually controls the file's size,
    # and it went unmeasured for two days while the size threshold pointed at
    # archiving instead.
    #
    # Measured 2026-08-19 (T51): the 2026-08-18 entries average 112 words and
    # top out at 324. The 2026-08-19 entries average 398 and top out at 846 --
    # 3.6x, for the same kind of content. 43 entries were 25% of the ledger by
    # count and 55% by words. Archiving 26 rows of genuine history recovered
    # 1,037 words; compressing one session's prose was worth ~12,000.
    #
    # So the file does not grow because findings accumulate. It grows because
    # entries get written long, and that is visible AT WRITE TIME with no
    # hindsight at all -- unlike archiving, which needs to know what turned out
    # to matter (T46).
    #
    # A warning, never a gate. Some entries have earned their length: a
    # correction that must stop a resurrection, or a load-bearing claim with its
    # controls. The check exists so that length is a DECISION rather than an
    # accident, which is all it was on 2026-08-19.
    LONG = 250
    long_rows = sorted(((len(b.split()), e) for e, (t, b, n) in rows.items()
                        if len(b.split()) > LONG), reverse=True)
    if long_rows:
        worst = ", ".join(f"{e} ({w}w)" for w, e in long_rows[:5])
        reminders.append(
            f"LENGTH: {len(long_rows)} entr{'y' if len(long_rows)==1 else 'ies'} "
            f"over {LONG} words ({sum(w for w, _ in long_rows):,} words total). "
            f"Longest: {worst}. Median entry is ~124w and carries claim, status, "
            f"evidence and falsifier fine. Trim, or decide the length is earned.")

    # Ledger size. The file is meant to be read IN FULL at session start, so its
    # cost is paid every time; past ~30k words that starts crowding out the work
    # it exists to serve. Measured 2026-08-18 at 194 entries / 18.9k words, with
    # the A-series (a now-resolved investigation, closed by L7) accounting for
    # 62% of it -- so the first archive pass is cheap and obvious.
    # NOT a structural problem, so it stays out of `problems` and cannot block
    # daily_push.sh: "the ledger is long" is not "the ledger is malformed".
    # Threshold raised 30k -> 40k on 2026-08-19, and the PRESCRIPTION changed,
    # because the old one had become unfollowable: it said "archive a closed
    # investigation" when both archivable investigations were already archived
    # (T46). A gate whose only prescribed action is unavailable gets satisfied
    # by whatever is easiest, which means archiving things that should stay.
    #
    # Measured yield of every size intervention tried (T54): compressing prose
    # +5,588 words net, archiving +367, merging by class -210. The lever is
    # spent, so this nag now points at the ONE thing still worth doing (write
    # short, per the LENGTH check above) and otherwise gets out of the way.
    #
    # The last clause used to read "if you are seeing this note you are reading
    # the raw file; that is the thing the index exists to avoid". It was FALSE
    # of almost every appearance. This checker reads the ledger itself, on every
    # ledger edit (as a hook), at every checkpoint, and inside daily_push.sh --
    # so the note accused its reader of the read that THIS SCRIPT had just done.
    # An inference a tool cannot actually make about its caller is not a warning,
    # it is noise that trains the reader to skim a standing reminder. Say what is
    # true (the size, the prescription) and drop what cannot be known from here.
    words = len(text.split())
    if words >= 40000:
        reminders.append(
            f"SIZE: {words:,} words in docs/findings-ledger.md. Housekeeping is "
            f"spent (T54) — do NOT start another archive or merge pass expecting "
            f"a saving. If the read cost is actually hurting, the remaining answer "
            f"is the two-tier index in T52 — which was BUILT as T68: read "
            f"`scripts/ledger.py --index` (~8.5k tokens, ~12% of the file) and "
            f"`--show <ID>` to expand, rather than the ledger end to end. This "
            f"note is emitted by check_ledger.py, which reads the file by design; "
            f"it says nothing about how YOU read it.")
    try:
        state = json.loads((LEDGER.parent / ".route-state.json").read_text())
        # ROUTABLE entries only (T155). This counted EVERY new entry, so a day
        # of user-directed work nagged that a routing decision was overdue --
        # but a roll distributes work I choose, and user-directed work was
        # chosen by the user. On 2026-08-22 it read "12 entries added since
        # roll #179" when every one of the twelve was user-directed and not one
        # routing decision had been skipped.
        _routable_now = sum(1 for _t, _b, _l in rows.values()
                            if not is_user_directed(_b))
        _base = state.get("last_routable_count")
        if _base is None:                      # pre-T155 state: fall back loudly
            since = len(rows) - state.get("last_entry_count", 0)
            _ud = ""
        else:
            since = _routable_now - _base
            _ud = (f" ({len(rows) - state.get('last_entry_count', 0)} added in "
                   f"total; the rest were user-directed and do not count)")
        if since >= 6:
            reminders.append(f"routing: {since} ROUTABLE entries added since roll "
                             f"#{state.get('roll', 0)}{_ud} — run scripts/route.py.")
    except Exception:
        reminders.append("routing: no roll recorded yet — run scripts/route.py.")

    # 4b. the L1 audit had NO trigger at all -- it fired only when someone
    # remembered, which is precisely the failure mode the audit exists to catch.
    # Every discipline left to memory on this project has failed at least once
    # (T26), so hang it off the one hook that always runs.
    try:
        ast_ = json.loads((LEDGER.parent / ".audit-state.json").read_text())
        st_ = json.loads((LEDGER.parent / ".route-state.json").read_text())
        due = st_.get("roll", 0) - ast_.get("last_roll", 0)
        if due >= 10:
            reminders.append(f"audit: {due} rolls since audit #{ast_.get('audits', 0)} "
                             f"— run scripts/audit.py (due every ~10).")
    except Exception:
        reminders.append("audit: no audit recorded yet — run scripts/audit.py.")

    # L2 (daily) and L3 (weekly) nags. The ladder specified four levels on
    # 2026-08-18; L2 and L3 were never built and never ran, and the reason is
    # simply that NOTHING ASKED FOR THEM -- L1 had a nag and still went 13 rolls
    # unread (T76), so a level with no nag was never going to happen at all.
    import datetime as _dt
    _today = _dt.date.today().isoformat()
    for _lvl, _statef, _script, _period in (
            ("L2", ".audit-l2-state.json", "scripts/audit_l2.py", "daily"),
            ("L3", ".audit-l3-state.json", "scripts/audit_l3.py", "weekly")):
        try:
            _sp = LEDGER.parent / _statef
            _last = json.loads(_sp.read_text()).get("last_date", "") if _sp.exists() else ""
            _due = (_last != _today) if _lvl == "L2" else (
                not _last or (_dt.date.fromisoformat(_today) - _dt.date.fromisoformat(_last)).days >= 7)
            if _due:
                reminders.append(f"{_lvl} ({_period}) audit due — run {_script} "
                                 f"(last: {_last or 'never'}).")
        except Exception:
            reminders.append(f"{_lvl} audit state unreadable — run {_script}.")

    # 4a2. THE COMPOSING STEP, CHECKED (T112).
    #
    # T57 ("when an entry stitches verified parts into a story, say which step is
    # the stitch and mark it unverified") was the project's MOST-VIOLATED prose
    # rule -- written, cited in CLAUDE.md, and violated at least twice
    # afterwards, most expensively in A179, where an ADDRESS measured in one run
    # was matched against CONTENTS from a snapshot of another. A rule with no
    # checker is a preference.
    #
    # THE HEURISTIC, deliberately narrow: a MEASURED/READ entry whose evidence
    # cell names artifacts from TWO OR MORE DISTINCT DATES is stitching across
    # runs. That is not automatically wrong -- it is exactly the moment T57 says
    # to name the stitch.
    #
    # NOISE MEASURED BEFORE SHIPPING (T29): across 296 entries this fires ONCE,
    # on A161 -- a withdrawn, user-caught entry of precisely this class. A
    # heuristic whose only historical positive is a known-bad entry is worth
    # having. Withdrawn entries are skipped, so it starts at zero standing noise.
    _mark = re.compile(r"composing step|inferred, not measured|INFERRED, NAMED", re.I)
    for eid, (tag, body, n) in rows.items():
        if is_withdrawn(tag) or not re.search(r"MEASURED|READ", tag):
            continue
        raw = text.split("\n")[n - 1] if 0 < n <= len(text.split("\n")) else ""
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", cells[-1]))
        if len(dates) >= 2 and not _mark.search(raw):
            problems.append(
                (n, f"{eid}: cites evidence from {len(dates)} different dates "
                    f"({', '.join(sorted(dates))}) and names no COMPOSING STEP. "
                    f"Stitching across runs is where A179 went wrong — say which "
                    f"step is the stitch and mark it unverified (T57/T112)."))

    # 4b2. USER-OBSERVED RUNS (T101). Two triggers, and the second is the point.
    #
    # I cannot perceive audio at all -- the capture pipeline records video only
    # -- and A97 is entirely about audio silence, so every claim in it comes
    # from reading source. Separately I have been wrong TWICE about what is on
    # screen (A93, A161), both times with the observation right and the
    # QUANTIFIER wrong. Neither gap closes without a human watching.
    #
    # TRIGGER 1, daily, but GATED ON WORK HAVING HAPPENED. A calendar nag on a
    # day with no work is ceremony, and T100 records that exact mistake in L2's
    # trigger -- worse here, because this one spends the USER'S time, and a
    # policy that wastes it will be abandoned (T29).
    #
    # TRIGGER 2, PROGRESS, and it is deliberately MECHANICAL rather than my
    # judgement: "seeming progress" assessed by the party whose claims are being
    # checked is worth nothing. Computed from run-log.tsv -- a run that asked
    # for more than the known crash time and did NOT come back rc=139 is either
    # real progress or a broken run, and both are worth a human look.
    try:
        _obs = LEDGER.parent / "observed-runs.md"
        _last_obs = ""
        if _obs.exists():
            _m = re.findall(r"^## (\d{4}-\d{2}-\d{2})T", _obs.read_text(), re.M)
            _last_obs = _m[-1] if _m else ""
        _today2 = __import__("datetime").date.today().isoformat()
        # GATED ON WORK HAVING HAPPENED -- AND NOW ACTUALLY GATED (T151).
        #
        # The comment above trigger 1 promised this and the code guarded on
        # `rows`, i.e. every ledger entry ever written, which is never empty.
        # The predicate was described, justified at length, and never
        # implemented, so the nag fired on any day at all -- including days
        # nobody touched the project, when `daily_push.sh` runs it from cron at
        # 18:30. **This one spends the USER'S time, and a policy that wastes it
        # gets abandoned (T29).** The user's rule, 2026-08-22: missing a day
        # must not mean owing two the next.
        #
        # THE SIGNAL IS "did anything happen today", NOT "was a roll consumed".
        # Keying on a roll would be circular: the observed run is meant to come
        # BEFORE the first roll of the day, so a roll-gated nag could never fire
        # in time to be useful. A run in run-log.tsv or an entry dated today are
        # the two things that mean a session is under way, and NEITHER is
        # produced by the cron job -- which is the whole point, since the cron
        # job is exactly the caller that used to nag about idle days.
        _rl_early = LEDGER.parent / "run-log.tsv"
        _worked_today = False
        if _rl_early.exists():
            _worked_today = any(r.startswith(_today2)
                                for r in _rl_early.read_text().split("\n"))
        if not _worked_today:
            _worked_today = any(_today2 in (_b or "") for _t, _b, _l in rows.values())
        if _last_obs != _today2 and _worked_today:
            reminders.append(
                f"observed run: none today (last: {_last_obs or 'never'}) — "
                f"run scripts/observed_run.sh. I cannot hear audio at all, and "
                f"scene identity has been wrong twice from sampling (T101).")
        _rl = (LEDGER.parent / "run-log.tsv")
        # SHAPE GUARD (T105). The verdict column was added to the DATA and never
        # to the HEADER, so for 88 rows the file had 10 names over 11 columns and
        # anything reading it BY NAME silently misaligned -- `log` would have
        # returned the verdict. Five older rows had no verdict at all, so the
        # width was not even self-consistent. A tabular evidence file whose
        # header lies is worse than one with no header, because the header
        # invites exactly the parse that breaks.
        if _rl.exists():
            _rows = [r for r in _rl.read_text().split("\n") if r.strip()]
            _w = {len(r.split("\t")) for r in _rows}
            if len(_w) > 1:
                reminders.append(
                    f"run-log.tsv has RAGGED rows (widths {sorted(_w)}) — anything "
                    f"parsing it positionally is misaligned for some rows (T105).")
        if _rl.exists():
            for _row in _rl.read_text().strip().split("\n")[-1:]:
                _f = _row.split("\t")
                # KEYED ON THE CURRENT FAULT SIGNATURE, NOT THE RETIRED ONE
                # (2026-08-21). This asked "did the run last >165 s WITHOUT
                # returning 139?" -- true of the 158 s SIGSEGV era, when a long
                # run that did not segfault was real news.
                #
                # THAT ERA ENDED ON 2026-08-20. Measured from run-log.tsv: every
                # long headless run up to 14:45 that day returned 139 at ~158 s
                # with ~4,659 tasks; every one since has returned 0 at 6,169.
                # So the condition became true of EVERY long run and the note
                # fired permanently -- on runs that stalled exactly as expected,
                # and on runs too short to reach the stall at all. An alarm that
                # always sounds is one you learn to skip (T29), and this one
                # gates the user's own time via T101.
                #
                # A299 measured 6,169 as a CEILING, not merely a stall point:
                # 13 runs sit exactly there and no run in 156 has ever exceeded
                # it, across three verdicts and five probe environments. So the
                # two things that would be genuine news are:
                #   * gfx_total > 6,169  -- the ceiling broke. This is A299's
                #     own falsifier, and it is what progress looks like.
                #   * a long HEADLESS run returning 139 again -- the retired
                #     crash is back.
                # The normal stall is neither, and neither is a run that simply
                # ran out of clock before reaching the wall.
                #
                # 6169 IS A LITERAL ON PURPOSE. Deriving it from the log's own
                # maximum would move the needle with the thing being measured --
                # the exact way a control stops discriminating (T100, T136), and
                # it would silently accept a new ceiling as the expected one.
                CEILING = 6169          # A299, 2026-08-21
                if len(_f) >= 4 and _f[1].isdigit() and _f[2].isdigit():
                    _req, _act, _rc = int(_f[1]), int(_f[2]), _f[3]
                    _gfx = _f[6] if len(_f) > 6 else ""
                    _env = _f[10] if len(_f) > 10 else ""
                    _n = int(_gfx) if _gfx.isdigit() else None
                    if _n is not None and _n > CEILING:
                        reminders.append(
                            f"observed run DUE ON PROGRESS: the last run reached "
                            f"{_n} graphics tasks — PAST the {CEILING} ceiling that "
                            f"13 runs have never exceeded (A299). This is that "
                            f"entry's own falsifier. Confirm with a human before "
                            f"believing it (T101).")
                    # NOTE THERE IS NO `_act > 165` HERE, and the first version
                    # had one inherited from the old condition. A CRASHING RUN
                    # DIES EARLY -- the retired signature is req=180, act=158 --
                    # so requiring a long DURATION excluded exactly the case
                    # this branch exists to catch. Caught by the control, which
                    # is the whole reason it feeds a real fixture rather than
                    # asserting on the source text.
                    elif _req > 165 and _rc == "139" and "VISIBLE" not in _env:
                        reminders.append(
                            f"observed run DUE ON A CHANGED SIGNATURE: the last run "
                            f"asked {_req}s, died at {_act}s and returned 139 — a "
                            f"HEADLESS SIGSEGV. Headless runs have stalled at "
                            f"{CEILING} and exited 0 since 2026-08-20; a crash is a "
                            f"regression, not the stall. Confirm with a human (T101).")
    except Exception:
        pass

    # 4c. SINGLE-RUN, ASKED AT WRITE TIME (T99).
    #
    # `single-run` is the one defect class that will not go away: 21 instances,
    # and L2 #5 flagged it as still recurring after every fix aimed at it. The
    # reason is timing, not detection -- audit.py already catches it, but days
    # later, when repeating a run is inconvenient and writing a justification is
    # easy. So the same question moves to the moment the entry is written, when
    # answering it honestly is still cheap.
    #
    # THE PREDICATE IS audit.py's, COPIED DELIBERATELY rather than reinvented:
    # MEASURED/INTERVENED, exactly one distinct .log cited, no plural-runs
    # phrasing. Two different definitions of "single-run" would be worse than
    # one, because entries would pass one checker and fail the other.
    #
    # BOUNDED BY A HIGH-WATER MARK. Unbounded it flags all 21 historical
    # instances on every run, and 21 permanent warnings bury the two real ones
    # (T29: noise is how a discipline stops being read). Same bound as
    # lint_tools.py's baseline and audit.py's window: only entries created after
    # the mark are checked, and the mark advances each run.
    _srp = LEDGER.parent / ".check-ledger-state.json"
    try:
        _srs = json.loads(_srp.read_text()) if _srp.exists() else {}
    except Exception:
        _srs = {}
    _base = _srs.get("sr_baseline")
    _cur = {}
    for eid in rows:
        m = re.match(r"([A-Z]+)(\d+)", eid)
        if m:
            _cur[m.group(1)] = max(_cur.get(m.group(1), 0), int(m.group(2)))
    if _base is not None:
        for eid, (tag, body, n) in rows.items():
            m = re.match(r"([A-Z]+)(\d+)", eid)
            if not m or int(m.group(2)) <= _base.get(m.group(1), 0):
                continue
            if not re.search(r"MEASURED|INTERVENED", tag):
                continue
            blob = tag + " " + body
            logs = set(re.findall(r"[\w.-]+\.log", blob))
            if len(logs) != 1:
                continue
            if re.search(r"\b(\d+|two|three|both)\s+runs?\b", blob, re.I):
                continue
            if re.search(r"ONE RUN IS ENOUGH", blob, re.I):
                continue
            problems.append(
                (n, f"{eid}: rests on ONE run ({sorted(logs)[0]}) and does not say why that "
                    f"is enough. Repeat it, cite a second log, or write "
                    f"'ONE RUN IS ENOUGH: <reason>' in the entry. Asked now because "
                    f"asked-at-audit-time has not worked 21 times (T99)."))
    if not hook:
        _srs["sr_baseline"] = _cur
        try:
            _srp.write_text(json.dumps(_srs, indent=1))
        except Exception:
            pass

    # 4e. THE CLOSING SENTENCE, IN THE ENTRY (T120).
    #
    # WHY IT MOVED INTO THE LEDGER. `route.py` has always printed "close this
    # checkpoint with one plain-language sentence". On 2026-08-20 the user asked
    # what had happened to it, and the answer was: written for 5 checkpoints of
    # 6, skipped on the one that also drifted (T119), and absent entirely from
    # every piece of user-directed work that day -- which was most of it.
    #
    # THE REASON IT IS THE PART THAT SLIPS: it was the ONLY element of a
    # checkpoint with no mechanical check. The roll lands in route-log.md, the
    # finding in the ledger, the change in git; the sentence existed only in
    # chat, where nothing could notice its absence. `test_route.py` asserts that
    # route.py PRINTS the requirement -- never that anyone met it. Everything
    # that was checked survived that day; the one thing that was not, did not.
    #
    # So it now lives in the entry, where check_ledger can see it.
    #
    # TWO CHECKS, AND THE SECOND IS THE DISCRIMINATING ONE. Presence alone is
    # satisfied by pasting the entry's own jargon after the label, which is
    # exactly the sentence the rule exists to prevent -- CLAUDE.md's wording is
    # "no hex, no entry IDs, no tool names". So the text is also checked for
    # being plain: an address, an entry ID, a filename, a register or a `ctx->`
    # expression means it was not written for a human.
    _swp = LEDGER.parent / ".check-ledger-state.json"
    try:
        _sws = json.loads(_swp.read_text()) if _swp.exists() else {}
    except Exception:
        _sws = {}
    # BOOTSTRAP, done once and recorded in the state file rather than in code.
    # A baseline seeded to the current maximum makes a new checker's first real
    # run find nothing, and T100 says that is the case to SUSPECT rather than
    # celebrate. So on 2026-08-20 this was seeded by hand to the session
    # boundary (A187/T117) instead, and its first run reported 15 genuine gaps
    # -- every entry written that day, including the ones being written while it
    # was built. That bootstrap is spent; the mark now lives in the state file.
    #
    # The default below is the ordinary one -- start from here -- because a
    # hard-coded boundary would silently make this check INERT for any ledger
    # whose IDs are lower than it, including every test fixture.
    _swcur = {}
    for eid in rows:
        m = re.match(r"([A-Z]+)(\d+)", eid)
        if m:
            _swcur[m.group(1)] = max(_swcur.get(m.group(1), 0), int(m.group(2)))
    _swb = _sws.get("sw_baseline", _swcur)
    _swfail = {}
    for eid, (tag, body, n) in rows.items():
        m = re.match(r"([A-Z]+)(\d+)", eid)
        if not m or int(m.group(2)) <= _swb.get(m.group(1), 10 ** 9):
            continue
        pre, num = m.group(1), int(m.group(2))

        def _fail(msg):
            _swfail[pre] = min(_swfail.get(pre, 10 ** 9), num)
            problems.append((n, msg))

        blob = tag + " " + body
        # TAKE THE REAL SENTENCE, NOT A QUOTED TEMPLATE (T121).
        #
        # The first version took the FIRST match, and flagged T120 -- the entry
        # that INTRODUCED this rule -- because that entry quotes the format
        # (`SO WHAT: <one plain sentence>`) before using it. A checker cannot
        # tell mention from use, and this is the third time that has bitten in
        # two days: the bash guard refused a ledger entry for quoting a refused
        # command, and a control once matched its own text and passed.
        #
        # So: discard placeholders (`<...`) and backtick-quoted mentions, and
        # take the LAST surviving match -- the sentence sits at the end of an
        # entry by convention, after everything it is summarising.
        got = None
        for _m in re.finditer(r"SO WHAT:\s*(.+?)(?:\*\*|\||$)", blob, re.S):
            _txt = _m.group(1).strip()
            if _txt.startswith("<"):
                continue
            if _m.start() > 0 and blob[_m.start() - 1] == "`":
                continue
            got = _m
        if not got:
            _fail(f"{eid}: has no SO WHAT line. One plain sentence saying what this "
                  f"achieved -- no hex, no entry IDs, no tool names. 'Nothing moved "
                  f"forward, I fixed a measuring instrument' is a valid answer and "
                  f"exposing that is the point (T120).")
            continue
        sentence = got.group(1).strip()
        if len(sentence) < 15:
            _fail(f"{eid}: its SO WHAT is too short to be a sentence.")
            continue
        what = not_plain(sentence)
        if what:
            _fail(f"{eid}: its SO WHAT contains {what}, so it is not plain "
                  f"language. Rewrite it for someone who has not read the "
                  f"entry (T120): \"{sentence[:70]}...\"")
    if not hook:
        # THE MARK MUST NOT STEP OVER A KNOWN FAILURE. The single-run check
        # advances its baseline to the current maximum every run, so anything it
        # reports is reported EXACTLY ONCE and then forgotten -- tolerable there
        # because that check fires rarely. Here it would mean today's missing
        # sentences vanish from the record the moment they are first mentioned,
        # which is the opposite of moving the discipline somewhere it can be
        # seen. So the mark stops one below the lowest still-failing entry, and
        # a gap keeps being reported until it is actually filled.
        _swnew = dict(_swcur)
        for pre, lowest in _swfail.items():
            _swnew[pre] = min(_swnew.get(pre, lowest - 1), lowest - 1)
        _sws["sw_baseline"] = _swnew
        try:
            _swp.write_text(json.dumps(_sws, indent=1))
        except Exception:
            pass

    # 4d. THE ROLL WITNESS (T98). route.py stamps each roll with a random token
    # and records it in route-log.md. Quoting it proves the tool ran, because it
    # cannot be written before it existed -- T91 fabricated a whole roll line and
    # every OTHER field was guessable (a verdict from two options, a draw that
    # only has to look like a probability, a target from a two-item frontier).
    #
    # CHECKED HERE, not just emitted, because T89/T90/T95 are all the same story:
    # a rule nothing verifies is a preference. The check is deliberately lagged
    # by one roll -- the CURRENT roll's checkpoint is legitimately mid-flight, so
    # demanding its witness immediately would fire on every checkpoint and become
    # noise. Only a roll that has been SUPERSEDED by a later one should already
    # have been written up.
    try:
        _rl = (LEDGER.parent / "route-log.md").read_text()
        _rolls = re.findall(r"^- roll #(\d+):.*?\[witness `([0-9a-f]+)`\]", _rl, re.M)
        if len(_rolls) >= 2:
            _n, _w = _rolls[-2]          # the last COMPLETED roll
            if _w not in text:
                reminders.append(
                    f"routing: roll #{_n}'s witness `{_w}` appears in no ledger entry. "
                    f"Either that checkpoint recorded no outcome, or its announcement "
                    f"was not transcribed from the tool (T91/T98).")
    except FileNotFoundError:
        pass

    # 4e. THE USER QUEUE (T131). Items only the user can do, batched so one
    # sitting clears several. Surfaced HERE because this is the nag everything
    # already reads -- a reminder in a file nobody opens is T56's shape again.
    #
    # DELIBERATELY NOT ADDED TO `overdue`: nothing here escalates the hook. I
    # cannot clear a single item myself, so a hard block would halt all work
    # while the user is away, and T127 is the entry where I reported a reminder
    # as a gate and sent them to watch a run nothing required.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import user_queue
        _fired, _probs = user_queue.report(text, _dt.date.today(), quiet=True)
        if _fired:
            reminders.append(
                "USER QUEUE worth a sitting — " + "; ".join(_fired)
                + ". Run scripts/user_queue.py for the items. REMINDER, not a gate.")
        for _p in _probs:
            reminders.append(f"USER QUEUE cross-ref broken — {_p}")
    except Exception as _e:
        reminders.append(f"USER QUEUE could not be read ({_e}) — the nag is BLIND, "
                         f"which is worse than an empty queue. Fix before trusting it.")

    # 5. duplicate ids
    for eid, n, first in dupes:
        problems.append((n, f"{eid}: duplicate ID (first seen line {first}). "
                            f"Merge; one ID, one current status."))

    out = sys.stderr if hook else sys.stdout
    for r in reminders:
        print(f"[ledger] note — {r}", file=out)

    # The SUMMARY line names how many notes preceded it.
    #
    # Reminders print first, so `check_ledger.py | tail -1` shows only this
    # line -- and that is exactly what the per-checkpoint routine did. The
    # "audit overdue" reminder fired on every roll from #64 to #77 and was
    # truncated away all thirteen times; the audit finally ran 13 rolls late
    # and immediately found real defects (T75). The reminder worked perfectly
    # and nothing read it, which is T56's shape.
    #
    # So the last line must say that there IS something above it. Truncating to
    # one line can now hide the CONTENT of a reminder but never its EXISTENCE.
    note = f" — {len(reminders)} note(s) above" if reminders else ""

    # OVERDUE ACTIONS ESCALATE THROUGH THE HOOK; standing observations do not.
    #
    # The hook only surfaces its report to Claude on exit 2, and this returned 0
    # whenever there were no structural problems -- so a reminder ALONE never
    # reached the one channel that cannot be skipped. That is T76 again: the
    # audit nag fired for 13 rolls into a channel nothing read. The L2/L3 nags
    # were about to inherit the same fate on their first day.
    #
    # But not every reminder deserves to interrupt. LENGTH and SIZE are standing
    # facts about a long file; escalating those would fire on every ledger edit
    # and train me to ignore the guard channel, which is the failure T29 warns
    # about. Only reminders that name something OVERDUE escalate.
    overdue = [r for r in reminders if re.search(r"\b(due|rolls since audit)\b", r, re.I)]
    if not problems:
        print(f"[ledger] OK — {len(rows)} entries, {len(lb)} load-bearing, "
              f"{len(withdrawn)} withdrawn.{note}", file=out)
        if hook and overdue:
            print(f"[ledger] {len(overdue)} OVERDUE: "
                  + "; ".join(overdue), file=out)
            return 2
        return 0

    print(f"[ledger] {len(problems)} thing(s) to look at "
          f"({len(rows)} entries, {len(lb)} load-bearing){note}:", file=out)
    for n, msg in sorted(problems):
        print(f"  {LEDGER.name}:{n}: {msg}", file=out)

    # THE TRAILER MUST DISCLOSE TOO -- it is the genuinely last line on this
    # path, and the disclosure above it is not.
    #
    # T76 was fixed by putting "N note(s) above" on the summary line, and that
    # worked only while the summary WAS the last line. As soon as the ledger had
    # both notes and findings, the summary moved up and this trailer became the
    # last line, disclosing nothing -- so `check_ledger | tail -1` hid 3 notes
    # AND a finding. It did exactly that to me on 2026-08-19 before being found.
    # The lesson is not "put the count on the summary line", it is "whatever line
    # is LAST must account for everything above it".
    tail = f" — {len(problems)} thing(s)"
    if reminders:
        tail += f" + {len(reminders)} note(s)"
    tail += " above"
    print(f"  (warnings, not errors — judgement stays with the reader){tail}", file=out)

    if hook:
        return 2      # surfaces the report back to Claude
    return 1 if "--strict" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
