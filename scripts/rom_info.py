#!/usr/bin/env python3
"""Sin & Punishment ROM analysis / conversion helpers.

Usage:
  rom_info.py convert <in.n64> <out.z64>   # V64 (16-bit swap) -> Z64 big-endian
  rom_info.py info <rom.z64>               # header + boot + microcode scan

All facts verified 2026-08-06; see docs/research.md.
"""
import hashlib
import struct
import sys
from pathlib import Path

BOOT_SIG = bytes.fromhex("3c08800625083450")  # lui t0,0x8006; addiu t0,t0,0x3450


def v64_to_z64(data: bytes) -> bytes:
    out = bytearray(data)
    for i in range(0, len(out) - 1, 2):
        out[i], out[i + 1] = out[i + 1], out[i]
    return bytes(out)


def info(path: Path) -> None:
    raw = path.read_bytes()
    z = v64_to_z64(raw)
    title_z = z[0x20:0x34].decode("latin1")
    title_raw = raw[0x20:0x34].decode("latin1")
    # V64 stores the title 16-bit swapped; the z64 form reads "TSUM..." cleanly.
    is_v64 = "TSUM" not in title_raw and "TSUM" in title_z
    d = z if is_v64 else raw
    print(f"file:            {path} ({len(d)} bytes)")
    print(f"format:          {'V64 (16-bit swap)' if is_v64 else 'Z64 (big-endian)'}")
    print(f"md5 (as-is):     {hashlib.md5(raw).hexdigest()}")
    print(f"md5 (z64):       {hashlib.md5(z).hexdigest()}")
    print(f"entrypoint:      0x{struct.unpack('>I', d[0x08:0x0C])[0]:08X}")
    print(f"release:         0x{struct.unpack('>I', d[0x0C:0x10])[0]:08X}")
    print(f"CRC1:            0x{struct.unpack('>I', d[0x10:0x14])[0]:08X}")
    print(f"CRC2:            0x{struct.unpack('>I', d[0x14:0x18])[0]:08X}")
    print(f"country:         0x{d[0x3E]:02X}  ({chr(d[0x3E]) if 32 <= d[0x3E] < 127 else '?'})")
    print(f"title:           {title_z!r}")
    print(f"boot sig @0x1000: {d[0x1000:0x1008].hex()} {'OK (standard libultra)' if d[0x1000:0x1008] == BOOT_SIG else 'UNKNOWN'}")
    for needle in [b"F3DEX", b"S2DEX", b"L3DEX", b"aspMain", b"Audio"]:
        idx = d.find(needle)
        print(f"string {needle.decode():8s} @ {hex(idx) if idx >= 0 else '-'}")
    print("boot disasm (first 8 instr):")
    for off in range(0x1000, 0x1020, 4):
        print(f"  0x{off:05X}: {struct.unpack('>I', d[off:off+4])[0]:08X}")


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "convert":
        src, dst = Path(sys.argv[2]), Path(sys.argv[3])
        dst.write_bytes(v64_to_z64(src.read_bytes()))
        print(f"wrote {dst} ({dst.stat().st_size} bytes)")
    elif cmd == "info":
        info(Path(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
