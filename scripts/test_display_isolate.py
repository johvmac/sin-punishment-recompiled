#!/usr/bin/env python3
"""Self-check for display_isolate.sh's screen recording (T83).

WHY THIS EXISTS
Scene identity was read off sampled stills three times and was wrong three
times -- A93 (10 s interval skipped the fade AND the title screen), A161 ("never
reaches the title screen" from two frames), and the inherited "title scene"
label on A99 that nobody had ever measured. The title screen is up for a few
seconds, so a sampler can miss it, and no sample can support "X never happened".
So every isolated run is now RECORDED.

THE CONTROL THAT MATTERS MOST IS THE NEGATIVE ONE. In `real` mode the display
is the USER'S DESKTOP. Recording it would capture whatever else they have on
screen -- mail, messages, anything. That must never happen, it is not a
tunable, and a control that only proves recording WORKS would not notice it
starting in the wrong mode. So this asserts both directions.

Everything here was verified to FAIL when the thing it checks is broken, per
T71 gate 2 -- not merely to pass when it works.

Usage:  scripts/test_display_isolate.py [--dry-run]
        --dry-run skips the two checks that start a real X server
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISO = ROOT / "scripts" / "display_isolate.sh"


def sh(script, env=None, timeout=90):
    """Run a bash snippet that sources display_isolate.sh."""
    e = dict(os.environ)
    e.setdefault("SNP_REC_MAX", "8")
    if env:
        e.update(env)
    p = subprocess.run(["bash", "-c", f'set -u; . "{ISO}"\n{script}'],
                       capture_output=True, text=True, env=e, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def main():
    dry = "--dry-run" in sys.argv
    checks = []

    def add(name, ok, detail):
        checks.append((name, ok, detail))

    src = ISO.read_text()

    # ---- static: the shape of the thing -----------------------------------
    add("recorder is bounded by -t, so a runaway cannot fill the drive",
        re.search(r'-t\s+"\$\{SNP_REC_MAX:-\d+\}"', src) is not None,
        "hard cap present" if "SNP_REC_MAX" in src else "NO -t cap")

    # SIGINT, not SIGKILL: ffmpeg must write the moov atom or the .mp4 is
    # unplayable. A truncated file looks like evidence and is not.
    #
    # Located with find(), NOT index(). index() RAISES when the substring is
    # absent -- which is precisely the broken case this check exists for -- and
    # the traceback aborted the run before the two live-server checks below,
    # leaving them unreported. A control that crashes instead of failing tells
    # you the tool is broken, not the thing under test, and it takes the rest of
    # the suite down with it.
    i_int = src.find("kill -INT")
    i_srv = src.find('kill "$SNP_ISO_PID"')
    add("cleanup stops the recorder with SIGINT before killing the X server",
        i_int != -1 and i_srv != -1 and i_int < i_srv,
        "recorder stopped first" if i_int != -1 and i_srv != -1 and i_int < i_srv
        else ("no `kill -INT` anywhere -- a SIGKILLed ffmpeg leaves an unplayable file"
              if i_int == -1 else "ordering wrong: X server dies before the recorder"))

    add("real-mode guard is present in snp_start_recording",
        re.search(r'SNP_ISO_MODE"\s*=\s*"real"', src) is not None,
        "guard present")

    if dry:
        print("[dry-run] skipping the two live-server checks\n")
    else:
        # ---- NEGATIVE control: real mode must NOT record ------------------
        with tempfile.TemporaryDirectory() as d:
            rc, out = sh('snp_isolate_display selftest_real; snp_display_cleanup',
                         {"SNP_ISO": "real", "SNP_REC_DIR": d})
            files = list(Path(d).iterdir())
            add("REAL mode records NOTHING (the user's desktop is not ours to film)",
                not files and "NOT recording" in out,
                f"{len(files)} file(s); banner={'yes' if 'NOT recording' in out else 'MISSING'}")

        # ---- POSITIVE control: isolated mode produces a real video --------
        with tempfile.TemporaryDirectory() as d:
            rc, out = sh('snp_isolate_display selftest_iso\n'
                         'sleep 3\n'
                         'snp_display_cleanup',
                         {"SNP_ISO_DISPLAY_MIN": "31", "SNP_REC_DIR": d})
            vids = sorted(Path(d).glob("*.mp4"))
            ok = bool(vids) and vids[0].stat().st_size > 1000
            detail = f"{len(vids)} file(s)"
            frames = 0
            if ok:
                pr = subprocess.run(
                    ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                     "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(vids[0])],
                    capture_output=True, text=True)
                m = re.search(r"\d+", pr.stdout or "")
                frames = int(m.group()) if m else 0
                detail = f"{vids[0].name}, {vids[0].stat().st_size} bytes, {frames} frames"
            # A file that exists but decodes to nothing is the truncation
            # failure this check is really for.
            add("ISOLATED mode produces a DECODABLE video with real frames",
                ok and frames > 10, detail)

            # The whole chain: lossless capture -> blackness verify -> crop ->
            # compress -> master deleted. A .mp4 at 640x480 proves every step
            # ran; a surviving .mkv means the crop REFUSED, and a 1280x720 .mp4
            # would mean it silently skipped.
            mkv = list(Path(d).glob("*.mkv"))
            dims = ""
            if vids:
                pr2 = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height", "-of", "csv=p=0", str(vids[0])],
                    capture_output=True, text=True)
                dims = pr2.stdout.strip()
            add("pipeline finalizes: cropped 640x480 .mp4, lossless master removed",
                dims == "640,480" and not mkv,
                f"dims={dims or 'none'}, leftover masters={len(mkv)}")

    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:62} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
