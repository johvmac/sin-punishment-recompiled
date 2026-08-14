#!/usr/bin/env python3
"""Click into a window (for WM click-to-focus), then send real XTEST key
press/release events so the target app sees genuine input."""
import sys
import time
from Xlib import X, XK, display
from Xlib.ext import xtest

def click_window(d, win_id_hex):
    win_id = int(win_id_hex, 16)
    win = d.create_resource_object('window', win_id)
    geom = win.get_geometry()
    x, y = geom.width // 2, geom.height // 2
    # Warp pointer into the window (relative to root) and click.
    root = d.screen().root
    coords = win.translate_coords(root, 0, 0)
    abs_x = -coords.x + x
    abs_y = -coords.y + y
    root.warp_pointer(abs_x, abs_y)
    d.sync()
    xtest.fake_input(d, X.ButtonPress, 1)
    d.sync()
    time.sleep(0.05)
    xtest.fake_input(d, X.ButtonRelease, 1)
    d.sync()
    print(f"clicked window {win_id_hex} at ({abs_x},{abs_y})")

def send_key(d, keysym_name, hold=0.1):
    keysym = XK.string_to_keysym(keysym_name)
    keycode = d.keysym_to_keycode(keysym)
    if keycode == 0:
        print(f"Could not map keysym {keysym_name}")
        return
    xtest.fake_input(d, X.KeyPress, keycode)
    d.sync()
    time.sleep(hold)
    xtest.fake_input(d, X.KeyRelease, keycode)
    d.sync()
    print(f"sent {keysym_name} (keycode {keycode})")

if __name__ == '__main__':
    win_id_hex = sys.argv[1]
    keys = sys.argv[2:]
    d = display.Display()
    click_window(d, win_id_hex)
    time.sleep(0.3)
    for name in keys:
        send_key(d, name)
        time.sleep(0.3)
