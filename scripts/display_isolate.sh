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
# The caller must call `snp_display_cleanup` on exit (all three do so via trap).

SNP_ISO_PID=""
SNP_ISO_MODE=""

snp_display_cleanup() {
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

    if [ "$want" = "1" ] || [ "$mode" = "real" ]; then
        SNP_ISO_MODE="real"
        echo "[$label] on the REAL display -- your keystrokes reach the game (T23)" >&2
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
            return 0
        fi
        SNP_ISO_PID=""
    fi

    SNP_ISO_MODE="real"
    echo "[$label] WARNING: no isolation available; running on the REAL display -- keystrokes reach the game (T23)" >&2
    return 0
}
