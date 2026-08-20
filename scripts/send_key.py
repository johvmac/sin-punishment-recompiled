#!/usr/bin/env python3
"""Send a single keypress to an isolated X display, via XTEST.

WHY THIS EXISTS (2026-08-21)
----------------------------
RT64's debugger inspector is opened with F1 and is the best instrument we have
for the render faults -- but it is an ImGui panel, so using it needed the user
at a keyboard. The first attempt cost a run and told us nothing: the F-keys
never reached the game (their keyboard needs Fn), and the run SIGSEGVed anyway.

Two runs of A/B then showed developer_mode and Xephyr are BOTH innocent -- 60s
CLEAN each, untouched -- so the crash needed the keypress. **T23 already records
one injected `A` press turning a healthy run into a SIGSEGV.** That is a real
property of this build and it is now in the way of a scheduled task.

So the keypress has to become something I can do, repeatably, with the outcome
recorded -- rather than something the user retries blind.

WHY THIS IS NOT A VIOLATION OF INPUT ISOLATION
----------------------------------------------
The isolation rule (T59/T23) exists so that stray input never contaminates a
run WITHOUT ANYONE KNOWING. This is the opposite: a deliberate, logged, single
keystroke at a chosen moment, sent to a display that only the game is on. Any
run using it is contaminated BY DESIGN and must say so in its own write-up --
it is a tool-verification run, never an evidence run.

    scripts/send_key.py --display :7 --key F1
    scripts/send_key.py --display :7 --key F1 --dry-run
    scripts/send_key.py --self-check
"""
import argparse
import sys
import time


def send(display_name, keyname, dry_run=False):
    from Xlib import display as xdisplay, X
    from Xlib.ext import xtest
    from Xlib import XK

    keysym = XK.string_to_keysym(keyname)
    if keysym == 0:
        print(f"[sendkey] unknown key name: {keyname}", file=sys.stderr)
        return 2

    d = xdisplay.Display(display_name)
    code = d.keysym_to_keycode(keysym)
    if code == 0:
        print(f"[sendkey] {keyname} has no keycode on {display_name}", file=sys.stderr)
        return 2

    # Name the focused window, so a keystroke that went nowhere is visible in
    # the log rather than looking like a key the game ignored.
    try:
        focus = d.get_input_focus().focus
        wname = focus.get_wm_name() if hasattr(focus, "get_wm_name") else None
    except Exception:
        wname = None
    print(f"[sendkey] display={display_name} key={keyname} keysym=0x{keysym:X} "
          f"keycode={code} focus={wname!r}")

    if dry_run:
        print("[sendkey] --dry-run: not sending")
        return 0

    xtest.fake_input(d, X.KeyPress, code)
    d.sync()
    time.sleep(0.05)
    xtest.fake_input(d, X.KeyRelease, code)
    d.sync()
    print("[sendkey] sent")
    return 0


def self_check():
    """Controls. The DISCRIMINATING one is that a bad key name is REFUSED:
    a tool that silently sent nothing would be indistinguishable from a game
    that ignored the key, which is exactly the question it is used to answer.
    """
    checks = []

    def chk(name, ok, detail):
        checks.append((name, ok, detail))

    try:
        from Xlib import XK
        chk("python-xlib imports", True, "ok")
        chk("F1 resolves to a keysym", XK.string_to_keysym("F1") != 0,
            f"0x{XK.string_to_keysym('F1'):X}")
        # DISCRIMINATING: an unknown name must not resolve.
        chk("a nonsense key name does NOT resolve (else 'sent' means nothing)",
            XK.string_to_keysym("NotAKey") == 0,
            "string_to_keysym must return 0")
    except Exception as e:  # pragma: no cover
        chk("python-xlib imports", False, str(e))

    # DISCRIMINATING: a display that does not exist must fail, not pretend.
    rc = 1
    try:
        rc = send(":99", "F1", dry_run=True)
    except Exception:
        rc = 2
    chk("a nonexistent display FAILS rather than reporting success", rc != 0,
        f"rc={rc}")

    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:62} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--display", default=":7")
    p.add_argument("--key", default="F1")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--self-check", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    a = p.parse_args()
    if a.help:
        print(__doc__)
        return 0
    if a.self_check:
        return self_check()
    return send(a.display, a.key, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
