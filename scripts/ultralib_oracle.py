#!/usr/bin/env python3
"""Match a compiled ultralib against our ROM: named SDK oracle at OUR build kind.

THE ROUTE THIS COMPLETES (A443, user-approved 2026-08-25): borrowing names
from other GAMES mostly fails -- MM is a different build kind (A440), Banjo
crosses only on the precompiled tier (A442). But Bangai-O proved era-matched
binaries match on compiled C, so an oracle COMPILED THE WAY OUR GAME WAS
BUILT -- ultralib (the public libultra reconstruction) at IDO -O2 _FINALROM --
carries names for exactly the band where our 145 anonymous shared functions
live, the audio library included (A97's territory).

WHY .o RELOCATION HOLES ARE NOT A PROBLEM, and in fact are the point: an
unlinked object's JAL targets and HI16/LO16 halves are addends, not addresses.
`symbol_transplant.skeleton()` masks EXACTLY those fields on both sides, so a
masked object function and a masked ROM function are directly comparable.
This tool reuses that skeleton and that matcher UNCHANGED -- one definition of
"matches", one set of validated controls (A440's five, plus this file's own).

VERSION IS DECIDED BY VOTE, NOT ASSUMPTION. S&P's microcode string (F3DEX2
2.08, 1999) brackets the SDK era but does not name the libultra revision.
Every built version is matched; the one that recovers the most of our 57
already-named functions is the era match, and only ITS new names are emitted.

    scripts/ultralib_oracle.py --versions I J K L        # vote, then report
    scripts/ultralib_oracle.py --versions L --emit-into symbols/inferred-names.toml
    scripts/ultralib_oracle.py --self-check
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from symbol_transplant import (OUR_ROM, OUR_TOML, GENERIC, parse_toml,   # noqa: E402
                               extract, skeleton, match)
import hashlib  # noqa: E402

ULTRALIB = Path.home() / "Documents/reference-recomps/ultralib"
OBJDUMP = "mips-linux-gnu-objdump"
OBJCOPY = "mips-linux-gnu-objcopy"


SYM_RE = re.compile(r"([0-9a-f]{8})\s+\S+\s+F\s+\.text\s+([0-9a-f]{8})\s+(\S+)$")


def obj_functions(obj_path, tmpdir):
    """[(name, words)] for every defined FUNC in the object's .text."""
    try:
        symtab = subprocess.run([OBJDUMP, "-t", str(obj_path)],
                                capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return []
    funcs = []
    for line in symtab.splitlines():
        m = SYM_RE.match(line)
        if m:
            off, size, name = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            if size >= 8 and size % 4 == 0:
                funcs.append((name, off, size))
    if not funcs:
        return []
    blob = tmpdir / (obj_path.stem + ".bin")
    r = subprocess.run([OBJCOPY, "-O", "binary", "--only-section=.text",
                        str(obj_path), str(blob)], capture_output=True)
    if r.returncode or not blob.exists():
        return []
    raw = blob.read_bytes()
    out = []
    for name, off, size in funcs:
        chunk = raw[off:off + size]
        if len(chunk) == size:
            out.append((name, [int.from_bytes(chunk[i:i + 4], "big")
                               for i in range(0, size, 4)]))
    return out


def oracle_side(version, tmpdir, target="libultra_rom"):
    """{name: (pseudo_vram, hash, nwords)} for one built ultralib version."""
    build = ULTRALIB / "build" / version / target
    side = {}
    fake = 0
    for obj in sorted(build.rglob("*.o")):
        for name, words in obj_functions(obj, tmpdir):
            sk = skeleton(words)
            h = hashlib.sha1(b"".join(w.to_bytes(4, "big") for w in sk)).hexdigest()
            # duplicate symbol across objects (shouldn't happen in one lib) --
            # keep first, count would show in self-collisions anyway
            if name not in side:
                side[name] = (fake, h, len(words))
                fake += len(words) * 4
    return side


def run(versions, emit_into=None, target="libultra_rom"):
    import tempfile
    our_rom = OUR_ROM.read_bytes()
    ours_all = extract(our_rom, parse_toml(OUR_TOML))
    named_by_vram = {v: n for n, (v, _h, _w) in ours_all.items()
                     if not GENERIC.match(n)}
    blinded = {f"@{v:08X}": (v, h, w) for n, (v, h, w) in ours_all.items()}
    print(f"[oracle] target={target}; our functions: {len(blinded)}, "
          f"of which named (validation set): {len(named_by_vram)}")

    results = {}
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for v in versions:
            side = oracle_side(v, tmpdir, target)
            if not side:
                print(f"[oracle] 2.0{v}: NO OBJECTS -- not built?")
                continue
            exact, ambig = match(side, blinded)
            hits = [(m, named_by_vram[vr]) for m, _t, vr, _w in exact
                    if vr in named_by_vram]
            agree = sum(1 for m, t in hits if m == t)
            disagree = [(m, t) for m, t in hits if m != t]
            new = [(m, vr, w) for m, _t, vr, w in exact if vr not in named_by_vram]
            results[v] = (exact, ambig, agree, disagree, new)
            print(f"[oracle] 2.0{v}: oracle-funcs={len(side)}  exact-unique={len(exact)}  "
                  f"validation {agree} agree / {len(disagree)} disagree  NEW={len(new)}")
    if not results:
        return 1

    best = max(results, key=lambda v: results[v][2])
    exact, ambig, agree, disagree, new = results[best]
    print(f"\n[oracle] ERA VOTE: 2.0{best} ({agree} of {len(named_by_vram)} "
          f"named functions recovered)")
    for m, t in disagree:
        print(f"[oracle]   DISAGREE: oracle says {m}, our map says {t}")
    au = [x for x in new if re.match(r"^(_?al|__al|n_al)", x[0])]
    print(f"[oracle] NEW names from 2.0{best}: {len(new)} ({len(au)} audio)")
    for name, vr, w in sorted(new, key=lambda x: x[1]):
        tag = "AUDIO" if re.match(r"^(_?al|__al|n_al)", name) else "     "
        print(f"    {tag} @{vr:08X} ({w:4}w)  {name}")

    if emit_into:
        p = Path(emit_into)
        s = p.read_text() if p.exists() else ""
        s += (f"\n# --- FROM THE ULTRALIB 2.0{best} ORACLE, IDO -O2 _FINALROM "
              f"(A444) -- compiled at\n"
              f"# our build kind from public libultra source; era chosen by vote "
              f"({agree}/{len(named_by_vram)}\n"
              f"# of our named functions recovered). Skeleton-exact, unique both "
              f"ways.\n")
        for name, vr, w in sorted(new, key=lambda x: x[1]):
            conf = "LOW confidence, uniqueness only" if w <= 3 else f"{w} words"
            s += f'0x{vr:08X} = "{name}"'.ljust(42) + f"# {conf}\n"
        p.write_text(s)
        print(f"[oracle] appended {len(new)} row(s) to {emit_into}")
    return 0


# ---------------------------------------------------------------------------
# CONTROLS -- the extraction path is the new code, so that is what they hit.
# The skeleton and matcher carry A440's five controls; not repeated here.
# ---------------------------------------------------------------------------
def self_check():
    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"[selfcheck] {'PASS' if cond else 'FAIL'} {name} {detail}")

    import tempfile
    build = ULTRALIB / "build" / "I" / "libultra_rom"
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        fs = obj_functions(build / "src/os/recvmesg.o", tmpdir)
        names = {n: w for n, w in fs}
        # C1: a known object yields its known function at its known size.
        chk("C1 recvmesg.o yields osRecvMesg at its symtab size",
            len(names.get("osRecvMesg", [])) == 0x138 // 4,
            f"{ {n: len(w) for n, w in fs} }")
        # C2: the SYMBOL REGEX ITSELF rejects an undefined-symbol row even
        # when its size field is large. THE FIRST VERSION CHECKED BEHAVIOUR
        # ("__osDisableInt not extracted") AND A DELIBERATE REGEX BREAK WENT
        # UNCAUGHT -- the size>=8 gate masked it, so the control was testing
        # the gate, not the regex. Now the regex is fed a crafted UND row
        # with a NONZERO size, which only the regex can reject.
        chk("C2 regex rejects an *UND* row regardless of size",
            SYM_RE.match("00000000       F *UND*\t00000138 __osDisableInt") is None
            and SYM_RE.match("00000000 g     F .text\t00000138 osRecvMesg") is not None)
        # C3: ALIGNMENT. osRecvMesg's raw words must start at its prologue
        # (addiu sp,sp,-0x28 = 0x27BDFFD8) and end jr-ra + stack restore.
        # THE FIRST VERSION ONLY CHECKED MASKED JALS, AND A DELIBERATE
        # 4-BYTE EXTRACTION SHIFT WENT UNCAUGHT -- every shifted JAL still
        # masks to the bare opcode. Raw boundary words catch a shift of any
        # size.
        w = names["osRecvMesg"]
        chk("C3 extraction is aligned to the function boundary",
            w[0] == 0x27BDFFD8 and w[-2] == 0x03E00008 and w[-1] == 0x27BD0028,
            f"first={w[0]:08X} last2={w[-2]:08X},{w[-1]:08X}")
        # C4: oracle_side's HASH equals a hash computed independently from
        # obj_functions + skeleton. THE FIRST VERSION NEVER EXERCISED
        # oracle_side AT ALL -- a deliberate break that skipped masking there
        # went uncaught because the control recomputed the skeleton itself.
        side = {}
        for name, words in fs:
            sk = skeleton(words)
            side[name] = hashlib.sha1(b"".join(x.to_bytes(4, "big")
                                               for x in sk)).hexdigest()
        full = oracle_side("I", tmpdir)
        c4 = "osRecvMesg" in full and full["osRecvMesg"][1] == side["osRecvMesg"]
        chk("C4 oracle_side hash matches an independent skeleton hash", c4,
            "" if c4 else ("hash mismatch" if "osRecvMesg" in full else "missing"))
        # C5: a multi-symbol object splits into distinct functions.
        fs2 = obj_functions(build / "src/io/vi.o", tmpdir)
        chk("C5 multi-symbol object extracts distinct functions",
            len(fs2) >= 1 and len({n for n, _ in fs2}) == len(fs2),
            f"{[n for n, _ in fs2]}")

    print(f"[selfcheck] {'ALL PASS' if ok else 'FAILURES ABOVE'}")
    return 0 if ok else 1


def main(argv):
    if "--self-check" in argv:
        return self_check()
    if "-h" in argv or "--help" in argv or not argv:
        print(__doc__)
        return 0
    versions = []
    if "--versions" in argv:
        i = argv.index("--versions") + 1
        while i < len(argv) and not argv[i].startswith("--"):
            versions.append(argv[i])
            i += 1
    emit = argv[argv.index("--emit-into") + 1] if "--emit-into" in argv else None
    target = argv[argv.index("--target") + 1] if "--target" in argv else "libultra_rom"
    return run(versions or ["I", "J", "K", "L"], emit, target)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
