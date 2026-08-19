# shellcheck shell=bash
# Sourceable display isolation for anything that launches the game.
#
# WHY THIS IS ONE FILE
# --------------------
# There used to be three copies of this logic and only one of them existed:
# run_game.sh isolated, gdb_watch.sh and gdb_fault.sh did not, so four debugger
# runs on 2026-08-19 put a live game window on the user's real desktop with the
# keyboard connected to it (T59). Divergence between copies WAS the bug, so
# there is now exactly one copy and the three callers source it.
#
# WHAT EACH MODE ACTUALLY DOES -- these differ in ways that matter:
#
#   xvfb    a real headless X server. NO window appears anywhere. This is the
#           default. Vulkan still renders on the GPU: the display server only
#           supplies the window and the presentation surface, so the swapchain
#           presents into Xvfb's in-RAM framebuffer. lavapipe (lvp_icd.json) is
#           present as a software fallback but should not be needed.
#
#   xephyr  a NESTED X server. It isolates INPUT -- keystrokes reach the game
#           only when its window has focus -- but it DOES show a window on the
#           real display, because that is what a nested server is. This was
#           previously described as keeping windows off the display; that was
#           wrong (T59). Use it when you want to watch without being able to
#           type into the run by accident.
#
#   real    no isolation. The window is on your desktop AND your typing goes
#           into the game -- T23 measured one injected `A` press turning a
#           healthy run into a SIGSEGV.
#
# SELECTION
#   SNP_VISIBLE=1   -> real display
#   SNP_ISO=xephyr  -> nested Xephyr
#   SNP_ISO=real    -> no isolation
#   otherwise       -> Xvfb, falling back to Xephyr, then real, with a warning
#
# The caller must call `snp_display_cleanup` on exit (all callers do so via trap).
#
# RECORDING (2026-08-19, T83)
# Every isolated run is RECORDED to a video by default -- every frame, not a
# sampled still. Scene identity had been read off stills three times and been
# wrong three times (A93, A161, and the inherited "title scene" label on A99):
# the title screen is up for a few seconds, so any sampler can miss it, and a
# sample can never support "X never happened". A recording can.
#
#   SNP_REC=0        disable
#   SNP_REC_DIR=...  output directory (default: today's archive evidence dir)
#   SNP_REC_FPS=N    default 30
#   SNP_REC_MAX=N    hard cap in seconds (default 400) so a runaway cannot fill
#                    the drive -- ffmpeg stops itself even if cleanup never runs
#
# NEVER records in `real` mode. There the display is the USER'S DESKTOP, and
# recording it would capture whatever else they have on screen. That is not a
# tunable; it is why snp_start_recording checks the mode first.

SNP_ISO_PID=""
SNP_ISO_MODE=""
SNP_REC_PID=""
SNP_REC_FILE=""
SNP_ISO_GEOM_WH=""

# Start recording the ISOLATED display. Returns 0 always: a missing recorder
# must never fail a run, but it must never be silent either -- an absent
# artifact that nobody was told about is indistinguishable from one nobody
# looked at.
snp_start_recording() {
    local label="${1:-run}"
    [ "${SNP_REC:-1}" = "0" ] && return 0
    # THE CONTROL THAT MATTERS. `real` means the user's own desktop.
    if [ "$SNP_ISO_MODE" = "real" ]; then
        echo "[$label] NOT recording: mode is 'real' and that display is the user's desktop" >&2
        return 0
    fi
    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo "[$label] WARNING: ffmpeg absent -- this run is NOT recorded" >&2
        return 0
    fi
    local dir="${SNP_REC_DIR:-/media/joh/extra/sin-punishment-archive/evidence/$(date +%Y-%m-%d)}"
    if ! mkdir -p "$dir" 2>/dev/null; then
        # T47: evidence goes to the archive drive, never /tmp. If the drive is
        # not there, say so rather than quietly writing somewhere that will not
        # survive the session.
        echo "[$label] WARNING: cannot write $dir -- this run is NOT recorded (T47)" >&2
        return 0
    fi
    SNP_REC_FILE="$dir/${label}-$(date +%H%M%S).mp4"
    ffmpeg -nostdin -loglevel error -y \
        -f x11grab -framerate "${SNP_REC_FPS:-30}" -video_size "${SNP_ISO_GEOM_WH:-1280x720}" \
        -i "$DISPLAY" -t "${SNP_REC_MAX:-400}" \
        -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p \
        "$SNP_REC_FILE" > /tmp/snp_rec_ffmpeg.log 2>&1 &
    SNP_REC_PID=$!
    sleep 0.5
    if ! kill -0 "$SNP_REC_PID" 2>/dev/null; then
        echo "[$label] WARNING: recorder died immediately; see /tmp/snp_rec_ffmpeg.log" >&2
        SNP_REC_PID=""; SNP_REC_FILE=""
        return 0
    fi
    echo "[$label] recording -> $SNP_REC_FILE" >&2
    return 0
}

snp_display_cleanup() {
    # STOP THE RECORDER FIRST, and with SIGINT not SIGKILL: ffmpeg needs to
    # write the moov atom or the file is unplayable. Killing the X server out
    # from under a live grab produces a truncated file that looks like evidence
    # and is not.
    if [ -n "${SNP_REC_PID:-}" ]; then
        kill -INT "$SNP_REC_PID" 2>/dev/null
        local i=0
        while [ $i -lt 40 ] && kill -0 "$SNP_REC_PID" 2>/dev/null; do
            sleep 0.1; i=$((i + 1))
        done
        kill -9 "$SNP_REC_PID" 2>/dev/null
        SNP_REC_PID=""
        if [ -n "${SNP_REC_FILE:-}" ] && [ -s "$SNP_REC_FILE" ]; then
            echo "[rec] $SNP_REC_FILE ($(du -h "$SNP_REC_FILE" | cut -f1))" >&2
        elif [ -n "${SNP_REC_FILE:-}" ]; then
            echo "[rec] WARNING: $SNP_REC_FILE is empty" >&2
        fi
    fi
    [ -n "${SNP_ISO_PID:-}" ] && kill "$SNP_ISO_PID" 2>/dev/null
    SNP_ISO_PID=""
    return 0
}

# Find a display number nothing is holding. A stale server on :7 used to make
# the isolation silently fail back to the real display.
_snp_free_display() {
    local n
    for n in $(seq "${SNP_ISO_DISPLAY_MIN:-7}" 20); do
        if [ ! -e "/tmp/.X11-unix/X${n}" ] && [ ! -e "/tmp/.X${n}-lock" ]; then
            echo ":$n"; return 0
        fi
    done
    echo ":7"
}

snp_isolate_display() {
    local want="${SNP_VISIBLE:-0}" mode="${SNP_ISO:-}" disp
    local label="${1:-run}"
    # Resolve the geometry ONCE. `${SNP_ISO_GEOM%x24}` on an UNSET variable
    # expands to empty, which made `Xephyr :7 -screen  -nolisten tcp` malformed;
    # Xephyr then failed, the helper fell through to "no isolation available",
    # and the run went to the real display -- silently, and with the window and
    # keyboard exposure this file exists to prevent. Caught by the A/B, whose
    # Xephyr arm reported the real display in its own banner.
    local geom="${SNP_ISO_GEOM:-1280x720x24}"
    SNP_ISO_GEOM_WH="${geom%x24}"

    if [ "$want" = "1" ] || [ "$mode" = "real" ]; then
        SNP_ISO_MODE="real"
        echo "[$label] on the REAL display -- your keystrokes reach the game (T23)" >&2
        # Called DELIBERATELY on the path that must not record. The refusal then
        # comes from the guard inside snp_start_recording rather than from the
        # call merely being absent -- so the protection is exercised on every
        # real-mode run, and the self-test can prove it fires. An untested
        # safeguard on a privacy boundary is not a safeguard.
        snp_start_recording "$label"
        return 0
    fi

    disp="${SNP_ISO_DISPLAY:-$(_snp_free_display)}"

    if [ "$mode" != "xephyr" ] && command -v Xvfb >/dev/null 2>&1; then
        Xvfb "$disp" -screen 0 "$geom" -nolisten tcp > /dev/null 2>&1 &
        SNP_ISO_PID=$!
        sleep 2
        if kill -0 "$SNP_ISO_PID" 2>/dev/null; then
            export DISPLAY="$disp"
            SNP_ISO_MODE="xvfb"
            echo "[$label] HEADLESS on $disp (Xvfb pid $SNP_ISO_PID) -- no window, no input. SNP_ISO=xephyr to watch it" >&2
            snp_start_recording "$label"
            return 0
        fi
        SNP_ISO_PID=""
        echo "[$label] WARNING: Xvfb failed to start; trying Xephyr" >&2
    fi

    if command -v Xephyr >/dev/null 2>&1; then
        Xephyr "$disp" -screen "${geom%x24}" -nolisten tcp > /dev/null 2>&1 &
        SNP_ISO_PID=$!
        sleep 2
        if kill -0 "$SNP_ISO_PID" 2>/dev/null; then
            export DISPLAY="$disp"
            SNP_ISO_MODE="xephyr"
            echo "[$label] nested on $disp (Xephyr pid $SNP_ISO_PID) -- input isolated, but a WINDOW IS SHOWN" >&2
            snp_start_recording "$label"
            return 0
        fi
        SNP_ISO_PID=""
    fi

    SNP_ISO_MODE="real"
    echo "[$label] WARNING: no isolation available; running on the REAL display -- keystrokes reach the game (T23)" >&2
    return 0
}
