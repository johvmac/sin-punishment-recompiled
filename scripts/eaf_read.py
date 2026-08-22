#!/usr/bin/env python3
"""Read back an ELAN `.eaf` — the user's time-aligned annotations, as data.

WHY THIS EXISTS (T150)
----------------------
T101 settled that time-aligned annotation is the return path for things I
cannot check myself: I cannot hear audio, and scene identity has been wrong
twice from my own sampling (A93; A161, which is WITHDRAWN and is cited FOR its
withdrawal, having been withdrawn because a scene claim outran what had been
looked at). The user watches a recording and marks spans on it.

**The annotations have been WRITE-ONLY.** A266 is the worked example and its
`.eaf` has been sitting on the archive since 2026-08-21 with nothing able to
read it. T160 did the slice that made this possible — the observed run now
records WHICH video and WHICH audio file — and named the rest: "the recording
is not served up for annotation, no `.eaf` is read back".

This is the read-back half. It does not touch `observed_run.sh`.

THE CONTROL IS THE REAL TOOL'S REAL OUTPUT, WHICH IS THE POINT
--------------------------------------------------------------
`--self-check` runs against `evidence/2026-08-21/run_game-135748.eaf` — **a file
ELAN itself wrote on this machine**, not a fixture written by whoever wrote the
parser. T100's standing complaint is controls that cannot discriminate because
they were built from the same misunderstanding as the code; a real artefact
cannot be wrong in the same direction as my reading of the format.

Its expected content is asserted by VALUE, from T150: tiers `faults`/`scene`/
`audio`, 8 time slots, and 4 annotations at 140-6980, 6980-7230, 21000-32400
and 155600-182367 ms.

TIMES COME OUT IN SECONDS AS WELL AS MILLISECONDS, deliberately: every other
instrument here speaks in seconds (`t=158 s`, census task bands, run logs), and
an annotation that cannot be lined up against those by eye is still write-only
in practice.

Usage:
    scripts/eaf_read.py <file.eaf>          # the annotations, time-ordered
    scripts/eaf_read.py <file.eaf> --tier audio
    scripts/eaf_read.py <file.eaf> --dry-run
    scripts/eaf_read.py --self-check
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CONTROL_EAF = Path("/media/joh/extra/sin-punishment-archive/evidence/"
                   "2026-08-21/run_game-135748.eaf")


def parse(path):
    """-> (media_url, declared_tiers, [ {tier, start_ms, end_ms, text} ...]).

    RAISES on a document with no annotations. A reader that returns an empty
    list on a malformed file is indistinguishable from one reading a file the
    user genuinely left blank, and the whole point is to notice the difference.
    """
    root = ET.parse(path).getroot()
    md = root.find(".//MEDIA_DESCRIPTOR")
    media = md.get("MEDIA_URL") if md is not None else None

    declared = [t.get("TIER_ID") for t in root.findall(".//TIER")]

    slots = {}
    for ts in root.findall(".//TIME_SLOT"):
        v = ts.get("TIME_VALUE")
        if v is not None:
            slots[ts.get("TIME_SLOT_ID")] = int(v)

    out = []
    for tier in root.findall(".//TIER"):
        tid = tier.get("TIER_ID")
        for aa in tier.findall(".//ALIGNABLE_ANNOTATION"):
            r1, r2 = aa.get("TIME_SLOT_REF1"), aa.get("TIME_SLOT_REF2")
            if r1 not in slots or r2 not in slots:
                # An unresolvable reference is REPORTED, never defaulted -- the
                # same rule the census walker follows for segments. A span
                # invented from a missing slot would look exactly like a real one.
                raise ValueError(f"{path}: annotation {aa.get('ANNOTATION_ID')} "
                                 f"references unknown time slot ({r1}, {r2})")
            val = aa.find("ANNOTATION_VALUE")
            out.append({"tier": tid, "start_ms": slots[r1], "end_ms": slots[r2],
                        "text": (val.text or "").strip() if val is not None else ""})
    if not out:
        raise ValueError(f"{path}: no annotations found — refusing to report an "
                         f"empty read as an empty file")
    out.sort(key=lambda a: (a["start_ms"], a["tier"]))
    return media, declared, out


def show(path, only_tier=None):
    media, declared, ann = parse(path)
    print(f"{path}")
    if media:
        print(f"media: {media}")
    rows = [a for a in ann if only_tier is None or a["tier"] == only_tier]
    used = {a["tier"] for a in ann}
    print(f"{len(rows)} annotation(s)"
          + (f" on tier {only_tier!r}" if only_tier else
             f" on {len(used)} of {len(declared)} declared tier(s)") + "\n")
    # AN EMPTY TIER IS NAMED, NEVER OMITTED. `audio` is the return path for the
    # one thing I cannot check at all, so a silently absent tier and a tier the
    # user deliberately left blank would look identical -- and they mean
    # opposite things. Same rule as T76: hide content, never existence.
    empty = [t for t in declared if t not in used]
    if empty and not only_tier:
        print(f"  ** DECLARED BUT EMPTY: {', '.join(empty)} — "
              f"no annotation was made on {'these tiers' if len(empty) > 1 else 'this tier'} **\n")
    print(f"{'tier':<10} {'start':>10} {'end':>10}  {'dur':>7}   text")
    print("-" * 100)
    for a in rows:
        s, e = a["start_ms"] / 1000.0, a["end_ms"] / 1000.0
        print(f"{a['tier']:<10} {s:>8.2f}s {e:>8.2f}s  {e - s:>6.2f}s   {a['text']}")
    print("-" * 100)
    return 0


def self_check():
    n = bad = 0

    def chk(name, ok, why=""):
        nonlocal n, bad
        n += 1
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"  -- {why}"))

    if not CONTROL_EAF.exists():
        print(f"FAIL  the control file is missing: {CONTROL_EAF}")
        print("\n0/1 controls pass")
        return 1

    media, declared, ann = parse(CONTROL_EAF)

    # ASSERTED BY VALUE against T150, not by shape. A parser that read the file
    # and returned plausible-looking nonsense would pass a shape check.
    chk("finds all 4 annotations ELAN really wrote", len(ann) == 4, f"got {len(ann)}")
    chk("recovers all three DECLARED tiers", set(declared) == {"faults", "scene", "audio"},
        f"got {sorted(declared)}")
    # CORRECTED 2026-08-22 AGAINST THE FILE ITSELF. This control first asserted
    # that all three tiers CARRY annotations, on T150's wording that the file
    # "has tiers faults, scene, audio". They are DECLARED; only `faults` is
    # used. The control was wrong and the parser was right -- and the empty
    # `audio` tier is a finding, not a detail (A362).
    chk("only `faults` actually carries annotations",
        {a["tier"] for a in ann} == {"faults"},
        f"got {sorted({a['tier'] for a in ann})}")
    spans = sorted((a["start_ms"], a["end_ms"]) for a in ann)
    want = [(140, 6980), (6980, 7230), (21000, 32400), (155600, 182367)]
    chk("resolves every span to the exact millisecond", spans == want, f"got {spans}")
    chk("REF1/REF2 are not transposed — every span runs forwards",
        all(a["end_ms"] >= a["start_ms"] for a in ann), "a negative-duration span")
    chk("carries the media path back", bool(media) and media.endswith(".mp4"),
        f"got {media!r}")
    chk("output is time-ordered", [a["start_ms"] for a in ann] == sorted(
        a["start_ms"] for a in ann), "annotations came back unsorted")

    # THE TWO REFUSALS, which are what stop a silent empty read. Both must RAISE.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty.eaf"
        empty.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                         '<ANNOTATION_DOCUMENT><TIME_ORDER/></ANNOTATION_DOCUMENT>\n')
        try:
            parse(empty); ok = False
        except ValueError:
            ok = True
        chk("REFUSES a document with no annotations", ok,
            "an empty read is reported as an empty file")

        broken = Path(td) / "broken.eaf"
        broken.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<ANNOTATION_DOCUMENT>'
            '<TIME_ORDER><TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="10"/></TIME_ORDER>'
            '<TIER TIER_ID="t"><ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a1" '
            'TIME_SLOT_REF1="ts1" TIME_SLOT_REF2="ts9">'
            '<ANNOTATION_VALUE>x</ANNOTATION_VALUE>'
            '</ALIGNABLE_ANNOTATION></ANNOTATION></TIER></ANNOTATION_DOCUMENT>\n')
        try:
            parse(broken); ok = False
        except ValueError:
            ok = True
        chk("REFUSES an unresolvable time-slot reference", ok,
            "a span invented from a missing slot would pass as real")

    # THE DISCLOSURE ITSELF IS CONTROLLED: a reader that quietly omits an empty
    # tier passes every other check here while hiding the one thing worth seeing.
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        show(CONTROL_EAF)
    txt = buf.getvalue()
    chk("REPORTS the declared-but-empty tiers in normal output",
        "DECLARED BUT EMPTY" in txt and "audio" in txt.split("DECLARED BUT EMPTY")[1][:60],
        "an unused tier is invisible, so 'nobody annotated audio' reads as 'no audio tier'")

    print(f"\n{n - bad}/{n} controls pass")
    return 1 if bad else 0


def main():
    a = sys.argv[1:]
    if "--help" in a or "-h" in a or not a:
        print(__doc__)
        return 0
    if "--self-check" in a:
        return self_check()
    path = Path(a[0])
    if "--dry-run" in a:
        print(f"would read {path}")
        print(f"  exists: {path.exists()}"
              + (f", {path.stat().st_size} bytes" if path.exists() else ""))
        print("would print every annotation as tier / start / end / duration / text,"
              " time-ordered, in seconds and milliseconds. Writes nothing.")
        return 0
    if not path.exists():
        print(f"[eaf] REFUSING: no such file {path}", file=sys.stderr)
        return 2
    tier = a[a.index("--tier") + 1] if "--tier" in a and len(a) > a.index("--tier") + 1 else None
    try:
        return show(path, tier)
    except (ET.ParseError, ValueError) as e:
        print(f"[eaf] REFUSING: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
