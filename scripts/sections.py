#!/usr/bin/env python3
"""Split a ledger entry body into the sections it is already written in.

WHY THIS IS ITS OWN MODULE (T192)
---------------------------------
The user asked for the walls of text to be sectioned in TWO places -- the status
page and the ledger reader. A second copy of this parser is a copy that goes
stale, which is a standing rule on this project, and the two would then disagree
about what an entry says. **One parser, two callers.**

WHY IT IS A VIEW AND NOT A REWRITE
----------------------------------
Measured over all 579 rows: **69% carry at least one all-caps lead-in acting as
a heading, median 3.** The structure is already in the file. Nothing here edits
the ledger; it re-presents it, and `roundtrip` asserts nothing is lost doing so.

    scripts/sections.py --self-check
"""
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "docs" / "findings-ledger.md"


def gist(line):
    """The human-readable body of a ledger row, without the markup."""
    body = line.split("|")
    txt = body[3] if len(body) > 3 else line
    return re.sub(r"\*\*|`|~~", "", txt).strip()


# A CAPS lead-in acting as a section heading: "THE RECOUNT:", "ONE RUN IS
# ENOUGH:", "NOT ESTABLISHED,". Matched by LOOKAHEAD so the separator is not
# consumed and heading+remainder reconstructs the source exactly -- which is
# what makes the round-trip control below possible.
# A heading must START A SENTENCE and END AT A COLON OR DASH. Both halves were
# learned by trying the loose version: allowing a bare comma as the terminator
# turned "7 GAME, 5 STACK, 2 METHOD" into a heading, and allowing a mid-sentence
# start turned the citation "(A358, A369)" into one. The tight form keeps the
# real headings and drops those.
#
# THE PROJECT'S OWN CLOSING VOCABULARY IS NAMED EXPLICITLY, because the generic
# pattern misses every one of them and they are the sections that matter most.
# "SO WHAT" is too short for the length rule; "Falsifier" is not upper case;
# "NOT ESTABLISHED, and unchanged:" breaks the caps run at its own comma. These
# are the standing section names this ledger uses -- the plain-language outcome,
# the scope limit, the single-run justification -- so a reader who only opens one
# section should be able to find them.
KNOWN = r"SO WHAT|Falsifier|NOT ESTABLISHED|ONE RUN IS ENOUGH|NO COMPOSING STEP|CONFIDENCE"
HEAD_RE = re.compile(
    r"(?:^|(?<=[.!?;] )|(?<=— )|(?<=\) ))"
    r"((?:" + KNOWN + r")(?=[:,])"
    r"|[A-Z][A-Z0-9 ,'’/()-]{9,}?(?=:| —))")


def sections(body):
    """Split an entry body on the CAPS lead-ins that already act as headings.

    WHY A VIEW AND NOT A REWRITE (user, 2026-08-24: "they're kind of just walls
    of text"). Measured over all 579 rows: **69% carry at least one CAPS lead-in,
    median 3.** The structure is already in the file -- it is simply rendered as
    one paragraph. So nothing here edits the ledger; it re-presents it.

    THE FIRST ATTEMPT AT THIS SPLIT WAS WRONG AND IS WORTH RECORDING: splitting on
    **bold runs** looked obvious, because there are ~10 per entry. But bold in
    these entries is mid-sentence EMPHASIS, not structure -- the split cut clauses
    in half and produced one fragment that was literally two asterisks. Ten
    segments is not ten sections. Measuring the right thing changed the answer.

    NOTHING MAY BE LOST. A splitter that silently drops a clause would be worse
    than the wall it replaces, because the reader cannot see the gap. The pieces
    are pure index slices and a control asserts they reconstruct the input.
    """
    ms = list(HEAD_RE.finditer(body))
    if not ms:
        return [{"h": "", "t": body.strip()}]
    out = []
    if ms[0].start() > 0:
        out.append({"h": "", "t": body[:ms[0].start()].strip()})
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        out.append({"h": m.group(1).strip(), "t": body[m.end():end].strip()})
    return [s for s in out if s["h"] or s["t"]]


def roundtrip(body):
    """Reassembly of _sections output, WHITESPACE-INSENSITIVE.

    Compared with all whitespace removed rather than normalised, because a
    heading that ends before a " —" separator loses the leading space to the
    lookahead boundary. That is a spacing artefact of where the cut falls; the
    property worth asserting is that **no characters are lost**, and comparing
    without whitespace says exactly that and nothing weaker.
    """
    return "".join("".join(s["h"] + s["t"] for s in sections(body)).split())


def self_check():
    """Controls VERIFIED TO FAIL. The load-bearing one is losslessness: a
    splitter that silently drops a clause is worse than the wall it replaces,
    because the reader cannot see the gap.

    The embedded probes carry the shapes that break it, so this discriminates
    wherever the script is run from -- relying on the ledger alone made an
    earlier version of this control fail for the WRONG reason in every break
    run from a scratch directory (BL14).
    """
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    PROBES = [
        "Roll #1. WHY THIS: because. SO WHAT: it reads. Falsifier: it does not.",
        "NO GAME RUN, NO DISPLAY — the only item needing neither. THE RECOUNT: of sixteen.",
        "no headings here at all, just a plain sentence with nothing shouted",
        "TRAILING HEADING WITH NOTHING AFTER IT:",
        "of sixteen, fourteen agree — 7 GAME, 5 STACK, 2 METHOD at both scopes (A358, A369).",
    ]
    real = ([l for l in LEDGER.read_text().split("\n")
             if re.match(r"^\|\s*[A-Z]+\d+\s*\|", l)] if LEDGER.exists() else [])
    corpus = PROBES + [gist(l) for l in real]
    lost = [c[:40] for c in corpus if roundtrip(c) != "".join(c.split())]
    chk(f"loses NO text ({len(corpus)} bodies, {len(real)} from the ledger)",
        not lost, f"{len(lost)} lose text: {lost[:3]}")

    heads = [s["h"] for s in sections(
        "Roll #1. WHY THIS AND NOT SOMETHING ELSE: because. "
        "NOT ESTABLISHED, and unchanged: the other thing. "
        "ONE RUN IS ENOUGH: there is no run. SO WHAT: it reads better. "
        "Falsifier: it does not.")]
    chk("the standing section names are found, not just shouty ones",
        all(h in heads for h in ("SO WHAT", "Falsifier", "NOT ESTABLISHED",
                                 "ONE RUN IS ENOUGH")), f"{heads}")
    # Measured on the live ledger: a bare comma terminator changes 318 of 579
    # entries; a mid-sentence start changes 137. Both restrictions are real.
    comma = [s["h"] for s in sections("NO GAME RUN, NO DISPLAY — the only item needing neither.")]
    chk("a heading is not cut at its own internal comma",
        comma == ["NO GAME RUN, NO DISPLAY"], f"{comma}")
    mid = [s["h"] for s in sections("The name of 0x02 IS RECALLED, NOT CITED: the count is the finding.")]
    chk("emphasis mid-sentence is not promoted to a heading", mid == [""], f"{mid}")
    noise = [s["h"] for s in sections(
        "of sixteen, fourteen agree — 7 GAME, 5 STACK, 2 METHOD at both scopes (A358, A369).")]
    chk("mid-sentence capitals are NOT mistaken for headings", noise == [""], f"{noise}")

    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--self-check" in sys.argv[1:]:
        sys.exit(self_check())
    print(__doc__)
