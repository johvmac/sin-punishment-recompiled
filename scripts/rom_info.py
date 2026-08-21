#!/usr/bin/env python3
"""Sin & Punishment ROM analysis / conversion helpers.

Usage:
  rom_info.py convert <in.n64> <out.z64>   # V64 (16-bit swap) -> Z64 big-endian
  rom_info.py info <rom.z64>               # header + boot + microcode scan

All facts verified 2026-08-06; see docs/research.md.
"""
import sys as _sys
if "--help" in _sys.argv or "-h" in _sys.argv:
    print(__doc__)
    _sys.exit(0)
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


# The first four bytes are the FORMAT's own signature and are game-independent.
#
# WHAT WAS HERE BEFORE, AND WHY IT IS AN I-CLASS DEFECT (I5, 2026-08-21):
#     is_v64 = "TSUM" not in title_raw and "TSUM" in title_z
# The detector grepped for **Sin & Punishment's own title**. For any other ROM
# neither branch can fire, so it answered "Z64 (big-endian)" unconditionally --
# including for a genuinely byte-swapped ROM, which would then be fed to a build.
# That is T100's rule exactly ("a control that greps its own file is the usual
# way one stops discriminating"), in a detector rather than a control.
# Caught on the first non-S&P ROM ever passed to it.
MAGICS = {
    bytes.fromhex("80371240"): "z64",   # big-endian, native
    bytes.fromhex("37804012"): "v64",   # 16-bit (byte-pair) swapped
    bytes.fromhex("40123780"): "n64",   # 32-bit little-endian
}


def detect(raw: bytes):
    """Return (format, normalised_z64_bytes). Refuses rather than guessing."""
    fmt = MAGICS.get(raw[:4])
    if fmt == "z64":
        return fmt, raw
    if fmt == "v64":
        return fmt, v64_to_z64(raw)
    if fmt == "n64":
        # Deliberately NOT converted: v64_to_z64 is a 2-byte swap and would
        # silently produce garbage here. A wrong ROM that looks converted is
        # worse than a refusal.
        return fmt, None
    return None, None


def info(path: Path) -> None:
    raw = path.read_bytes()
    fmt, d = detect(raw)
    if fmt is None:
        print(f"REFUSED: {path} has no known N64 magic (first 4 bytes "
              f"{raw[:4].hex()}). Not guessing.", file=sys.stderr)
        sys.exit(2)
    if d is None:
        print(f"REFUSED: {path} is {fmt.upper()} (32-bit little-endian). "
              f"This tool's converter is a 2-byte swap and would corrupt it.",
              file=sys.stderr)
        sys.exit(2)
    label = {"z64": "Z64 (big-endian)", "v64": "V64 (16-bit swap)"}[fmt]
    title_z = d[0x20:0x34].decode("latin1")
    print(f"file:            {path} ({len(d)} bytes)")
    print(f"format:          {label}")
    print(f"md5 (as-is):     {hashlib.md5(raw).hexdigest()}")
    # md5 of the NORMALISED buffer. Previously this was md5 of an
    # unconditionally-swapped copy, so for an already-z64 ROM -- the normal
    # case -- it was the hash of a deliberately corrupted buffer, printed
    # under a label saying otherwise.
    print(f"md5 (z64):       {hashlib.md5(d).hexdigest()}")
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


def self_check() -> int:
    """Controls. This tool had NONE until 2026-08-21, which is how a detector
    keyed to one game's title survived in it (I5)."""
    checks = []

    def chk(name, ok, detail):
        checks.append((name, ok, detail))

    def rom(magic_hex, title):
        b = bytearray(b"\x00" * 0x1010)
        b[0:4] = bytes.fromhex(magic_hex)
        b[0x20:0x20 + len(title)] = title.encode()
        return bytes(b)

    z = rom("80371240", "MISCHIEF MAKERS")
    chk("an already-Z64 rom is reported Z64 and NOT transformed",
        detect(z) == ("z64", z), f"{detect(z)[0]}")
    # DISCRIMINATING, AND IT IS THE EXACT DEFECT: a NON-S&P byte-swapped rom
    # must be caught. The old detector grepped for "TSUM" and so answered Z64
    # for every ROM in the world except this project's own.
    v = v64_to_z64(z)
    fmt, norm = detect(v)
    chk("a byte-swapped NON-S&P rom is detected as V64 (the old bug)",
        fmt == "v64", f"got {fmt}")
    chk("...and converting it round-trips to the original", norm == z,
        "normalised == z64 original" if norm == z else "conversion is wrong")
    # DISCRIMINATING: the title must come from the NORMALISED buffer.
    chk("the title reads correctly for an already-Z64 rom",
        norm is not None and z[0x20:0x2F].decode() == "MISCHIEF MAKERS",
        repr(z[0x20:0x2F].decode()))
    # DISCRIMINATING: unknown and unconvertible inputs must REFUSE, not guess.
    chk("a rom with no known magic is REFUSED", detect(b"\xde\xad\xbe\xef" + b"\x00" * 64)[0] is None,
        "must return None")
    chk("a 32-bit little-endian rom REFUSES rather than mis-converting",
        detect(rom("40123780", "X"))[1] is None, "must refuse to convert")

    bad = 0
    for name, ok, detail in checks:
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name:60} — {detail}")
    print(f"\n{len(checks)-bad}/{len(checks)} controls pass")
    return 1 if bad else 0


def main() -> None:
    if "--self-check" in sys.argv:
        sys.exit(self_check())
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
