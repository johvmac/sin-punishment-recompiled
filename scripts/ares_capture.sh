#!/usr/bin/env bash
# Capture a REFERENCE run in ares, for comparison against our build's output.
#
# Usage:
#   scripts/ares_capture.sh [seconds] [label]      # default 300s, watchable
#   scripts/ares_capture.sh --dry-run [seconds]
#   scripts/ares_capture.sh --self-check
#
# WHY THIS EXISTS (A218)
# ----------------------
# A218 asks what the tutorial's background SHOULD look like. Our build draws the
# character and two pylon structures and nothing behind them, and "that is
# missing" currently rests on the user's memory of the original game -- which is
# why A218 is priced at 3 rather than 2. A reference we can step through frame by
# frame turns a recollection into a comparison.
#
# WHY ares AND NOT A VIDEO OFF THE INTERNET
#   * no re-encode at all -- we capture it ourselves, losslessly
#   * frame-steppable and deterministic, so a specific moment can be revisited
#   * the leading downloadable longplay is BizHawk/Mupen64 AND runs an English
#     translation patch, i.e. emulated AND a modified ROM. The best-looking
#     source was disqualified twice over.
# Real-hardware footage remains the tiebreaker if ares and our build disagree in
# a way that looks odd rather than obviously broken.
#
# WHERE THE OUTPUT GOES, AND WHY NOT scene-refs/
# ----------------------------------------------
# `scene-refs/` holds frames from OUR build and feeds classify_recording.py's
# perceptual hash. ares renders at a different resolution with the console's own
# video filtering emulated, so mixing the two would poison the matcher AND
# invite the pixel comparison T88 says is invalid. ares output is authoritative
# for SEQUENCE and IDENTITY -- what should be on screen and in what order --
# and useless for pixel matching. Separate tree, named for what it is.
#
# TWO MECHANICS INHERITED FROM ares_watch.sh, both hard-won:
#   * ABSOLUTE ROM PATH. A relative path does not resolve inside the flatpak
#     sandbox; ares starts, sits at its menu, and the failure looks like
#     something else entirely.
#   * VERIFY THE LIVE PROCESS CMDLINE, not the command you think you ran. A
#     failed relaunch once left an older instance running and the retry silently
#     re-tested it.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

ROM="$ROOT/rom/Tsumi to Batsu - Hoshi no Keishousha (Japan).z64"
ARCHIVE="${SNP_ARCHIVE:-/media/joh/extra/sin-punishment-archive}"
REFDIR="$ARCHIVE/ares-refs"

usage() { sed -n '2,/^set -/p' "$0" | sed '$d; s/^#\( \|$\)//'; }

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
    --self-check)
        fails=0; n=0
        chk() { n=$((n+1)); if [[ "$2" == "1" ]]; then echo "ok    $1"; else echo "FAIL  $1 -- $3"; fails=$((fails+1)); fi; }
        # GREP THE EXECUTABLE REGION ONLY -- i.e. the file MINUS this block.
        #
        # regenerate.sh took "everything after esac", which SILENTLY EXCLUDES
        # every assignment at the top of the file. Two controls here failed on a
        # correct script for exactly that reason: the paths they check are set
        # above the argument parsing, because the self-check itself needs them.
        # Deleting only the self-check range keeps the whole of the rest of the
        # program in scope, which is what "executable region" was always meant
        # to mean.
        BODY=$(sed '/--self-check)/,/^        exit 0 ;;$/d' "$0")
        # AND STRIP COMMENTS FOR THE "must never" CHECKS. This script's header
        # explains at length why output does NOT go to scene-refs/, so a control
        # asserting "scene-refs never appears" fails on a correct script -- the
        # explanation is the match. FOURTH mention-versus-use failure today: the
        # bash guard refused a ledger entry for quoting a refused command, the
        # SO WHAT check flagged the entry that introduced it, and a control once
        # matched its own text and passed. A "must never appear" test has to
        # look at CODE, not at prose about the code.
        CODE=$(printf '%s\n' "$BODY" | grep -v '^[[:space:]]*#')

        # THE ONE THAT MATTERS: output must never land in scene-refs/. Mixing an
        # emulator's frames into our build's reference set breaks the matcher
        # and invites an invalid comparison -- and it is the kind of mistake
        # nobody notices until a hash match is quietly wrong.
        got=0; printf '%s\n' "$CODE" | grep -q 'ares-refs' && \
               ! printf '%s\n' "$CODE" | grep -q 'scene-refs' && got=1
        chk "writes to ares-refs and NEVER to scene-refs (T88)" "$got" \
            "output tree wrong -- would poison the perceptual matcher"

        got=0; printf '%s\n' "$BODY" | grep -q '\$ROOT/rom/' && got=1
        chk "uses an ABSOLUTE rom path (flatpak cannot see relative ones)" "$got" \
            "a relative path fails silently inside the sandbox"

        got=0; printf '%s\n' "$BODY" | grep -q 'pgrep -af' && got=1
        chk "verifies the LIVE process cmdline, not the intended one" "$got" \
            "a stale instance would be re-tested silently"

        got=0; printf '%s\n' "$BODY" | grep -q 'snp_isolate_display' && got=1
        chk "reuses the single isolation source, never its own copy (T59)" "$got" \
            "three divergent copies WAS the bug"

        # Refuses when the archive is absent (T47) -- evidence must outlive the
        # session, and /tmp does not.
        out=$(SNP_ARCHIVE=/proc/nonexistent/x "$0" --dry-run 2>&1); rc=$?
        got=0; [[ $rc -ne 0 || "$out" == *REFUS* ]] && got=1
        chk "REFUSES when the archive is unavailable (T47)" "$got" "rc=$rc"

        got=0; [[ -f "$ROM" ]] && got=1
        chk "the reference rom is present" "$got" "missing: $ROM"

        # THE DISCRIMINATING ONE, added after the first smoke test: the script
        # must FAIL when no video was produced. It previously exited 0 with the
        # recorder dead, which is the worst possible outcome -- a capture run
        # that reports success and captured nothing.
        got=0; printf '%s\n' "$CODE" | grep -q 'no video landed' && \
               printf '%s\n' "$CODE" | grep -q 'exit 1' && got=1
        chk "FAILS when no video was produced" "$got" \
            "would report success on an empty capture"

        got=0; printf '%s\n' "$CODE" | grep -q 'SNP_REC_DIR' && got=1
        chk "passes the recorder a DIRECTORY and a label, not a path" "$got" \
            "an absolute path is concatenated onto the evidence dir and ffmpeg dies"

        echo; echo "$((n-fails))/$n controls pass"
        [[ $fails -eq 0 ]] || exit 1
        exit 0 ;;
esac

DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi
SECS="${1:-300}"
LABEL="${2:-tutorial}"
STAMP="$(date +%Y-%m-%d-%H%M%S)"
DEST="$REFDIR/$STAMP-$LABEL"

if [[ ! -f "$ROM" ]]; then
    echo "[ares] REFUSING: no reference rom at $ROM" >&2
    exit 2
fi

if [[ "$DRY" == "1" ]]; then
    echo "=== DRY RUN — nothing launched ==="
    echo " rom      : $ROM"
    echo " duration : ${SECS}s   label: $LABEL"
    echo " isolation: xephyr — a window you can WATCH, but keystrokes cannot reach it"
    echo " output   : $DEST/  (a separate tree from the build's own refs — see the header)"
    if ! mkdir -p "$REFDIR" 2>/dev/null; then
        echo "[ares] REFUSING: cannot write $REFDIR — the archive is not mounted." >&2
        exit 1
    fi
    exit 0
fi

if ! mkdir -p "$DEST" 2>/dev/null; then
    echo "[ares] REFUSING: cannot write $DEST — the archive is not mounted." >&2
    echo "[ares] Reference footage must outlive the session (T47); /tmp does not." >&2
    exit 1
fi

# ONE copy of the isolation logic, sourced (T59).
export SNP_ISO="${SNP_ISO:-xephyr}"
# shellcheck source=scripts/display_isolate.sh
. "$ROOT/scripts/display_isolate.sh"
trap snp_display_cleanup EXIT INT TERM

snp_isolate_display
# snp_start_recording takes a LABEL and prepends SNP_REC_DIR -- it is NOT a
# path. Passing an absolute path concatenated the two and ffmpeg died on a
# nonsense filename, which the 30s smoke test caught on its first run.
export SNP_REC_DIR="$DEST"
snp_start_recording "ares-$LABEL"

echo "[ares] launching ares on the reference rom — WATCH THE WINDOW."
echo "[ares] the tutorial autoplays; tell me when it is over and I will stop."
for p in $(pgrep -f 'ares --setting' 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
nohup timeout -s KILL "$SECS" flatpak run dev.ares.ares "$ROM" \
    >"$DEST/ares.log" 2>&1 &
APID=$!
sleep 6

# VERIFY THE LIVE CMDLINE (see header) -- not the command we believe we ran.
if ! pgrep -af 'ares' > "$DEST/cmdline.txt" 2>/dev/null || \
   ! grep -q "Tsumi to Batsu" "$DEST/cmdline.txt"; then
    echo "[ares] WARNING: no live ares process is running the reference rom." >&2
    echo "[ares] Check $DEST/ares.log — the window may be sitting at the menu." >&2
fi

{
    echo "captured: $STAMP"
    echo "label: $LABEL"
    echo "source: ares (flatpak dev.ares.ares) — EMULATED, hardware-accurate"
    echo "rom: $(basename "$ROM")"
    echo "rom-sha256-16: $(sha256sum "$ROM" | cut -c1-16)"
    echo "duration-requested: ${SECS}s"
    echo "NOT-FOR: pixel comparison against our build (T88). Authoritative for"
    echo "         SEQUENCE and IDENTITY only."
} > "$DEST/PROVENANCE"

wait "$APID" 2>/dev/null

# A CAPTURE SCRIPT THAT PRODUCES NO CAPTURE MUST NOT EXIT 0.
# The first smoke test lost its recording to a mangled filename and this script
# still reported success -- the whole point of the run was the video, and the
# only sign of failure was one WARNING line above a cheerful "done". That is a
# signal with no reader, which is the defect this project keeps rediscovering.
shopt -s nullglob
vids=("$DEST"/*.mkv "$DEST"/*.mp4)
if [[ ${#vids[@]} -eq 0 ]]; then
    echo "[ares] FAILED: no video landed in $DEST — the recording did not happen." >&2
    echo "[ares] ares itself may have run fine; check $DEST/ares.log and" >&2
    echo "[ares] /tmp/snp_rec_ffmpeg.log for the recorder's own error." >&2
    exit 1
fi
echo "[ares] done — $DEST"
for v in "${vids[@]}"; do echo "[ares]   $(du -h "$v" | cut -f1)  $(basename "$v")"; done
exit 0
