#!/usr/bin/env python3
"""Ablation screen driver — batch-run the game with one function stubbed per run.

WHY (2026-08-26, user-directed; the technique survey session)
-------------------------------------------------------------
The runtime hook (SNP_ABLATE in lib/N64ModernRuntime/librecomp/src/overlays.cpp,
NEVER COMMITTED, same as every probe) first-byte-patches a listed function to
RET at startup, making it `jr ra; nop`.  This script runs one target per run,
collects a per-run SIGNATURE, and writes one TSV row per run.  Its job is
TRIAGE: a row that differs from baseline names a CANDIDATE, never a claim —
T22's rule stands (no claim on fewer than 3 runs per arm; the screen is 1).

THE SIGNATURE, per run
  verdict / wall / gfx_total / gfx_rate   — read from docs/run-log.tsv's own row
  patched_n                               — count of "[ablate] ... PATCHED RET"
                                            lines in the game log; 0 => INVALID
                                            (the stub did not happen; the run
                                            says nothing about the target)
  aud_pct / aud_rms_db                    — non-zero sample %% and RMS of the
                                            SNP_AUDIO_DUMP raw (deleted after
                                            stats unless --keep-audio)
  geom digest per armed task              — counts of v/t/r lines plus a hash of
                                            the t/r sequence between task=N
                                            BEGIN/END markers ([dlgeom] goes to
                                            stderr, i.e. into the game log)

CONTROLS (measured 2026-08-26, before any screen row existed):
  positive  — stub boot_gameEntry (0x80025C40): 0 frames, DEGRADED, vs 1297
              CLEAN baseline.  The mechanism and the signature both discriminate.
  negative  — stub 0x800E47F0 (ovlfile05, never loaded in the 250 s attract log):
              signature identical to baseline (1298 frames CLEAN, aud 86.9%%).
  refuse    — a vram that is no function start halts the run at init (exit 2)
              rather than silently ablating nothing (T65).
  NOTE the alAudioFrame result: stubbing 0x80042B2C changed NOTHING — the SDK
  driver the oracle named (A444) is present in ROM but is not the runtime audio
  path.  Audio amplitude therefore does NOT discriminate for SDK-audio targets;
  frames/verdict/geometry are the load-bearing signals.

Resumable: targets already present in the output TSV are skipped, so a killed
screen continues where it stopped.  BASELINE is a row like any other and is run
first if absent.
"""

import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN_LOG_TSV = REPO / "docs" / "run-log.tsv"
RUN_GAME = REPO / "scripts" / "run_game.sh"

TSV_COLS = ("ts", "target", "name", "secs", "verdict", "wall", "gfx_total",
            "gfx_rate", "patched_n", "aud_pct", "aud_rms_db", "geom", "log")


# --------------------------------------------------------------------------
# parsing helpers — each is exercised by --self-check on ASSEMBLED fixtures,
# never on this file or on live data (T100).

def parse_runlog_row(row: str):
    """docs/run-log.tsv row -> dict of the fields the signature needs."""
    parts = row.rstrip("\n").split("\t")
    # header: ts secs_req secs_actual rc input leftover gfx_total gfx_rate verdict log env
    if len(parts) < 10:
        return None
    return {
        "ts": parts[0], "secs_req": parts[1], "wall": parts[2],
        "gfx_total": parts[6], "gfx_rate": parts[7], "verdict": parts[8],
        "log": parts[9],
    }


def count_patched(game_log_text: str) -> int:
    """How many functions did the hook actually stub?  0 on an ablated run
    means the run is INVALID — it measured the ordinary game."""
    # needle assembled from parts so no self-referential match is possible
    needle = "[abl" + "ate]"
    return sum(1 for ln in game_log_text.splitlines()
               if needle in ln and ln.rstrip().endswith("PATCHED RET"))


def geom_digests(game_log_text: str):
    """Per armed task: v/t/r counts + sha1 of the ordered t/r lines.
    Returns {task: 'v<n>t<n>r<n>:<sha1-12>'} — comparable across runs."""
    out = {}
    task = None
    counts = None
    h = None
    tag = "[dlg" + "eom]"
    for ln in game_log_text.splitlines():
        if tag not in ln:
            continue
        body = ln.split(tag, 1)[1].strip()
        m = re.match(r"task=(\d+) BEGIN", body)
        if m:
            task = int(m.group(1))
            counts = {"v": 0, "t": 0, "r": 0}
            h = hashlib.sha1()
            continue
        m = re.match(r"task=(\d+) END", body)
        if m and task is not None:
            out[task] = (f"v{counts['v']}t{counts['t']}r{counts['r']}"
                         f":{h.hexdigest()[:12]}")
            task = None
            continue
        if task is not None and body[:1] in ("v", "t", "r"):
            counts[body[0]] += 1
            if body[0] in ("t", "r"):
                h.update(body.encode())
    return out


def audio_stats(raw_path: Path):
    """(pct_nonzero, rms_dbfs) of an s16le dump, or (None, None)."""
    try:
        data = raw_path.read_bytes()
    except OSError:
        return None, None
    n = len(data) // 2
    if n == 0:
        return 0.0, float("-inf")
    samples = struct.unpack(f"<{n}h", data[:n * 2])
    nz = sum(1 for s in samples if s != 0)
    acc = 0.0
    for s in samples:
        acc += float(s) * s
    rms = (acc / n) ** 0.5
    db = float("-inf") if rms == 0 else 20 * __import__("math").log10(rms / 32768.0)
    return 100.0 * nz / n, db


# --------------------------------------------------------------------------

def load_targets(path: Path):
    """Lines: <vram-hex> [name...].  '#' comments and blanks skipped."""
    targets = []
    for ln in path.read_text().splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        parts = ln.split(None, 1)
        vram = parts[0]
        int(vram, 16)  # must parse; a typo here must die now, not at run 400
        targets.append((vram.lower(), parts[1].strip() if len(parts) > 1 else ""))
    return targets


def done_targets(tsv: Path):
    done = set()
    if tsv.exists():
        for ln in tsv.read_text().splitlines()[1:]:
            parts = ln.split("\t")
            if len(parts) >= 2:
                done.add(parts[1])
    return done


def run_one(target, name, args, outdir: Path, tsv: Path):
    """One screen run.  target='BASELINE' means no ablation."""
    stamp = time.strftime("%H%M%S")
    tag = "baseline" if target == "BASELINE" else target
    log = outdir / f"ablate-{tag}-{stamp}.log"
    raw = outdir / f"ablate-{tag}-{stamp}.raw"

    cmd = [str(RUN_GAME), str(args.secs), str(log)]
    if target != "BASELINE":
        cmd.append(f"SNP_ABLATE={target}")
    if args.geom:
        # SNP_DL_GEOM lives INSIDE the census block (events.cpp) -- without
        # SNP_DL_CENSUS armed it is silently inert, measured 2026-08-26 on this
        # harness's own first smoke test (geom=NA on every row).
        cmd.append("SNP_DL_CENSUS=1")
        cmd.append(f"SNP_DL_GEOM={args.geom}")
    cmd.append(f"SNP_AUDIO_DUMP={raw}")

    if args.dry_run:
        print("DRY-RUN would exec:", " ".join(cmd))
        return

    subprocess.run(cmd, check=False, capture_output=True)

    row = parse_runlog_row(RUN_LOG_TSV.read_text().splitlines()[-1])
    if row is None or Path(row["log"]).name != log.name:
        # the run-log row is not ours: record the anomaly, do not guess
        row = {"ts": time.strftime("%FT%T"), "wall": "NA", "gfx_total": "NA",
               "gfx_rate": "NA", "verdict": "NO-RUNLOG-ROW", "log": log.name}

    text = log.read_text(errors="replace") if log.exists() else ""
    patched = count_patched(text)
    valid = (target == "BASELINE") or patched >= 1
    geoms = geom_digests(text)
    pct, db = audio_stats(raw)
    if raw.exists() and not args.keep_audio:
        raw.unlink()

    geom_s = ";".join(f"{k}={v}" for k, v in sorted(geoms.items())) or "NA"
    verdict = row["verdict"] if valid else "INVALID-NO-PATCH"
    with tsv.open("a") as f:
        f.write("\t".join([
            row["ts"], target, name, str(args.secs), verdict, row["wall"],
            row["gfx_total"], row["gfx_rate"], str(patched),
            "NA" if pct is None else f"{pct:.1f}",
            "NA" if db is None else f"{db:.2f}",
            geom_s, log.name,
        ]) + "\n")
    print(f"[{time.strftime('%H:%M:%S')}] {target} {name}: {verdict} "
          f"wall={row['wall']} gfx={row['gfx_total']} aud={pct if pct is None else round(pct,1)}%")


# --------------------------------------------------------------------------

FIX_RUNLOG = ("2026-08-26T15:26:08+10:00\t45\t45\t0\t0\t0\t1297\t30\tCLEAN\t"
              "ablate-ctl-positive.log\tSNP_ABLATE=0x80042B2C")
FIX_LOG_OK = ("[abl" + "ate] 0x80042B2C -> section idx 0 (rom 0x00001000) "
              "native 0x1 rom_size 0x1B0 : PATCHED RET\n"
              "[dlg" + "eom] armed for 1 task(s)\n"
              "[dlg" + "eom] task=900 BEGIN\n"
              "[dlg" + "eom] v 0 1 2 3\n"
              "[dlg" + "eom] t 0 1 2 99\n"
              "[dlg" + "eom] r a 1 2 3 4\n"
              "[dlg" + "eom] task=900 END ok=1\n")
FIX_LOG_NOPATCH = "SDL Video Driver: x11\nnothing here\n"


def self_check(break_n: int = 0) -> int:
    checks = []

    row = parse_runlog_row(FIX_RUNLOG)
    checks.append(("run-log row parses", row is not None and row["verdict"] == "CLEAN"
                   and row["gfx_total"] == "1297" and row["log"].endswith(".log")))

    fix = FIX_LOG_OK if break_n != 1 else FIX_LOG_NOPATCH
    checks.append(("patched line counted", count_patched(fix) == 1))

    checks.append(("unpatched log flagged", count_patched(FIX_LOG_NOPATCH) == 0))

    g = geom_digests(FIX_LOG_OK)
    checks.append(("geom digest built", g.get(900, "").startswith("v1t1r1:")))

    g2 = geom_digests(FIX_LOG_OK.replace("t 0 1 2 99", "t 0 1 2 98"))
    same = g.get(900) == g2.get(900) if break_n != 2 else True
    checks.append(("digest sees a 1-triangle change", not same))

    silent = struct.pack("<4h", 0, 0, 0, 0)
    loud = struct.pack("<4h", 16384, -16384, 16384, -16384)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tf:
        tf.write(loud if break_n != 3 else silent)
        p = Path(tf.name)
    pct, db = audio_stats(p)
    p.unlink()
    checks.append(("audio stats discriminate", pct == 100.0 and db is not None
                   and abs(db - (-6.02)) < 0.1))

    ok = 0
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok += passed
    print(f"self-check {ok}/{len(checks)}")
    return 0 if ok == len(checks) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--targets", type=Path, help="file: <vram-hex> [name] per line")
    ap.add_argument("--secs", type=int, default=45)
    ap.add_argument("--geom", default="", help="SNP_DL_GEOM task list, e.g. 900,1000")
    ap.add_argument("--outdir", type=Path, required=False)
    ap.add_argument("--limit", type=int, default=0, help="stop after N targets (testing)")
    ap.add_argument("--keep-audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print every command that would run, run nothing (T71 gate 1)")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--self-check-break", type=int, default=0, metavar="N",
                    help="deliberately break fixture N (1-3) to prove the check can fail")
    args = ap.parse_args()

    if args.self_check or args.self_check_break:
        sys.exit(self_check(args.self_check_break))

    if not args.targets or not args.outdir:
        ap.error("--targets and --outdir are required for a screen")
    args.outdir.mkdir(parents=True, exist_ok=True)
    tsv = args.outdir / "ablate-screen.tsv"
    if not tsv.exists() and not args.dry_run:
        tsv.write_text("\t".join(TSV_COLS) + "\n")

    targets = [("BASELINE", "unablated")] + load_targets(args.targets)
    done = done_targets(tsv) if not args.dry_run else set()
    todo = [(t, n) for t, n in targets if t not in done]
    if args.limit:
        todo = todo[:args.limit]

    est_h = len(todo) * (args.secs + 5) / 3600
    print(f"{len(todo)} run(s) to do ({len(done)} already in TSV); "
          f"worst-case ~{est_h:.1f} h at {args.secs}s each (crashes finish sooner)")

    for t, n in todo:
        run_one(t, n, args, args.outdir, tsv)


if __name__ == "__main__":
    main()
