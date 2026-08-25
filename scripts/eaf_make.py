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
import re, sys, uuid, html
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


MIME_BY_SUFFIX = {".mp4": "video/mp4", ".mkv": "video/x-matroska",
                  ".flac": "audio/x-flac", ".wav": "audio/x-wav"}


def _descriptor(path: Path):
    url = "file://" + str(path.resolve())
    mime = MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")
    return (f'        <MEDIA_DESCRIPTOR MEDIA_URL={quoteattr(url)}\n'
            f'            MIME_TYPE={quoteattr(mime)}'
            f' RELATIVE_MEDIA_URL={quoteattr("./" + path.name)}/>\n'), url


def build(video: Path, tiers, question=None, date="2026-01-01T00:00:00+00:00",
          audio: Path = None):
    """Return the .eaf text. `video` is used ABSOLUTE and RELATIVE, because ELAN
    falls back to the relative path when the file has moved -- and these files
    live on a removable archive drive whose mount point has changed before.

    AUDIO IS A SECOND DESCRIPTOR, NOT AN ALTERNATIVE TO THE VIDEO. **Our .mp4
    carries no audio track** -- the sound finalises to a .flac beside it (T160)
    -- so a project linking the video alone hands the user a SILENT FILM. T150
    wrote that trap down in advance ("the generated project must link BOTH
    media descriptors or the user annotates a silent video and A97 stays
    exactly where it is") and the first version of this tool walked into it
    anyway: one descriptor, MIME hardcoded to video/mp4.
    """
    out = [HDR.format(date=quoteattr(date))]
    out.append('    <HEADER MEDIA_FILE="" TIME_UNITS="milliseconds">\n')
    desc, url = _descriptor(video)
    out.append(desc)
    if audio is not None:
        out.append(_descriptor(audio)[0])
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


STAMP = re.compile(r"(\d{6})")
PAIR_WINDOW_S = 120


def _stamp_seconds(name):
    """HHMMSS out of a run filename -> seconds since midnight, or None."""
    m = STAMP.search(name)
    if not m:
        return None
    v = m.group(1)
    h, mi, s = int(v[0:2]), int(v[2:4]), int(v[4:6])
    if h > 23 or mi > 59 or s > 59:
        return None
    return h * 3600 + mi * 60 + s


def find_audio(video: Path):
    """The .flac from THIS run, matched by timestamp -- never just the first one.

    THE BUG THIS REPLACES ACTUALLY HAPPENED (2026-08-25): the first version
    globbed `run_game*.flac` and took `sorted(...)[0]`, which paired the 11:40
    video with the 08:50 sound. **A project pairing one run's video with
    another run's audio is worse than one with no audio at all** -- it plays,
    the timestamps look plausible, and every annotation made against it is
    wrong in a way nobody can see. The tool's own controls passed, because the
    fixture directory contained exactly one .flac.

    So: nearest timestamp, and it must be INSIDE a window. `run_game.sh` starts
    the recorder a second or two before the audio sink, so the pair differ by
    seconds; anything further apart is a different run and returns None, which
    makes the caller refuse rather than guess.
    """
    vt = _stamp_seconds(video.stem)
    best, best_d = None, None
    for cand in sorted(video.parent.glob("*.flac")):
        at = _stamp_seconds(cand.stem)
        if vt is None or at is None:
            continue
        d = abs(at - vt)
        if best_d is None or d < best_d:
            best, best_d = cand, d
    if best is not None and best_d is not None and best_d <= PAIR_WINDOW_S:
        return best
    return None


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

        # T150's NAMED TRAP, and this tool fell into it on its first version:
        # one descriptor, MIME hardcoded video/mp4. Our .mp4 has NO audio track
        # (T160), so that project plays silent and the user annotates a mute
        # film -- leaving A97 exactly where it was.
        #
        # THE CONTROL IS SHAPED THE WAY T160 HAD TO SHAPE ITS OWN: it demands
        # BOTH descriptors and the AUDIO MIME. Counting descriptors alone, or
        # checking only that a MEDIA_URL exists, would PASS on the video-only
        # file -- which is the exact bug.
        snd = Path(td) / "clip.flac"; snd.write_bytes(b"\0")
        both = build(vid, tiers, audio=snd)
        chk("BOTH media are linked when audio is given",
            both.count("<MEDIA_DESCRIPTOR") == 2
            and 'MIME_TYPE="audio/x-flac"' in both
            and 'RELATIVE_MEDIA_URL="./clip.flac"' in both,
            "video-only means a silent film and A97 stays where it is (T150)")

        # VERIFIED TO FAIL: the video-only build must go red on that control.
        chk("that control FAILS on a video-only file (so it discriminates)",
            not (x.count("<MEDIA_DESCRIPTOR") == 2
                 and 'MIME_TYPE="audio/x-flac"' in x),
            "the control would pass on exactly the defect it exists to catch")

        # PAIRING BY TIME, NOT BY SORT ORDER. This control exists because the
        # first version of find_audio really did pair an 11:40 video with an
        # 08:50 sound -- and the controls above all PASSED, because the fixture
        # had one .flac in it. A directory with exactly one candidate cannot
        # discriminate a chooser.
        pdir = Path(td) / "pair"; pdir.mkdir()
        (pdir / "run_game-114051.mp4").write_bytes(b"\0")
        (pdir / "run_game-085038-audio.flac").write_bytes(b"\0")   # a different run
        (pdir / "run_game-114052-audio.flac").write_bytes(b"\0")   # THIS run
        picked = find_audio(pdir / "run_game-114051.mp4")
        chk("the sound of THIS run is chosen, not the first in sort order",
            picked is not None and picked.name == "run_game-114052-audio.flac",
            f"picked {picked.name if picked else None} -- cross-run pairing is "
            "worse than no audio: it plays, and every annotation is silently wrong")

        # VERIFIED TO FAIL the other way: with only a far-off candidate there is
        # no pair, and None must be returned so the caller REFUSES. Returning
        # the far one 'because it is all there is' is the original bug.
        far = Path(td) / "far"; far.mkdir()
        (far / "run_game-114051.mp4").write_bytes(b"\0")
        (far / "run_game-085038-audio.flac").write_bytes(b"\0")
        chk("a far-off sound is NOT paired -- refuse rather than guess",
            find_audio(far / "run_game-114051.mp4") is None,
            "an out-of-window match is a different run")

        # MIME comes from the suffix, not from a hardcoded string -- the
        # original defect was a constant that happened to be right once.
        mkv = Path(td) / "clip.mkv"; mkv.write_bytes(b"\0")
        wav = Path(td) / "clip.wav"; wav.write_bytes(b"\0")
        other = build(mkv, tiers, audio=wav)
        chk("MIME follows the suffix rather than a hardcoded constant",
            'MIME_TYPE="video/x-matroska"' in other
            and 'MIME_TYPE="audio/x-wav"' in other,
            "a constant that is right once is not a rule")

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
    audio = None
    no_audio = "--no-audio" in argv
    argv = [a for a in argv if a != "--no-audio"]
    while i < len(argv):
        a = argv[i]
        if a == "--tier":    tiers.append(argv[i + 1]); i += 2
        elif a == "-o":      out = Path(argv[i + 1]);   i += 2
        elif a == "--question": question = argv[i + 1]; i += 2
        elif a == "--audio": audio = Path(argv[i + 1]); i += 2
        else:                pos.append(a);             i += 1
    if not pos:
        print("[eaf] need a VIDEO", file=sys.stderr); return 2
    video = Path(pos[0])
    if not video.exists():
        print(f"[eaf] no such video: {video}", file=sys.stderr); return 2
    # FIND THE SOUND, because forgetting it is silent in both senses. Our .mp4
    # has no audio track (T160), so a project with only the video plays mute
    # and the user annotates a silent film -- exactly what T150 warned about.
    if audio is None and not no_audio:
        audio = find_audio(video)
    if audio is not None and not audio.exists():
        print(f"[eaf] no such audio: {audio}", file=sys.stderr); return 2
    if audio is None and not no_audio:
        # REFUSE rather than quietly produce a mute project. --no-audio is the
        # way to say you meant it; a missing file must never be a default.
        print("[eaf] REFUSING: no audio found beside the video and --no-audio "
              "was not given. Our .mp4 has NO audio track, so this project "
              "would play silent and A97 would stay exactly where it is "
              "(T150). Pass --audio <file>, or --no-audio if that is intended.",
              file=sys.stderr)
        return 2
    if not tiers:
        print("[eaf] REFUSING: no --tier given. An eaf with no tiers gives the "
              "user nowhere to write, and looks fine.", file=sys.stderr); return 2
    if dry:
        print("=== DRY RUN — nothing written ===")
        print(f"video   : {video.resolve()}")
        print(f"audio   : {audio.resolve() if audio else '(NONE — --no-audio)'}")
        print(f"tiers   : {tiers}")
        print(f"question: {question or '(none)'}")
        print(f"would write: {out or '(stdout)'}")
        print("annotations: NONE — the tiers arrive empty on purpose")
        return 0
    from datetime import datetime, timezone
    text = build(video, tiers, question,
                 datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                 audio=audio)
    if out: out.write_text(text); print(f"[eaf] wrote {out}")
    else:   sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
