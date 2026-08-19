#!/usr/bin/env python3
"""Click a specific point inside an X11 window via XTEST.

Reliable against top-level SDL/game-render windows (confirmed against
BanjoRecomp, ares' main window, and our own build). NOT reliable against
native Qt dropdown/popup menus (e.g. ares' Settings/Nintendo 64 menus) --
a correctly-computed click there can land as a hover on the wrong item
without ever opening it. For menu-driven UI interactions, ask the user to
drive it directly instead of iterating on coordinates.

Usage: xclick.py <window_id_hex> <local_x> <local_y>
"""
import sys as _sys
if "--help" in _sys.argv or "-h" in _sys.argv:
    print(__doc__)
    _sys.exit(0)
import sys
import time
from Xlib import X, display
from Xlib.ext import xtest

win_id = int(sys.argv[1], 16)
lx, ly = int(sys.argv[2]), int(sys.argv[3])

d = display.Display()
win = d.create_resource_object('window', win_id)
root = d.screen().root
coords = win.translate_coords(root, 0, 0)
abs_x = -coords.x + lx
abs_y = -coords.y + ly
root.warp_pointer(abs_x, abs_y)
d.sync()
xtest.fake_input(d, X.ButtonPress, 1)
d.sync()
time.sleep(0.05)
xtest.fake_input(d, X.ButtonRelease, 1)
d.sync()
print(f"clicked at local ({lx},{ly}) -> abs ({abs_x},{abs_y})")
