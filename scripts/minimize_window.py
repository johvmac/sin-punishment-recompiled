#!/usr/bin/env python3
"""Minimize (iconify) an X11 window via the ICCCM WM_CHANGE_STATE protocol.

Used to keep automated test runs of the game out of the way of whatever
the user is doing on their real desktop, without needing a true headless
setup (Xvfb + software Vulkan aren't installed on this machine and would
need apt/sudo). Confirmed 2026-08-14: the game keeps rendering and stays
capturable via xwd while minimized -- this is a real "out of your way"
fix, not just a visual trick.

Usage: minimize_window.py <window_id_hex>
"""
import sys as _sys
if "--help" in _sys.argv or "-h" in _sys.argv:
    print(__doc__)
    _sys.exit(0)
import sys
from Xlib import display, X, protocol

win_id = int(sys.argv[1], 16)
d = display.Display()
win = d.create_resource_object('window', win_id)
root = d.screen().root
ICONIC_STATE = 3  # ICCCM WM_STATE: IconicState
ev = protocol.event.ClientMessage(
    window=win,
    client_type=d.intern_atom('WM_CHANGE_STATE'),
    data=(32, [ICONIC_STATE, 0, 0, 0, 0])
)
mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
root.send_event(ev, event_mask=mask)
d.sync()
print(f"minimized window {sys.argv[1]}")
