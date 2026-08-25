#!/usr/bin/env python3
"""T197 phase 0+1: skeleton-match Mischief Makers' named functions onto ours.

THE BET (user-approved 2026-08-24, U14 -> T197): Treasure shipped Mischief
Makers in 1997 and Sin & Punishment in 2000. The other port's symbol map names
245 Treasure-engine functions and 364 libultra/SDK ones; ours names 57 (the
SDK tier, by Ghidra + hand work) out of 6,808. If the code matches, the names
transfer -- INTO A STANDALONE MAP, never into RecompiledFuncs/ (T197: a wrong
name in a lookup file is a one-line fix; burned into 30,000 generated files it
is a disaster).

HOW A MATCH IS MADE -- THE SKELETON. Each function's words are masked so that
fields which legitimately differ between two link layouts cannot break a
match, and everything else must be IDENTICAL:

    masked to zero: the 26-bit target of J/JAL; the imm16 of LUI, ADDI/ADDIU,
                    ORI, and every load/store (address halves and data
                    offsets move between games).
    kept verbatim:  opcode, register fields, shifts, SPECIAL/REGIMM functs,
                    branch offsets (internal, position-independent), ANDI/
                    XORI/SLTI/SLTIU immediates (flags and comparisons, rarely
                    addresses).

A match must be EXACT on the masked words, SAME LENGTH, and UNIQUE IN BOTH
DIRECTIONS. Anything with two candidates on either side is AMBIGUOUS and is
reported, never accepted. Empty beats wrong at every step (T197).

THE TWO CONTROLS THAT CAN FAIL, per T197's own design:
  * BLIND HOLDOUT -- our 57 hand/Ghidra-named functions have their names
    hidden from the matcher; MM's map names the same SDK routines; the
    matcher must land MM's name on OUR address for a healthy share of them,
    or phase 1 is dead and the item closes cheap. The holdout is graded
    against names it never saw.
  * SELF-COLLISION CENSUS -- within ONE game, two different functions
    sharing a skeleton hash measure how loose the mask is. If the mask is so
    aggressive that unrelated functions collide wholesale, cross-game
    "matches" are noise. Reported per side, every run.
NEGATIVE CONTROL STILL OWED (stated so it is not silently dropped): the same
matcher between two UNRELATED games must find ~nothing beyond SDK code. We
have no function boundaries for a third game, so this runs before any
TREASURE-tier match is accepted -- phase 1's SDK tier is covered by the
holdout, which is the stronger control for that tier anyway.

    scripts/symbol_transplant.py --dry-run       # what would be read, then exit
    scripts/symbol_transplant.py                 # phase 1: match + holdout grade
    scripts/symbol_transplant.py --emit MAP.toml # write the inferred-name view
    scripts/symbol_transplant.py --self-check
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUR_TOML = ROOT / "symbols" / "sinpunishment.syms.toml"
OUR_ROM = ROOT / "rom" / "sinpunishment.z64"          # ORIGINAL, not patched:
# the syms describe the shipped layout and the patched ROM may not carry it.
MM_TOML = Path.home() / ("Documents/reference-recomps/trouble-makers-pc-recomp/"
                         "symbols/troublemakers.us1.toml")
MM_ROM = ROOT / "rom" / "Mischief Makers (USA) (Rev 1).z64"
MM_SHA = "e00ab74c3dee79efaafe8e10f2a6b67784d7327ab588d8ef90ad8945427da627"

GENERIC = re.compile(r"^(boot_func|main_func|func|D)_[0-9A-Fa-f]+(_[0-9A-Fa-f]+)?$|^ovl")
SDKISH = re.compile(r"^(_|__|os|al|sp|gu|bcopy|bzero|str|mem|sqrt|sin|cos|rmon|kdebug)")


def parse_toml(path):
    """[(section, rom, vram, size, [(name, vram, size), ...]), ...] in order.

    The functions arrays follow their [[section]] header; a full TOML parser
    is not needed for this fixed generator format, and both files come from
    the same generator family.
    """
    secs, cur = [], None
    for line in path.read_text().splitlines():
        m = re.match(r'\s*name = "([^"]+)"\s*$', line)
        if m:
            cur = {"name": m.group(1), "funcs": []}
            secs.append(cur)
            continue
        m = re.match(r"\s*rom = (0x[0-9A-Fa-f]+)", line)
        if m and cur is not None and "rom" not in cur:
            cur["rom"] = int(m.group(1), 16)
            continue
        m = re.match(r"\s*vram = (0x[0-9A-Fa-f]+)", line)
        if m and cur is not None and "vram" not in cur:
            cur["vram"] = int(m.group(1), 16)
            continue
        m = re.match(r'\s*\{ name = "([^"]+)", vram = (0x[0-9A-Fa-f]+), size = (0x[0-9A-Fa-f]+)', line)
        if m and cur is not None:
            cur["funcs"].append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
    return [s for s in secs if "rom" in s and "vram" in s and s["funcs"]]


def skeleton(words):
    out = []
    for w in words:
        op = w >> 26
        if op in (2, 3):                      # J / JAL: mask 26-bit target
            w &= 0xFC000000
        elif op in (8, 9, 13, 15,             # ADDI, ADDIU, ORI, LUI
                    32, 33, 34, 35, 36, 37, 38, 39,   # LB..LWR
                    40, 41, 42, 43, 46,               # SB..SWR
                    49, 53, 57, 61):                  # LWC1, LDC1, SWC1, SDC1
            w &= 0xFFFF0000                   # mask imm16
        out.append(w)
    return out


def extract(rom_bytes, secs, keep=lambda n: True):
    """{name: (vram, hash, nwords)} for every function whose bytes are in ROM."""
    out = {}
    for s in secs:
        base_rom, base_vram = s["rom"], s["vram"]
        for name, vram, size in s["funcs"]:
            if not keep(name):
                continue
            off = base_rom + (vram - base_vram)
            raw = rom_bytes[off:off + size]
            if len(raw) != size or size < 8 or size % 4:
                continue
            words = [int.from_bytes(raw[i:i + 4], "big") for i in range(0, size, 4)]
            sk = skeleton(words)
            h = hashlib.sha1(b"".join(w.to_bytes(4, "big") for w in sk)).hexdigest()
            out[name] = (vram, h, len(words))
    return out


def collide(side):
    """{hash: [names]} restricted to hashes carried by >1 function."""
    byh = {}
    for name, (_v, h, _n) in side.items():
        byh.setdefault(h, []).append(name)
    return {h: ns for h, ns in byh.items() if len(ns) > 1}


def match(mm, ours):
    """Unique-both-ways skeleton matches: [(mm_name, our_name, our_vram, nwords)]."""
    mm_byh, our_byh = {}, {}
    for n, (_v, h, _w) in mm.items():
        mm_byh.setdefault(h, []).append(n)
    for n, (_v, h, _w) in ours.items():
        our_byh.setdefault(h, []).append(n)
    exact, ambig = [], []
    for h, mm_names in mm_byh.items():
        if h not in our_byh:
            continue
        our_names = our_byh[h]
        if len(mm_names) == 1 and len(our_names) == 1:
            on = our_names[0]
            exact.append((mm_names[0], on, ours[on][0], ours[on][2]))
        else:
            ambig.append((mm_names, our_names))
    return sorted(exact, key=lambda t: t[2]), ambig


def run(dry=False, emit=None, rom_path=OUR_ROM):
    import hashlib as hl
    mm_rom = MM_ROM.read_bytes()
    got = hl.sha256(mm_rom).hexdigest()
    if got != MM_SHA:
        print(f"[transplant] REFUSING: MM ROM sha256 {got[:16]}... != documented "
              f"{MM_SHA[:16]}... -- their addresses are revision-specific (T197 step 0)")
        return 2
    print(f"[transplant] MM ROM verified against documented SHA-256")
    our_rom = rom_path.read_bytes()
    mm_secs = parse_toml(MM_TOML)
    our_secs = parse_toml(OUR_TOML)

    if dry:
        print(f"[transplant] DRY RUN -- would extract:")
        print(f"  MM : {sum(len(s['funcs']) for s in mm_secs)} functions "
              f"across {len(mm_secs)} section(s) from {MM_ROM.name}")
        print(f"  our: {sum(len(s['funcs']) for s in our_secs)} functions "
              f"across {len(our_secs)} section(s) from {rom_path.name}")
        print(f"  then skeleton-hash both sides, match, and grade the blind "
              f"holdout ({57} hidden names). No file is written without --emit.")
        return 0

    # MM side: only functions with real names -- matching anonymous-to-
    # anonymous transfers nothing.
    mm_named = extract(mm_rom, mm_secs,
                       keep=lambda n: not GENERIC.match(n) and n != "recomp_entrypoint")
    # Our side: EVERYTHING, names hidden. The matcher sees addresses only.
    ours_all = extract(our_rom, our_secs)
    holdout = {n: v for n, (v, _h, _w) in ours_all.items() if not GENERIC.match(n)}
    blinded = {f"@{v:08X}": (v, h, w) for n, (v, h, w) in ours_all.items()}

    print(f"[transplant] extracted MM named={len(mm_named)}  ours(all)={len(ours_all)}  "
          f"holdout(hidden)={len(holdout)}")

    # CONTROL: self-collision census, both sides.
    for label, side in (("MM-named", mm_named), ("ours-all", blinded)):
        c = collide(side)
        n_funcs = sum(len(v) for v in c.values())
        print(f"[transplant] self-collisions {label}: {len(c)} hash(es) shared by "
              f"{n_funcs} function(s)")

    exact, ambig = match(mm_named, blinded)
    print(f"[transplant] EXACT-UNIQUE matches: {len(exact)}   ambiguous groups: {len(ambig)}")

    # BLIND HOLDOUT GRADE. A match lands on a holdout address; MM's name and
    # our hidden name refer to the same SDK routine when they are equal after
    # stripping leading underscores/prefixes -- graded strictly on equality.
    hold_hits, hold_wrong = [], []
    by_vram = {v: n for n, v in holdout.items()}
    for mm_name, our_tag, vram, _w in exact:
        if vram in by_vram:
            truth = by_vram[vram]
            (hold_hits if mm_name == truth else hold_wrong).append(
                (mm_name, truth, vram))
    print(f"[transplant] HOLDOUT: {len(hold_hits)} recovered exactly, "
          f"{len(hold_wrong)} landed on a named address with a DIFFERENT name, "
          f"of {len(holdout)} hidden")
    for mm_name, truth, vram in hold_wrong:
        print(f"    DISAGREE @{vram:08X}: MM says {mm_name}, our map says {truth}")

    # The new names: matches onto addresses our map does NOT name.
    new = [(m, v, w) for m, t, v, w in exact if v not in by_vram]
    treasure = [x for x in new if not SDKISH.match(x[0])]
    sdk_new = [x for x in new if SDKISH.match(x[0])]
    print(f"[transplant] NEW names for anonymous functions: {len(new)} "
          f"(SDK {len(sdk_new)}, TREASURE-tier {len(treasure)})")
    for name, vram, w in sorted(new, key=lambda x: x[1]):
        tier = "SDK " if SDKISH.match(name) else "TRSR"
        print(f"    {tier} @{vram:08X} ({w:4} words)  {name}")

    if emit:
        lines = ["# Inferred names, transplanted from the Mischief Makers port's map.",
                 "# EVERY ROW IS AN INFERENCE (T197): skeleton-exact, unique both ways.",
                 "# This file is a VIEW for readers and tools. RecompiledFuncs is never edited.",
                 f"# holdout at emit time: {len(hold_hits)}/{len(holdout)} recovered, "
                 f"{len(hold_wrong)} disagreements", ""]
        for mm_name, our_tag, vram, w in exact:
            marker = by_vram.get(vram, "")
            lines.append(f'0x{vram:08X} = "{mm_name}"'
                         + (f"  # our map already names this {marker}" if marker else ""))
        Path(emit).write_text("\n".join(lines) + "\n")
        print(f"[transplant] wrote {emit} ({len(exact)} row(s))")
    return 0


# ---------------------------------------------------------------------------
# CONTROLS, and the break each must catch is DIFFERENT (A261).
# ---------------------------------------------------------------------------
def self_check():
    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"[selfcheck] {'PASS' if cond else 'FAIL'} {name} {detail}")

    # C1: the mask hits exactly the fields it claims. LUI imm masked...
    lui = 0x3C088012          # lui t0, 0x8012
    sw = 0xAD09001C           # sw  t1, 0x1C(t0)
    jal = 0x0C012345          # jal <target>
    andi = 0x31EF00FF         # andi t7, t7, 0xFF -- must be KEPT
    beq = 0x11090003          # beq t0, t1, +3 -- offset KEPT
    sk = skeleton([lui, sw, jal, andi, beq])
    chk("C1 mask zeroes LUI/SW imm and JAL target only",
        sk == [0x3C080000, 0xAD090000, 0x0C000000, andi, beq], f"{[hex(w) for w in sk]}")

    # C2: two functions differing ONLY in an address half must collide
    # (that is the point of the mask)...
    a = [lui, sw, 0x03E00008, 0x00000000]
    b = [0x3C088077, 0xAD090F00, 0x03E00008, 0x00000000]
    chk("C2 address-half difference collapses", skeleton(a) == skeleton(b))

    # ...and C3: differing in a KEPT field must NOT collide.
    c = [lui, 0xAD0A001C, 0x03E00008, 0x00000000]   # different rt register
    chk("C3 register difference survives the mask", skeleton(a) != skeleton(c))

    # C4: matching demands uniqueness both ways. Two identical MM functions
    # matching one of ours must come back AMBIGUOUS, not accepted.
    mk = lambda ws: ("x", hashlib.sha1(b"".join(w.to_bytes(4, "big")
                     for w in skeleton(ws))).hexdigest(), len(ws))
    mm = {"MM_f1": (0x100,)+mk(a)[1:], "MM_f2": (0x200,)+mk(a)[1:]}
    ours = {"@1": (0x80001000,)+mk(a)[1:]}
    ex, am = match(mm, ours)
    chk("C4 duplicate-source match is ambiguous, never accepted",
        ex == [] and len(am) == 1, f"exact={ex}")

    # C5: the parser reads a section+functions fragment correctly, including
    # a second section, so an overlay cannot inherit the wrong base.
    import tempfile
    frag = ('[[section]]\nname = ".a"\nrom = 0x1000\nvram = 0x80000000\n'
            'size = 0x100\nfunctions = [\n'
            '    { name = "f1", vram = 0x80000010, size = 0x8 },\n]\n'
            '[[section]]\nname = ".b"\nrom = 0x2000\nvram = 0x80000000\n'
            'size = 0x100\nfunctions = [\n'
            '    { name = "f2", vram = 0x80000010, size = 0x8 },\n]\n')
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        f.write(frag)
    secs = parse_toml(Path(f.name))
    Path(f.name).unlink()
    # THE FIXTURE CAUGHT MY OWN FIXTURE: the first version used
    # bytes(range(256))*64, which is PERIODIC with period 256 -- and the two
    # rom bases are congruent mod 256, so both sections read identical bytes
    # and the control failed against a correct extractor. Same lesson as
    # dup_draws C4 and gap_classify C5, third day running: a control is only
    # a control if the fixture means what it claims. Non-periodic bytes:
    rom = bytes(((i * 37) ^ (i >> 8)) & 0xFF for i in range(0x3000))
    e = extract(rom, secs)
    chk("C5 two sections at one vram extract from their OWN rom bases",
        len(secs) == 2 and len(e) == 2 and e["f1"][1] != e["f2"][1],
        f"secs={len(secs)} funcs={list(e)}")

    print(f"[selfcheck] {'ALL PASS' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


def main(argv):
    if "--self-check" in argv:
        return self_check()
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    emit = argv[argv.index("--emit") + 1] if "--emit" in argv else None
    return run(dry="--dry-run" in argv, emit=emit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
