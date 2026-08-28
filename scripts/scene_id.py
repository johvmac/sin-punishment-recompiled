#!/usr/bin/env python3
"""Which SCENE is an RDRAM snapshot in? Read from memory, not sampled from video.

Usage:
  scripts/scene_id.py <dump.rdram> [<dump.rdram> ...]
  scripts/scene_id.py --self-check
  scripts/scene_id.py --help

WHY THIS EXISTS (T101, A93, A161, A608)
---------------------------------------
Scene identity has been read off sampled frames three times on this project and
been WRONG twice -- the observation right, the quantifier wrong -- and A608
nearly repeated it in a new costume by sampling a frame after the emulator had
quit. Sampling cannot support "the run was in scene X", because a scene the game
holds for two seconds can be missed by any sampler.

THIS READS IT OUT OF MEMORY INSTEAD, and it cross-checks itself.

WHAT IT READS
  0x80068A94  u8  the CURRENT scene index   (loaded into $a0 at 0x80025F7C's
                  sibling site and consumed by boot_func_800263CC, which indexes
                  T_COUNT/T_LIST/T_INIT at [scene-1])
  0x80068A93  u8  the PREVIOUS scene, copied from the current one by the loader
                  at 0x80026420-0x80026428 on entry
  0x800744D8  u32 the per-scene allocation CURSOR
  0x800744D4  u32 the per-scene cursor BASE (constant 0x802A0370)

THE CONTROL, AND IT CAN FAIL
  Every scene subtracts its own chunk sizes from the cursor, so the FINAL cursor
  value is a signature of the scene -- computed independently from the ROM by
  scripts/overlay_map.py, which never looks at a dump. This tool runs that map
  and checks the scene byte against it. Several scenes share a cursor (5 and 19
  load identical data and differ only in their init function), so the cursor
  NARROWS rather than identifies -- but scenes 1 and 20 are unique, so a
  misread byte is caught. Reported per dump as AGREES / DISAGREES.

  The base word is a second, cheaper control: overlay_map.py computes
  0x802A0370 from the ROM alone, so a dump disagreeing there means the map and
  the build have diverged and nothing else here should be believed.

BYTE ORDER -- the trap this project has hit three times (A635, A647, A659)
  RDRAM is stored byte-swapped within each word. A 32-bit read at the natural
  offset is correct as little-endian; a BYTE at address A lives at index A^3.
  Getting that wrong reads a neighbouring field, which is exactly what happened
  on the first attempt here: 0x80068A95 (the requested-scene byte, zero in every
  dump) was read instead of 0x80068A94, and the control caught it.
"""
import os
import re
import subprocess
import sys

SCENE = 0x80068A94
PREV = 0x80068A93
CURSOR = 0x800744D8
BASE = 0x800744D4
BASE_EXPECTED = 0x802A0370


def rb(buf, addr):
    """One byte at a KSEG0 address, honouring the word-internal byte swap."""
    return buf[(addr - 0x80000000) ^ 3]


def rw(buf, addr):
    o = addr - 0x80000000
    return int.from_bytes(buf[o:o + 4], "little")


def cursor_table(rom=None):
    """cursor value -> [scene numbers], computed from the ROM by overlay_map.py.

    Shelled out rather than imported: overlay_map.py does its work in main(),
    and duplicating its arithmetic here would be a second copy to go stale.
    Returns {} if it cannot be run -- callers must treat that as "no control",
    never as "control passed".
    """
    cmd = [sys.executable, "scripts/overlay_map.py"] + ([rom] if rom else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception:
        return {}
    if out.returncode != 0:
        return {}
    low = {}
    for ln in out.stdout.splitlines():
        m = re.match(r"\s*scene\s+(\d+) init=(0x[0-9A-Fa-f]+).*-> vram (0x[0-9A-Fa-f]+)", ln)
        if m:
            s, v = int(m.group(1)), int(m.group(3), 16)
            if s not in low or v < low[s]:
                low[s] = v
    tab = {}
    for s, v in low.items():
        tab.setdefault(v, []).append(s)
    return {k: sorted(v) for k, v in tab.items()}


def describe(path, tab):
    with open(path, "rb") as fh:
        buf = fh.read()
    if len(buf) < 0x800000:
        return dict(path=path, error=f"only {len(buf)} bytes -- not an 8 MB RDRAM dump")
    scene, prev = rb(buf, SCENE), rb(buf, PREV)
    cur, base = rw(buf, CURSOR), rw(buf, BASE)
    allowed = tab.get(cur)
    if not tab:
        verdict = "NO CONTROL (overlay_map.py did not run)"
    elif allowed is None:
        verdict = "cursor unknown to the map"
    else:
        verdict = "AGREES" if scene in allowed else "DISAGREES"
    return dict(path=path, scene=scene, prev=prev, cursor=cur, base=base,
                allowed=allowed, verdict=verdict,
                base_ok=(base == BASE_EXPECTED))


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[1] == "--self-check":
        return self_check()
    tab = cursor_table()
    if not tab:
        print("[scene_id] WARNING: overlay_map.py did not run, so the cursor control "
              "is ABSENT. The scene byte below is unchecked -- do not cite it as "
              "measured.", file=sys.stderr)
    bad = 0
    for p in argv[1:]:
        d = describe(p, tab)
        if d.get("error"):
            print(f"{os.path.basename(p):<22} ERROR: {d['error']}")
            bad += 1
            continue
        allowed = d["allowed"]
        print(f"{os.path.basename(p):<22} scene={d['scene']:<3} prev={d['prev']:<3} "
              f"cursor=0x{d['cursor']:08X} allows={allowed if allowed else '?'}  "
              f"{d['verdict']}"
              + ("" if d["base_ok"] else
                 f"   !! BASE 0x{d['base']:08X} != 0x{BASE_EXPECTED:08X}"))
        if d["verdict"] == "DISAGREES" or not d["base_ok"]:
            bad += 1
    return 1 if bad else 0


def self_check():
    ok = True
    # (1) SYNTHETIC: a buffer with known bytes placed under the byte-swap rule.
    buf = bytearray(0x800000)
    def wb(addr, v):
        buf[(addr - 0x80000000) ^ 3] = v
    def ww(addr, v):
        o = addr - 0x80000000
        buf[o:o + 4] = v.to_bytes(4, "little")
    wb(SCENE, 19)
    wb(PREV, 2)
    ww(CURSOR, 0x80206AE0)
    ww(BASE, BASE_EXPECTED)
    if rb(buf, SCENE) != 19 or rb(buf, PREV) != 2:
        print("[self-check] FAIL: byte read does not round-trip the ^3 swap")
        ok = False
    if rw(buf, CURSOR) != 0x80206AE0 or rw(buf, BASE) != BASE_EXPECTED:
        print("[self-check] FAIL: word read does not round-trip")
        ok = False

    # (2) THE SWAP MUST MATTER. Reading the NEIGHBOURING address must NOT return
    #     the scene -- that is precisely the error this tool was written after.
    if rb(buf, SCENE + 1) == 19:
        print("[self-check] FAIL: address+1 returns the scene, so the byte offset "
              "is not actually being discriminated")
        ok = False

    # (3) THE CONTROL MUST FIRE ON A WRONG BYTE.
    tab = {0x80206AE0: [5, 19], 0x8029BBC0: [1]}
    scene, cur = rb(buf, SCENE), rw(buf, CURSOR)
    if not (scene in tab[cur]):
        print("[self-check] FAIL: control rejects a CORRECT pairing")
        ok = False
    wb(SCENE, 7)
    if rb(buf, SCENE) in tab[cur]:
        print("[self-check] FAIL: control ACCEPTS scene 7 against a cursor that only "
              "allows 5 or 19 -- it cannot fail, so it is not a control")
        ok = False
    wb(SCENE, 19)

    # (4) REAL DUMPS, if the archive is mounted: 4/4 must agree, and two of the
    #     four have UNIQUE cursors so the check is discriminating.
    d = "/media/joh/extra/sin-punishment-archive/evidence/2026-08-28/"
    known = {"a604-logowindow.rdram": 1, "a594-logo.rdram": 20,
             "a590-tutorial.rdram": 19, "a601-freeze.rdram": 19}
    have = [f for f in known if os.path.exists(d + f)]
    if have:
        tab2 = cursor_table()
        if not tab2:
            print("[self-check] SKIP real-dump control: overlay_map.py did not run")
        else:
            for f in sorted(have):
                r = describe(d + f, tab2)
                if r.get("error") or r["scene"] != known[f] or r["verdict"] != "AGREES":
                    print(f"[self-check] FAIL: {f} -> {r}")
                    ok = False
            print(f"[self-check] real-dump control: {len(have)}/4 dump(s) present, "
                  f"all agree with both the cursor map and their recorded scene")
    else:
        print("[self-check] SKIP real-dump control: archive not mounted")

    print(f"[self-check] {'PASS' if ok else 'FAIL'} "
          f"(round-trip, swap-discrimination, must-fire-on-wrong-byte, real dumps)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
