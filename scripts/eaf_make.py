#!/usr/bin/env python3
"""Build an ELAN `.eaf` for a video, with named EMPTY tiers for the user.

WHY THIS EXISTS (T150, and the user's request 2026-08-25)
--------------------------------------------------------
`eaf_read.py` reads the user's annotations back as data. Nothing WROTE the file
they annotate into -- A266's `.eaf` was made by hand in ELAN, and every new
question meant another hand-built file. T150 is the open item for wiring ELAN
into the loop; this is the writing half.

**IT DELIBERATELY PRE-FILLS NOTHING.** The tiers arrive empty and named after
the question. That is the same rule the status page's own control enforces --
"NO answer key reaches the page" -- and it matters more here, not less: A383
found the user's labels disagreed with the machine consensus on 3 of 5
entries where the machines were unanimous, so an annotation file that showed
them my expected answer would be destroying the only independent reading we
get. A marker saying "the interesting moment is at 12.4s" is an answer key.

WHAT IT WILL NOT DO
-------------------
It writes tiers and media links. It does not write annotations, because an
annotation is the user's. `--dry-run` prints the tiers and the media path and
exits without writing (T71 gate 1).

    scripts/eaf_make.py --dry-run VIDEO --tier a --tier b
    scripts/eaf_make.py VIDEO -o OUT.eaf --tier a --tier b [--question "..."]
    scripts/eaf_make.py --self-check
"""
import sys, uuid, html
from pathlib import Path
from xml.sax.saxutils import quoteattr

HDR = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<ANNOTATION_DOCUMENT AUTHOR="snp" DATE={date} FORMAT="3.0" VERSION="3.0"\n'
       '    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
       ' xsi:noNamespaceSchemaLocation="http://www.mpi.nl/tools/elan/EAFv3.0.xsd">\n')

TAIL = ('    <LINGUISTIC_TYPE GRAPHIC_REFERENCES="false"'
        ' LINGUISTIC_TYPE_ID="default-lt" TIME_ALIGNABLE="true"/>\n'
        '    <CONSTRAINT DESCRIPTION="Time subdivision of parent annotation\'s time'
        ' interval, no time gaps allowed within this interval"'
        ' STEREOTYPE="Time_Subdivision"/>\n'
        '    <CONSTRAINT DESCRIPTION="Symbolic subdivision of a parent annotation.'
        ' Annotations refering to the same parent are ordered"'
        ' STEREOTYPE="Symbolic_Subdivision"/>\n'
        '    <CONSTRAINT DESCRIPTION="1-1 association with a parent annotation"'
        ' STEREOTYPE="Symbolic_Association"/>\n'
        '    <CONSTRAINT DESCRIPTION="Time alignable annotations within the parent'
        ' annotation\'s time interval, gaps are allowed" STEREOTYPE="Included_In"/>\n'
        '</ANNOTATION_DOCUMENT>\n')


def build(video: Path, tiers, question=None, date="2026-01-01T00:00:00+00:00"):
    """Return the .eaf text. `video` is used ABSOLUTE and RELATIVE, because ELAN
    falls back to the relative path when the file has moved -- and these files
    live on a removable archive drive whose mount point has changed before."""
    url = "file://" + str(video.resolve())
    out = [HDR.format(date=quoteattr(date))]
    out.append('    <HEADER MEDIA_FILE="" TIME_UNITS="milliseconds">\n')
    out.append(f'        <MEDIA_DESCRIPTOR MEDIA_URL={quoteattr(url)}\n'
               f'            MIME_TYPE="video/mp4"'
               f' RELATIVE_MEDIA_URL={quoteattr("./" + video.name)}/>\n')
    out.append(f'        <PROPERTY NAME="URN">urn:nl-mpi-tools-elan-eaf:'
               f'{uuid.uuid5(uuid.NAMESPACE_URL, url)}</PROPERTY>\n')
    if question:
        # The QUESTION belongs in the file, not in a chat message that scrolls
        # away -- A266's eaf outlived the conversation that produced it.
        out.append(f'        <PROPERTY NAME="question">{html.escape(question)}'
                   f'</PROPERTY>\n')
    out.append('        <PROPERTY NAME="lastUsedAnnotationId">0</PROPERTY>\n')
    out.append('    </HEADER>\n')
    # TIME_ORDER must be present and may be empty; ELAN writes it back populated.
    out.append('    <TIME_ORDER/>\n')
    for t in tiers:
        out.append(f'    <TIER LINGUISTIC_TYPE_REF="default-lt"'
                   f' TIER_ID={quoteattr(t)}/>\n')
    out.append(TAIL)
    return "".join(out)


def self_check():
    import tempfile, re
    fails = n = 0
    def chk(name, ok, why=""):
        nonlocal fails, n
        n += 1
        print(("ok    " if ok else "FAIL  ") + name + ("" if ok else f"  -- {why}"))
        if not ok: fails += 1

    with tempfile.TemporaryDirectory() as td:
        vid = Path(td) / "clip.mp4"; vid.write_bytes(b"\0")
        tiers = ["how-it-goes", "notes"]
        x = build(vid, tiers, question="does the title cut or fade?")

        chk("every requested tier appears",
            all(f'TIER_ID="{t}"' in x for t in tiers), "a dropped tier loses a question")

        # THE CONTROL THAT MATTERS: no annotation content of ANY kind. An empty
        # file is the whole point, and "I accidentally seeded a marker" is the
        # failure that would quietly turn this into an answer key.
        chk("writes NO annotations -- nothing to lead the user",
            "<ANNOTATION_VALUE>" not in x and "<ALIGNABLE_ANNOTATION" not in x,
            "a pre-filled span tells them where to look, which is A383's warning")

        # VERIFIED TO FAIL: seed one and the same control must go red.
        bad = x.replace("<TIME_ORDER/>",
                        '<TIME_ORDER><TIME_SLOT TIME_SLOT_ID="ts1" TIME_VALUE="1"/>'
                        '</TIME_ORDER>').replace(
              '<TIER LINGUISTIC_TYPE_REF="default-lt" TIER_ID="notes"/>',
              '<TIER LINGUISTIC_TYPE_REF="default-lt" TIER_ID="notes">'
              '<ANNOTATION><ALIGNABLE_ANNOTATION ANNOTATION_ID="a1"'
              ' TIME_SLOT_REF1="ts1" TIME_SLOT_REF2="ts1">'
              '<ANNOTATION_VALUE>look here</ANNOTATION_VALUE>'
              '</ALIGNABLE_ANNOTATION></ANNOTATION></TIER>')
        chk("that control FAILS on a seeded file (so it discriminates)",
            "<ANNOTATION_VALUE>" in bad,
            "the control cannot detect the thing it exists to detect")

        chk("media is linked both absolutely and relatively",
            'MEDIA_URL="file://' in x and 'RELATIVE_MEDIA_URL="./clip.mp4"' in x,
            "the archive drive's mount point has changed before")

        chk("the question is carried IN the file",
            "does the title cut or fade?" in x, "a question in chat scrolls away")

        # Round-trip through the reader that will consume it.
        p = Path(td) / "t.eaf"; p.write_text(x)
        import xml.etree.ElementTree as ET
        try:
            got = [t.get("TIER_ID") for t in ET.parse(p).getroot().iter("TIER")]
            ok = got == tiers
        except Exception as e:
            ok, got = False, repr(e)
        chk("it parses as XML and the tiers round-trip", ok, f"got {got}")

    print(f"\n{n - fails}/{n} controls pass")
    return 1 if fails else 0


def main(argv):
    if "--self-check" in argv: return self_check()
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__); return 0
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    tiers, out, question, pos = [], None, None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--tier":    tiers.append(argv[i + 1]); i += 2
        elif a == "-o":      out = Path(argv[i + 1]);   i += 2
        elif a == "--question": question = argv[i + 1]; i += 2
        else:                pos.append(a);             i += 1
    if not pos:
        print("[eaf] need a VIDEO", file=sys.stderr); return 2
    video = Path(pos[0])
    if not video.exists():
        print(f"[eaf] no such video: {video}", file=sys.stderr); return 2
    if not tiers:
        print("[eaf] REFUSING: no --tier given. An eaf with no tiers gives the "
              "user nowhere to write, and looks fine.", file=sys.stderr); return 2
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(f"video   : {video.resolve()}")
        print(f"tiers   : {tiers}")
        print(f"question: {question or '(none)'}")
        print(f"would write: {out or '(stdout)'}")
        print("annotations: NONE — the tiers arrive empty on purpose")
        return 0
    from datetime import datetime, timezone
    text = build(video, tiers, question,
                 datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    if out: out.write_text(text); print(f"[eaf] wrote {out}")
    else:   sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
