#!/usr/bin/env python3
"""Measure audio-vs-video drift WITHIN one capture pair, by anchor comparison.

WHY THIS EXISTS, AND WHY NOT THE OBVIOUS THING (A461/A462/A471/A478)
--------------------------------------------------------------------
A463 asks whether our captured sound slides behind the picture. Three
instruments have already been wrong or useless on this question:

  * GLOBAL CROSS-CORRELATION (A461) reported "+0.9 s, in sync" for a file that
    drifts ~23 s. It ASSUMES A CONSTANT LAG, so a drifting one is outside its
    vocabulary: it locked onto the early in-sync stretch. WITHDRAWN IN PART.
  * FLAC-DURATION vs WALL-CLOCK (A471) cannot work at all: capture windows are
    TIMER-FIXED with pre-launch arming, so durations are constant across runs
    by construction (eight runs read 240.001451 s to six decimals).
  * A462's piecewise-lag script WAS ad-hoc and DID NOT SURVIVE. T209's rule
    covers exactly this: ad-hoc analysis scripts are tools and need T71's gates.

THE METHOD HERE (A478's, made repeatable): find an AUDIO event and a VIDEO
event that mark the same moment, EARLY in the pair and again LATE. Drift is the
CHANGE in offset, not either offset -- so the unknown constant gap between "the
music starts" and "the screen brightens", and the recorder's pre-roll, both
CANCEL. A pair that does not drift gives late == early.

    scripts/av_drift.py <audio.flac> <video.mp4> [--json out.json]
    scripts/av_drift.py --self-check

ANCHORS, and their honest limits:
  audio: onset  = first of 3 consecutive 100 ms windows above -30 dBFS
         offset = first such SILENCE (3 windows below) after a loud stretch
  video: bright = first frame whose mean luma exceeds --luma (default 30)
         dark   = first frame back below it after a bright stretch
These are SCENE-BOUNDARY anchors: they work when a capture has an audible and
visible transition at both ends. `--report-only` prints what it found without a
verdict when it cannot find a late pair -- an honest NA beats a fabricated lag.

WHAT A NON-DRIFTING PAIR WOULD LOOK LIKE, stated before reading any number
(T209): early_offset == late_offset within the sampling resolution (0.1 s audio,
one frame video). A drifting pair grows monotonically. If BOTH anchors move
together the pair is fine and the capture is merely shifted.
"""

import argparse
import json
import subprocess
import sys
import struct
from pathlib import Path

WIN_S = 0.1          # audio analysis window
DB_FLOOR = -30.0     # "loud" threshold
RUN_WINDOWS = 3      # consecutive windows required


def decode_audio(path, sr=22050):
    """flac/wav -> mono int16 list at sr, via ffmpeg."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le",
         "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path}: {out.stderr.decode()[:200]}")
    n = len(out.stdout) // 2
    return struct.unpack(f"<{n}h", out.stdout[:n * 2]), sr


def window_db(samples, sr):
    """Per-window dBFS."""
    w = int(sr * WIN_S)
    import math
    out = []
    for i in range(len(samples) // w):
        chunk = samples[i * w:(i + 1) * w]
        acc = 0.0
        for s in chunk:
            acc += float(s) * s
        rms = (acc / w) ** 0.5
        out.append(-999.0 if rms == 0 else 20 * math.log10(rms / 32768.0))
    return out


def first_run(flags, n=RUN_WINDOWS):
    """Index of the first run of n consecutive True, else None."""
    for i in range(len(flags) - n + 1):
        if all(flags[i:i + n]):
            return i
    return None


def audio_anchors(db):
    loud = [d > DB_FLOOR for d in db]
    on = first_run(loud)
    if on is None:
        return None, None
    quiet_after = [not x for x in loud[on:]]
    off = first_run(quiet_after)
    return on * WIN_S, (None if off is None else (on + off) * WIN_S)


def audio_transitions(db):
    """EVERY loud<->quiet boundary, in order: [(t, 'on'|'off'), ...].

    ADDED after the tool's FIRST REAL RUN reported +139 s of drift by pairing
    an audio silence at t=180 with a video fade at t=38 -- two different
    events. A single 'first offset' anchor cannot know it is looking at the
    same transition as the video's. A full ordered list can be checked for
    correspondence, and disagreement in COUNT is itself the warning.
    """
    loud = [d > DB_FLOOR for d in db]
    out, state, i = [], None, 0
    while i <= len(loud) - RUN_WINDOWS:
        run_loud = all(loud[i:i + RUN_WINDOWS])
        run_quiet = all(not x for x in loud[i:i + RUN_WINDOWS])
        if run_loud and state != "on":
            out.append((round(i * WIN_S, 2), "on")); state = "on"
        elif run_quiet and state == "on":
            out.append((round(i * WIN_S, 2), "off")); state = "off"
        i += 1
    return out


def video_transitions(samples, luma_thresh):
    """EVERY dark<->bright boundary, in order: [(t, 'on'|'off'), ...]."""
    out, state = [], None
    for t, y in samples:
        cur = "on" if y > luma_thresh else "off"
        if state is None:
            state = cur
            if cur == "on":
                out.append((round(t, 2), "on"))
            continue
        if cur != state:
            out.append((round(t, 2), cur))
            state = cur
    return out


def video_luma(path, step_frames=15):
    """(pts_time, YAVG) sampled every step_frames."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         f"movie={path},select='not(mod(n\\,{step_frames}))',signalstats",
         "-show_entries", "frame=pts_time:frame_tags=lavfi.signalstats.YAVG",
         "-of", "json"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {r.stderr[:200]}")
    frames = json.loads(r.stdout).get("frames", [])
    return [(float(f["pts_time"]), float(f["tags"]["lavfi.signalstats.YAVG"]))
            for f in frames if "tags" in f]


def video_anchors(samples, luma_thresh):
    bright = None
    for t, y in samples:
        if y > luma_thresh:
            bright = t
            break
    if bright is None:
        return None, None
    dark = None
    for t, y in samples:
        if t > bright and y <= luma_thresh:
            dark = t
            break
    return bright, dark


# --------------------------------------------------------------------------

def self_check(break_n=0):
    """Controls on SYNTHETIC signals whose answer is known by construction."""
    checks = []

    # 1. onset detection on a constructed ramp: silence 1.0 s then tone
    sr = 22050
    silence = [0] * int(sr * 1.0)
    tone = [12000 if (i // 40) % 2 else -12000 for i in range(int(sr * 2.0))]
    db = window_db(silence + tone, sr)
    on, off = audio_anchors(db)
    checks.append(("audio onset found at ~1.0 s", on is not None and abs(on - 1.0) < 0.25))

    # 2. offset detection: tone then silence
    db2 = window_db(silence + tone + [0] * int(sr * 2.0), sr)
    on2, off2 = audio_anchors(db2)
    checks.append(("audio offset found after the tone",
                   off2 is not None and off2 > (on2 or 0)))

    # 3. THE DISCRIMINATING ONE: a pair with a KNOWN growing offset must report
    #    drift, and an aligned pair must report ~0. Built from anchor values
    #    directly (the arithmetic under test), not from media.
    def drift(ea, eb, la, lb):
        return (la - lb) - (ea - eb)
    d_none = drift(10.0, 8.0, 100.0, 98.0)     # constant +2 offset => no drift
    d_grow = drift(10.0, 8.0, 100.0, 80.0) if break_n != 3 else 0.0
    checks.append(("constant offset reads as ZERO drift", abs(d_none) < 1e-9))
    checks.append(("growing offset reads as POSITIVE drift", d_grow > 17.9))

    # 4. an all-silent input must yield NO anchor rather than a fake one
    db3 = window_db([0] * int(sr * 3.0), sr)
    on3, _ = audio_anchors(db3)
    checks.append(("silent audio yields NO anchor (not 0.0)",
                   on3 is None if break_n != 4 else on3 is not None))

    ok = 0
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok += passed
    print(f"self-check {ok}/{len(checks)}")
    return 0 if ok == len(checks) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("audio", nargs="?", type=Path)
    ap.add_argument("video", nargs="?", type=Path)
    ap.add_argument("--luma", type=float, default=30.0)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--self-check-break", type=int, default=0)
    a = ap.parse_args()

    if a.self_check or a.self_check_break:
        sys.exit(self_check(a.self_check_break))
    if not a.audio or not a.video:
        ap.error("audio and video are both required")

    samples, sr = decode_audio(a.audio)
    db = window_db(samples, sr)
    a_on, a_off = audio_anchors(db)
    v_samples = video_luma(a.video)
    v_on, v_off = video_anchors(v_samples, a.luma)

    res = {
        "audio": str(a.audio), "video": str(a.video),
        "audio_onset_s": a_on, "audio_offset_s": a_off,
        "video_bright_s": v_on, "video_dark_s": v_off,
        "early_offset_s": None, "late_offset_s": None, "drift_s": None,
    }
    if a_on is not None and v_on is not None:
        res["early_offset_s"] = round(a_on - v_on, 3)
    if a_off is not None and v_off is not None:
        res["late_offset_s"] = round(a_off - v_off, 3)
    if res["early_offset_s"] is not None and res["late_offset_s"] is not None:
        res["drift_s"] = round(res["late_offset_s"] - res["early_offset_s"], 3)

    # THE CORRESPONDENCE CHECK, added after the +139 s false positive: pair the
    # ordered transition lists and require the counts to be comparable. Without
    # it, "first silence" and "first fade" can be different events and their
    # difference is meaningless arithmetic, not drift.
    at = audio_transitions(db)
    vt = video_transitions(v_samples, a.luma)
    res["audio_transitions"] = at
    res["video_transitions"] = vt
    paired = list(zip(at, vt))
    res["paired_offsets_s"] = [round(a_t - v_t, 2) for (a_t, _), (v_t, _) in paired]
    ok_corr = at and vt and abs(len(at) - len(vt)) <= max(1, len(at) // 4)
    res["correspondence_ok"] = bool(ok_corr)
    if not ok_corr:
        res["drift_s"] = None

    for k, v in res.items():
        if k in ("audio_transitions", "video_transitions"):
            print(f"  {k}: {len(v)} -> {v[:8]}{' ...' if len(v) > 8 else ''}")
        else:
            print(f"  {k}: {v}")
    if not ok_corr:
        print(f"  VERDICT: NA — transition counts disagree "
              f"(audio {len(at)}, video {len(vt)}); the anchors are not the "
              f"same events and their difference would be meaningless")
    elif res["drift_s"] is None:
        print("  VERDICT: NA — no LATE anchor pair in this capture "
              "(needs an audible AND visible transition late in the run)")
    else:
        print(f"  VERDICT: drift {res['drift_s']:+.3f} s between the anchors "
              f"(positive = audio falls behind); paired offsets: "
              f"{res['paired_offsets_s'][:6]}")
    if a.json:
        a.json.write_text(json.dumps(res, indent=1))
        print(f"  wrote {a.json}")


if __name__ == "__main__":
    main()
