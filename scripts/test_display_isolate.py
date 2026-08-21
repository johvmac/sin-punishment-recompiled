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

    # --- a SECOND video recording must be refused (T141) --------------------
    # The audio path has refused this since T133; the video path never did, so
    # `snp_isolate_display` + a later `snp_start_recording` started two ffmpegs
    # and orphaned the first. Its lossless master was never finalised: three of
    # them were 1,353 MB, 42% of the archive, and were nearly deleted as junk
    # when they were the only full-length ares reference captures (T140).
    add("a SECOND video recording is refused over a live one",
        "NOT starting a second recording" in src,
        "two ffmpegs orphan the first master AND contend for CPU mid-run")
    # DISCRIMINATING: the guard must test a LIVE pid, not merely a set variable.
    # SNP_REC_FILE survives a finished recording, so keying on it would refuse
    # every legitimate second run in the same shell.
    add("the second-recording guard tests a LIVE pid, not a stale variable",
        re.search(r'SNP_REC_PID:-\}"?\s*\]\s*&&\s*kill -0 "\$SNP_REC_PID"', src)
        or ('kill -0 "$SNP_REC_PID"' in src.split("NOT starting a second")[0][-400:]),
        "keying on SNP_REC_FILE would refuse a legitimate later run")

    # THE CALLER THAT HIT IT, checked by DISCOVERY not by memory: any script
    # that sets SNP_REC_DIR must do so BEFORE it isolates, or its recording
    # lands in the default directory and a redirect afterwards orphans it.
    # COMMENTS ARE STRIPPED FIRST. The first version scanned raw text and
    # flagged ares_capture.sh because the comment EXPLAINING this very fix
    # names `snp_isolate_display` above the assignment. A checker that reads
    # prose as code fires on the documentation of its own rule -- and the
    # obvious "fix" is to reword the comment, which teaches exactly the wrong
    # lesson. Same class as audit.py's probe check matching any entry that
    # merely said the word "probe".
    # ANCHORED TO STATEMENTS, not to text anywhere in the file. This check gave
    # TWO false positives in a row, both on ares_capture.sh and both from
    # matching prose instead of code: first the comment explaining this very
    # fix, then the script's OWN self-test, which greps for the strings
    # 'snp_isolate_display' and 'SNP_REC_DIR' in that order. So it now requires
    # an actual assignment and an actual call, each at the start of a line.
    # Same class as audit.py's probe check firing on any entry that merely said
    # the word "probe" -- a predicate matched against a wider thing than the one
    # it describes.
    ASSIGN = re.compile(r"^\s*(?:export\s+)?SNP_REC_DIR=", re.M)
    CALL = re.compile(r"^\s*snp_isolate_display\b", re.M)
    late = []
    for f in sorted(SCRIPTS.glob("*.sh")):
        code = "\n".join(re.sub(r"(^|\s)#.*$", "", l)
                         for l in f.read_text().split("\n"))
        a, c = ASSIGN.search(code), CALL.search(code)
        if not a or not c:
            continue
        if a.start() > c.start():
            late.append(f.name)
    add("every caller sets SNP_REC_DIR BEFORE isolating (discovered, not declared)",
        not late,
        f"late: {' '.join(late) if late else 'none'}")

    # --- the renderer identity must SURVIVE the run (2026-08-21) ------------
    # RT64 prints "Device Name"/"Device Vendor"/"Driver Version" to STDOUT at
    # startup. run_game.sh merged both streams all along, but stdout to a FILE
    # is block-buffered and every run ends in `kill -9`, so the partial buffer
    # was discarded: the GPU identity appeared in 2 of 34 logs. It was being
    # written and thrown away, which reads exactly like never being written.
    add("run_game.sh line-buffers stdout so the GPU identity survives kill -9",
        "stdbuf -oL" in rg,
        "block-buffered stdout is discarded by SIGKILL; the device lines vanish")
    # DISCRIMINATING: it must wrap the BINARY, not sit somewhere harmless. A
    # `stdbuf` anywhere in the file would satisfy a bare substring test.
    add("stdbuf wraps the game binary on the launch line",
        re.search(r'stdbuf -oL "\$BIN"', rg) is not None,
        "stdbuf must be on the process whose stdout we are keeping")

    # SNP_ISO MUST BE ACCEPTED AS AN ARGUMENT, LIKE SNP_VISIBLE (A312).
    # run_game.sh scanned argv for SNP_VISIBLE and not for SNP_ISO, so
    # `run_game.sh N log SNP_ISO=xephyr` forwarded the assignment to the GAME's
    # env and left display_isolate.sh -- which runs in run_game.sh's own shell --
    # reading an unset SNP_ISO. A documented command silently chose a different
    # display mode from the one written on it.
    add("run_game.sh scans argv for SNP_ISO, not only SNP_VISIBLE",
        re.search(r'case "\$a" in SNP_ISO=\*\)', rg) is not None
        and re.search(r'export SNP_ISO="\$WANT_ISO"', rg) is not None,
        "a trailing SNP_ISO=... would reach the game but not the isolation code")

    # THE OUTPUT PATH REFUSALS (A312) -- BEHAVIOURAL, not a grep. Both fire
    # before the launch, so invoking for real costs nothing and no game runs.
    # The needle is the ACCIDENT THAT HAPPENED: a stale prompt line fused
    # `...inspector-depth.log` and `scripts/run_game.sh` into one token, which
    # became $2. The launch redirects the game's stdout over $2.
    _tmp = Path(tempfile.mkdtemp())
    _r1 = subprocess.run([str(SCRIPTS / "run_game.sh"), "5", "scripts/run_game.sh"],
                         capture_output=True, text=True, timeout=60)
    _r2 = subprocess.run([str(SCRIPTS / "run_game.sh"), "5", str(_tmp / "no" / "such" / "x.log")],
                         capture_output=True, text=True, timeout=60)
    _r3 = subprocess.run([str(SCRIPTS / "run_game.sh"), "--help"],
                         capture_output=True, text=True, timeout=60)
    add("a log path that is a SCRIPT is refused before any launch",
        _r1.returncode == 2 and "REFUSING" in _r1.stderr,
        f"rc={_r1.returncode}; the redirect would truncate the file it names")
    add("a log path in a NONEXISTENT directory is refused, not failed deep inside",
        _r2.returncode == 2 and "REFUSING" in _r2.stderr,
        f"rc={_r2.returncode}; otherwise it dies at the launch with a bare rc=1")
    # AND THE REFUSALS MUST NOT EAT LEGITIMATE CALLS -- a control that refuses
    # everything is not a control. --help must still work.
    add("the refusals do not swallow a legitimate invocation (--help still works)",
        _r3.returncode == 0 and "Usage" in _r3.stdout,
        f"rc={_r3.returncode}; a guard that refuses everything discriminates nothing")

    # THE RUN LOG MUST RECORD THE MODE USED, NOT THE ARGV IT WAS HANDED (A310).
    # SNP_VISIBLE is accepted two ways -- as an argument AND from the
    # environment -- but the env column logged only `"${*:-none}"`, so the
    # prescribed shell-prefix form produced a REAL-display row indistinguishable
    # from a headless one. check_ledger.py's changed-signature trigger reads
    # that column to decide whether a SIGSEGV is a regression or a user at the
    # keyboard, and it duly called a deliberate user-triggered crash "a HEADLESS
    # SIGSEGV".
    #
    # BEHAVIOUR-SHAPED, NOT A BARE GREP FOR THE NAME: the fix is only real if
    # the RESOLVED value reaches the printf. So require the guard to test
    # SNP_VISIBLE, and require the printf's last field to be the derived
    # variable rather than "$*" -- the second half is what a re-broken version
    # would fail. Matching only the first half would pass on code that computes
    # ENVCOL and then logs "$*" anyway.
    _guard = re.search(r'SNP_VISIBLE:-0.*==\s*"1"', rg) is not None
    _used = re.search(r'"\$\{ENVCOL:-none\}"\s*>>\s*"\$RUNLOG"', rg) is not None
    _stale = re.search(r'"\$\{\*:-none\}"\s*>>\s*"\$RUNLOG"', rg) is not None
    add("the run log records the display mode ACTUALLY USED, not just argv",
        _guard and _used and not _stale,
        f"guard={_guard} derived-value-logged={_used} old-argv-form-still-there={_stale}")

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
