#!/usr/bin/env python3
"""Compute where every compressed code overlay is unpacked to, from the ROM alone.

WHY
---
About a third of this game's code is stored Yay0-compressed and was never
segmented, disassembled or recompiled -- which is why a scene load can complete
having registered nothing (see docs/findings-ledger.md B28/B30). Fixing that
needs each chunk's *runtime* address, because the recompiler has to know where
code will live.

The addresses turn out to be fully deterministic, so they can be computed here
rather than observed:

    D_800744D8 starts at 0x802B4000            (boot_func_80025E44)
    boot_func_80026340 loads file 0x2D, then snapshots D_800744D4 = cursor
    every scene resets the cursor to D_800744D4 (boot_func_800263CC)
    each entry: cursor -= decompressed_size; chunk lands at the new cursor

Only boot_func_8003A290 moves that cursor -- confirmed by xref: the sole writers
of D_800744D8 are boot_func_80025E44, 80026340 and 800263CC. The sibling loaders
boot_func_8003A324/8003A41C advance unrelated *index* counters (seeded 0x1B and
0x77), not the memory cursor.

Emits a JSON map and a short summary. Nothing here runs the game.
"""
import json
import struct
import sys
from pathlib import Path

ROM_TO_VRAM = 0x80024C00  # boot/main segment: vram = rom + this

# Table addresses, all read out of the ROM image.
T_FILES = 0x800599F0  # [i] -> rom offset of file i (size = [i+1] - [i])
T_COUNT = 0x8005912C  # [scene-1] -> u8 number of 3-byte entries
T_LIST = 0x80059144   # [scene-1] -> ptr to that scene's entry list
T_INIT = 0x800591A0   # [scene-1] -> scene init function
CURSOR_START = 0x802B4000  # D_800744D8 initial value
BOOT_FILE = 0x2D           # loaded by boot_func_80026340 before the base snapshot
MAX_SCENE = 23             # T_INIT is terminated by 0xFFFFFFFF at index 23


def yay0_decompress(src: bytes) -> bytes:
    """Standard Yay0. Header: magic, decompressed size, link offset, chunk offset."""
    if src[:4] != b"Yay0":
        raise ValueError("not Yay0")
    size, link_off, chunk_off = struct.unpack_from(">III", src, 4)
    out = bytearray(size)
    mask_p, link_p, chunk_p, pos = 0x10, link_off, chunk_off, 0
    mask, bits = 0, 0
    while pos < size:
        if bits == 0:
            mask = struct.unpack_from(">I", src, mask_p)[0]
            mask_p += 4
            bits = 32
        if mask & 0x80000000:
            out[pos] = src[chunk_p]
            chunk_p += 1
            pos += 1
        else:
            link = struct.unpack_from(">H", src, link_p)[0]
            link_p += 2
            dist = (link & 0x0FFF) + 1
            count = link >> 12
            if count == 0:
                count = src[chunk_p] + 0x12
                chunk_p += 1
            else:
                count += 2
            start = pos - dist
            for i in range(count):
                out[pos + i] = out[start + i]
            pos += count
        mask = (mask << 1) & 0xFFFFFFFF
        bits -= 1
    return bytes(out)


def main() -> int:
    rom_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        __file__).resolve().parent.parent / "rom" / "Tsumi to Batsu - Hoshi no Keishousha (Japan).z64"
    d = rom_path.read_bytes()

    def u32(vram):
        return struct.unpack_from(">I", d, vram - ROM_TO_VRAM)[0]

    def u8(vram):
        return d[vram - ROM_TO_VRAM]

    # File table: monotonic rom offsets, ends when it stops ascending.
    files = []
    i = 0
    while True:
        v = u32(T_FILES + i * 4)
        if not (0 < v < len(d)) or (files and v < files[-1]):
            break
        files.append(v)
        i += 1

    def info(idx):
        off = files[idx]
        comp = files[idx + 1] - off
        if d[off:off + 4] == b"Yay0":
            return off, comp, struct.unpack_from(">I", d, off + 4)[0], True
        return off, comp, comp, False

    base = CURSOR_START - info(BOOT_FILE)[2]

    scenes, code_chunks, data_chunks = [], 0, 0
    for scene in range(1, MAX_SCENE + 1):
        n = scene - 1
        cnt, lst, init = u8(T_COUNT + n), u32(T_LIST + n * 4), u32(T_INIT + n * 4)
        cursor, entries = base, []
        for k in range(cnt):
            idx = d[(lst - ROM_TO_VRAM) + k * 3]
            if idx == 0xFF:
                continue
            off, comp, dec, packed = info(idx)
            cursor -= dec
            body = yay0_decompress(d[off:off + comp]) if packed else d[off:off + comp]
            # Density of `addiu $sp, $sp, -N` at word alignment. Testing only
            # the first word is wrong: the known-good code overlay at ROM
            # 0x772030 opens with `lui`, not a prologue. Real code carries many
            # prologues; asset data essentially none.
            prologues = sum(1 for o in range(0, len(body) - 3, 4)
                            if body[o] == 0x27 and body[o + 1] == 0xBD and body[o + 2] == 0xFF)
            is_code = prologues >= 8
            code_chunks += is_code
            data_chunks += not is_code
            entries.append({"file": idx, "rom": off, "comp": comp, "size": dec,
                            "vram": cursor, "yay0": packed, "code": is_code,
                            "prologues": prologues})
        scenes.append({"scene": scene, "init": init, "entries": entries})

    out = {"base": base, "cursor_start": CURSOR_START, "files": len(files), "scenes": scenes}
    dest = Path(__file__).resolve().parent.parent / "overlay_map.json"
    dest.write_text(json.dumps(out, indent=1))

    print(f"file table: {len(files)} entries   per-scene base D_800744D4 = 0x{base:08X}")
    print(f"chunks: {code_chunks} code, {data_chunks} data")
    for s in scenes:
        if not s["entries"]:
            print(f"  scene {s['scene']:2d} init=0x{s['init']:08X}  (no entries)")
        for e in s["entries"]:
            print(f"  scene {s['scene']:2d} init=0x{s['init']:08X}  file 0x{e['file']:02X} "
                  f"rom 0x{e['rom']:07X} size 0x{e['size']:06X} -> vram 0x{e['vram']:08X} "
                  f"{'CODE' if e['code'] else 'data'}")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
