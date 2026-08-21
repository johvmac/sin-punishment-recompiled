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
SCRIPTS = ROOT / "scripts"


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
    # --help must be handled BEFORE anything else. Without this, `--help` fell
    # through to the full test, which starts real X servers and records video
    # -- the T37 failure: a script that does not understand its arguments
    # running its side-effecting default anyway. Caught by lint_tools.py on its
    # first real run, 2026-08-20.
    a = sys.argv[1:]
    if "--help" in a or "-h" in a:
        print(__doc__)
        return 0
    unknown = [x for x in a if x != "--dry-run"]
    if unknown:
        print(f"[test_iso] unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print("[test_iso] REFUSING rather than starting an X server.", file=sys.stderr)
        return 2
    dry = "--dry-run" in a
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

    # ---- COVERAGE: every launcher must actually source the one copy --------
    #
    # T59's fix wired "the three callers". There were FOUR: gdb_threads.sh
    # launches the binary under gdb and inherited DISPLAY, so it would have put
    # a live game window on the real desktop with the keyboard connected to it
    # -- the exact incident T59 records. It sat uncovered because nothing
    # checked the LIST, only the file.
    #
    # So the list is DISCOVERED, not declared: anything under scripts/ that
    # launches the binary under gdb/rr, or via SDL_VIDEODRIVER, must source
    # display_isolate.sh. Add a launcher and this fails until it is wired.
    launchers, unwired = [], []
    for f in sorted(SCRIPTS.glob("*.sh")):
        s = f.read_text()
        if f.name in ("display_isolate.sh", "build_staleness.sh"):
            continue
        launches = ("SDL_VIDEODRIVER" in s) or bool(re.search(r"gdb .*--args|rr record", s))
        if not launches:
            continue
        launchers.append(f.name)
        if "display_isolate.sh" not in s:
            unwired.append(f.name)
    add("every launcher sources the ONE copy (list DISCOVERED, not declared)",
        not unwired,
        f"{len(launchers)} launcher(s); unwired: {' '.join(unwired) if unwired else 'none'}")

    # --- audio capture, wired in for A265 -----------------------------------
    iso = (SCRIPTS / "display_isolate.sh").read_text()
    rg = (SCRIPTS / "run_game.sh").read_text()

    add("audio capture lives in the ONE isolation copy, not a fourth copy",
        "snp_start_audio()" in iso,
        "defined in display_isolate.sh" if "snp_start_audio()" in iso else "not defined there")

    # DISCOVERED, not declared -- the same shape as the staleness check's caller
    # list. A hook wired into "the launcher I was thinking of" is how T128
    # happened, twice in one script.
    add("run_game.sh actually CALLS it (discovered, not assumed)",
        "snp_start_audio " in rg,
        "called after the PID exists" if "snp_start_audio " in rg else "NOT called")

    # ORDERING IS THE BUG THE FIRST WIRING HAD, INVERTED. The game must inherit
    # PULSE_SINK, so the capture must be prepared BEFORE the launch. Calling it
    # after meant chasing a sink-input that did not exist yet -- "Failure: No
    # such entity", an empty file, and a result indistinguishable from a silent
    # game. That is precisely the failure mode this whole wiring exists to
    # detect, so it must not be re-introducible without a control failing.
    add("audio is prepared BEFORE the launch (the game inherits PULSE_SINK)",
        "snp_start_audio" in rg and rg.find("snp_start_audio") < rg.find("PID=$!"),
        "ordering is prepare -> launch")
    add("it uses prepare/finish, NOT attach (no sink-input race)",
        '"$cap" prepare' in iso and '"$cap" finish' in iso and '"$cap" attach' not in iso,
        "attach hunts a live stream and gives up; prepare cannot race")

    add("SNP_AUDIO=0 opts out", 'SNP_AUDIO:-1' in iso and '= "0" ]' in iso,
        "default on, explicit opt-out")

    # THE DISCRIMINATING ONE. --cleanup is force-remove. Running it against a
    # capture observed_run.sh owns would destroy a run the user is sitting
    # through, so teardown must be gated on having started it ourselves.
    owned_gate = 'SNP_AUDIO_OWNED:-' in iso and iso.index("snp_display_cleanup()") < iso.index('SNP_AUDIO_OWNED:-}')
    add("cleanup tears down ONLY a capture we started (never the user's run)",
        owned_gate, "guarded on SNP_AUDIO_OWNED" if owned_gate else "UNGUARDED --cleanup would kill an observed run")

    add("it refuses to start a SECOND capture over an active one",
        "not starting a second" in iso,
        "two null sinks on one stream would give both a partial recording")

    # An artifact nobody measured is indistinguishable from one nobody looked at.
    add("the amplitude is REPORTED, not just the filename",
        "volumedetect" in iso and "ABOVE THE NOISE FLOOR" in iso,
        "a change in A97 has to be noticeable without anyone listening")

    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:62} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
