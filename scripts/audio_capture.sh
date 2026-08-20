#!/usr/bin/env bash
# Capture ONLY the game's audio -- never the rest of the machine's.
#
# WHY THIS EXISTS
# ---------------
# T101 found that every run recording this project has ever made is SILENT BY
# CONSTRUCTION: display_isolate.sh's ffmpeg invocation has no audio input. A97's
# status is "audio silence only" and there has never been one piece of audio
# evidence for it -- every claim in it comes from reading source. I cannot
# perceive audio at all, so without this the only instrument is the user's ears
# and their memory of what they heard.
#
# WHY NOT JUST RECORD THE DEFAULT SINK
# ------------------------------------
# Because that records whatever else the machine is playing -- music, calls,
# notifications. That is the same class of problem as filming the user's desktop,
# which display_isolate.sh has guarded against since T83. **A capture that can
# pick up the user's audio is not acceptable even once.** --self-check asserts
# the isolation behaviourally, not by inspection.
#
# HOW IT WORKS, AND WHY THIS SHAPE
# --------------------------------
# `pw-record --target <stream-node>` was tried FIRST and CAPTURED SILENCE -- both
# against the app's stream node and against a null sink's monitor. Measured, not
# assumed (T60/T62/T63: three tools shipped confident wrong answers). The working
# shape is the classic PulseAudio one:
#
#   1. load a dedicated null sink                 (nothing else is routed to it)
#   2. move ONLY the game's sink-input into it    (so its monitor is game-only)
#   3. loopback that monitor to the real output   (so the user STILL HEARS IT)
#   4. `parec` the null sink's monitor
#
# Step 2 is what makes it private: the monitor can only contain what was moved.
#
# IF THE GAME NEVER OPENS AN AUDIO STREAM, THAT IS ITSELF THE FINDING. It means
# the silence is "nothing is being produced", not "the samples are wrong", and
# those call for completely different work on A97. Reported explicitly rather
# than as an empty file.
#
# Usage:
#   scripts/audio_capture.sh prepare <out.wav>    # BEFORE launch; prints the
#                                                 # sink name for PULSE_SINK
#   scripts/audio_capture.sh finish               # stop, unload, compress to FLAC
#   scripts/audio_capture.sh attach <pid> <out.wav> [secs] [wait_s]   # ad-hoc
#   scripts/audio_capture.sh --dry-run
#   scripts/audio_capture.sh --self-check     # two-tone isolation control
#   scripts/audio_capture.sh --cleanup        # force-remove our modules
set -uo pipefail

SINK="snp_capture"
LOADED_SINK=""; LOADED_LOOP=""; PAREC_PID=""

_unload_all() {
    [[ -n "$LOADED_LOOP" ]] && pactl unload-module "$LOADED_LOOP" 2>/dev/null
    [[ -n "$LOADED_SINK" ]] && pactl unload-module "$LOADED_SINK" 2>/dev/null
    LOADED_LOOP=""; LOADED_SINK=""
}
# Leaving a null sink loaded silently breaks the user's audio routing, so the
# trap covers every exit path, not just the happy one.
_cleanup() {
    [[ -n "$PAREC_PID" ]] && kill -INT "$PAREC_PID" 2>/dev/null && wait "$PAREC_PID" 2>/dev/null
    _unload_all
}
trap _cleanup EXIT INT TERM

usage() { sed -n '/^# Usage:/,/^set -/p' "$0" | sed 's/^# \{0,1\}//;$d'; }

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    --cleanup)
        # Any stray module from a killed run. Named sink only -- never a blanket
        # unload, which would tear down the user's own routing.
        for m in $(pactl list modules short | awk -v s="$SINK" '$0 ~ s {print $1}'); do
            pactl unload-module "$m" 2>/dev/null && echo "unloaded module $m"
        done
        echo "cleanup done"; exit 0 ;;
    --dry-run)
        echo "=== DRY RUN — nothing loaded, nothing recorded ==="
        echo "would: load null sink '$SINK'"
        echo "       move ONLY the game's sink-input into it"
        echo "       loopback its monitor -> $(pactl info 2>/dev/null | awk -F': ' '/Default Sink/{print $2}')"
        echo "       parec -d ${SINK}.monitor  (game audio ONLY)"
        echo "note : if the game never opens a stream, that is REPORTED as the finding"
        exit 0 ;;
esac

if [[ "${1:-}" == "--self-check" ]]; then
    # THE CONTROL IS BEHAVIOURAL AND DISCRIMINATES IN BOTH DIRECTIONS: one tone
    # is moved into the capture sink and one is deliberately left out. A capture
    # that grabbed the whole machine would pass a "did we get audio" test and
    # fail this one. Both tones play into null sinks, so the user hears nothing.
    command -v parec >/dev/null || { echo "FAIL  parec absent"; exit 1; }
    TD=$(mktemp -d); trap '_cleanup; rm -rf "$TD"' EXIT
    ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=440:duration=6"  "$TD/a.wav"
    ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=1800:duration=6" "$TD/b.wav"
    LOADED_SINK=$(pactl load-module module-null-sink sink_name=$SINK)
    OTHER=$(pactl load-module module-null-sink sink_name=snp_selftest_other)
    paplay --device=snp_selftest_other --property=application.name=SNPCHK_A "$TD/a.wav" & PA=$!
    paplay --device=snp_selftest_other --property=application.name=SNPCHK_B "$TD/b.wav" & PB=$!
    sleep 1
    IDX=$(pactl list sink-inputs | awk '/Sink Input #/{i=$NF} /application.name = "SNPCHK_A"/{print i; exit}' | tr -d '#')
    [[ -n "$IDX" ]] && pactl move-sink-input "$IDX" $SINK
    timeout 4 parec -d ${SINK}.monitor --file-format=wav "$TD/cap.wav" 2>/dev/null
    wait $PA $PB 2>/dev/null; pactl unload-module "$OTHER" 2>/dev/null; _unload_all
    python3 - "$TD/cap.wav" <<'EOF'
import sys, wave, numpy as np
w = wave.open(sys.argv[1]); n = w.getnframes(); sr = w.getframerate()
a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(float)
if w.getnchannels() > 1: a = a[::w.getnchannels()]
checks = []
peak = float(np.abs(a).max()) if n else 0.0
if peak > 0:
    sp = np.abs(np.fft.rfft(a * np.hanning(len(a)))); fr = np.fft.rfftfreq(len(a), 1/sr)
    e = lambda f0: float(sp[(fr > f0-40) & (fr < f0+40)].max() / (sp.max() + 1e-9))
    ina, outb = e(440), e(1800)
else:
    ina = outb = 0.0
checks.append(("captures the stream MOVED IN (440Hz)", ina > 0.5, f"relative energy {ina:.3f}"))
checks.append(("captures NOTHING from the stream left OUT (1800Hz) — the privacy property",
               outb < 0.05, f"relative energy {outb:.4f}"))
checks.append(("capture is not empty", peak > 0, f"peak {peak:.0f}"))
bad = 0
for nme, ok, d in checks:
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {nme:62} — {d}")
sys.exit(bad)
EOF
    BAD=$?
    NC=3
    # 4. THE PIPELINE MUST FINALIZE: one lossless pass, master removed. Same
    #    shape as the video pipeline's finalize control. Without this a run
    #    leaves a 35 MB WAV per 3 minutes on the archive drive -- the first
    #    observed run did exactly that.
    TD2=$(mktemp -d)
    ffmpeg -loglevel error -y -f lavfi -i "sine=frequency=660:duration=2" "$TD2/x.wav" 2>/dev/null
    SN=$("$0" prepare "$TD2/cap.wav"); PULSE_SINK="$SN" paplay "$TD2/x.wav" 2>/dev/null
    "$0" finish >/dev/null 2>&1
    if [[ -f "$TD2/cap.flac" && ! -f "$TD2/cap.wav" ]]; then
        echo "ok    pipeline finalizes: FLAC written, WAV master removed        — $(stat -c%s "$TD2/cap.flac") bytes"
    else
        echo "FAIL  pipeline finalizes: FLAC written, WAV master removed        — flac=$([[ -f "$TD2/cap.flac" ]] && echo yes || echo NO), leftover wav=$([[ -f "$TD2/cap.wav" ]] && echo YES || echo no)"
        BAD=$((BAD+1))
    fi
    NC=$((NC+1))
    rm -rf "$TD2"
    echo; echo "$((NC-BAD))/$NC controls pass"
    [[ $BAD -eq 0 ]] || exit 1
    exit 0
fi

STATEF="${TMPDIR:-/tmp}/.snp_audio_capture_state"

# PRELAUNCH ROUTING (T104) -- set the sink up BEFORE the game starts and let it
# connect there itself via PULSE_SINK, instead of chasing its stream afterwards.
#
# WHY: the first observed run (2026-08-20) captured 198 s of PURE SILENCE while
# the USER HEARD A LOUD BLIP "as the program opened". The capture began 6 s into
# the run, because `attach` has to POLL for a sink-input that does not exist
# until the game opens audio. **The one event worth hearing happened inside the
# gap.** A capture that reliably misses the interesting moment is worse than
# none: it produces a confident silent artefact.
#
# PULSE_SINK routes ONE PROCESS and touches nothing else -- measured, not
# assumed: a paplay launched with it landed in the target sink with no move.
# Setting the SYSTEM default sink would have caught the game too, but would also
# have captured every other app that started during the run, which is the exact
# privacy failure this tool exists to avoid.
if [[ "${1:-}" == "prepare" ]]; then
    OUT="${2:?need an output .wav}"
    REALSINK=$(pactl info | awk -F': ' '/Default Sink/{print $2}')
    LOADED_SINK=$(pactl load-module module-null-sink sink_name=$SINK) || exit 1
    LOADED_LOOP=$(pactl load-module module-loopback source=${SINK}.monitor sink="$REALSINK" latency_msec=50)
    setsid parec -d ${SINK}.monitor --file-format=wav "$OUT" >/dev/null 2>&1 &
    printf '%s\n%s\n%s\n%s\n' "$LOADED_SINK" "$LOADED_LOOP" "$!" "$OUT" > "$STATEF"
    trap - EXIT INT TERM          # hand ownership to `finish`
    echo "$SINK"                  # caller exports PULSE_SINK=<this>
    exit 0
fi

if [[ "${1:-}" == "finish" ]]; then
    [[ -f "$STATEF" ]] || { echo "[audio] no capture in progress" >&2; exit 1; }
    { read -r LOADED_SINK; read -r LOADED_LOOP; read -r PP; read -r OUT; } < "$STATEF"
    kill -INT "$PP" 2>/dev/null; sleep 0.5; kill -9 "$PP" 2>/dev/null
    pactl unload-module "$LOADED_LOOP" 2>/dev/null
    pactl unload-module "$LOADED_SINK" 2>/dev/null
    rm -f "$STATEF"; LOADED_SINK=""; LOADED_LOOP=""
    # ONE compression pass, LOSSLESS, mirroring the video pipeline's shape --
    # capture raw, compress once, remove the master.
    #
    # BUT LOSSLESS WHERE VIDEO IS LOSSY, AND THAT IS THE POINT: video is
    # compressed lossily because we look at SCENES, which survive it. Audio
    # evidence here is about SILENCE and possibly faint or corrupted output --
    # exactly the signal a lossy codec discards first. Opus at a low bitrate
    # could erase the very blip we are hunting and leave a confident, clean,
    # WRONG artefact. FLAC costs nothing: 34.9 MB -> 36.6 KB on the silent run.
    if [[ -s "$OUT" ]] && command -v ffmpeg >/dev/null; then
        if ffmpeg -nostdin -loglevel error -y -i "$OUT" -c:a flac -compression_level 8 \
                  "${OUT%.wav}.flac" 2>/dev/null; then
            W=$(stat -c%s "$OUT"); F=$(stat -c%s "${OUT%.wav}.flac")
            rm -f "$OUT"
            echo "[audio] ${OUT##*/} -> ${OUT##*/}.flac: $((F/1024)) KB from $((W/1024)) KB, LOSSLESS"
        fi
    fi
    exit 0
fi

[[ "${1:-}" == "attach" ]] || { echo "[audio] unknown argument: ${1:-<none>}" >&2
    echo "[audio] REFUSING rather than guessing. --help for usage." >&2; exit 2; }

PID="${2:?need the game pid}"; OUT="${3:?need an output .wav}"; SECS="${4:-200}"; WAIT="${5:-30}"

# Poll for the game's OWN sink-input. It does not exist until the game opens
# audio, so the recorder cannot simply start with the run.
IDX=""
for _ in $(seq 1 "$WAIT"); do
    IDX=$(pactl list sink-inputs 2>/dev/null | awk -v p="$PID" '
        /Sink Input #/{i=$NF} /application.process.id = /{gsub(/"/,"",$3); if ($3==p) {print i; exit}}' | tr -d '#')
    [[ -n "$IDX" ]] && break
    sleep 1
done

if [[ -z "$IDX" ]]; then
    echo "[audio] NO AUDIO STREAM: pid $PID opened no sink-input in ${WAIT}s."
    echo "[audio] **That is a FINDING, not a failed capture** — it means nothing is"
    echo "[audio] being produced at all, which is a different defect from wrong"
    echo "[audio] samples, and points A97 at a different place."
    exit 3
fi

REALSINK=$(pactl info | awk -F': ' '/Default Sink/{print $2}')
LOADED_SINK=$(pactl load-module module-null-sink sink_name=$SINK) || exit 1
pactl move-sink-input "$IDX" $SINK || exit 1
# Loopback so the run is still AUDIBLE -- an observed run the user cannot hear
# would defeat the entire point of capturing audio in the first place.
LOADED_LOOP=$(pactl load-module module-loopback source=${SINK}.monitor sink="$REALSINK" latency_msec=50)
echo "[audio] capturing sink-input $IDX (pid $PID) -> $OUT ; you will still hear it"
timeout "$SECS" parec -d ${SINK}.monitor --file-format=wav "$OUT" 2>/dev/null &
PAREC_PID=$!
wait $PAREC_PID 2>/dev/null
PAREC_PID=""
_unload_all
echo "[audio] wrote $OUT ($(du -h "$OUT" 2>/dev/null | cut -f1))"
exit 0
