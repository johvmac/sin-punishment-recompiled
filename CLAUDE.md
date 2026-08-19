# Standing instructions

Loaded automatically every session. **Keep this short.** It holds only the
things that must be true before any work starts; everything else lives in the
files it points at, and a duplicate here is a copy that will go stale.

## Read these, in this order

1. `HANDOFF-<latest date>.md` — perishable state (git position, current build,
   what is mid-flight). **Gitignored, so it is not in the repo listing** — look
   for it in the working directory. Run its FIRST FIVE MINUTES before touching
   anything; it is a set of checks, not advice, and each either passes or does
   not.
2. **`scripts/ledger.py --index`** — the VISITED SET. Do not re-derive what it
   records, withdrawn entries included. **Do not read
   `docs/findings-ledger.md` end to end**; it is 83k tokens and growing, and
   the index is ~8.5k. Expand with `scripts/ledger.py --show <ID>` before
   relying on anything: **the index says whether something was checked, never
   what it established.**
3. `docs/diagnostic-playbook.md` — how to run things without generating
   evidence that turns out to be worthless.

## How a checkpoint runs

A checkpoint is: `scripts/route.py` (a roll, recorded — skipping one leaves a
visible gap in `docs/route-log.md`), then the bounded work it selects, then a
ledger entry recording the outcome **either way**.

**The handoff's FIRST FIVE MINUTES is a SESSION-START check, not a per-checkpoint
one.** Between checkpoints, re-run only what your own last checkpoint could have
invalidated — the ledger check, the roll, and the self-test of any script you
edited. Re-running the guard pair and the stray-process check when no game ran
and no hook changed is ceremony, and ceremony makes a real check easy to skip.

**Close every checkpoint with one plain-language sentence saying what it
achieved** — no hex, no entry IDs, no tool names. If the honest answer is
"nothing moved forward, I fixed a measuring instrument", say that; exposing
that distinction is the whole point of the sentence. `route.py` prints this
requirement at the end of every roll and `scripts/test_route.py` asserts it is
still there.

## New tools — three gates (T71)

Before a new tool's output counts as evidence:
1. **Dry run first.** If it generates a script or command, it must be able to
   print what it would do and exit. Look at that before the first real run.
2. **A control that can fail.** A positive control that discriminates, or a
   `--self-check` verified to FAIL when the tool is broken — not merely to pass
   when it works.
3. **Written up in the playbook in the same checkpoint**, naming its purpose,
   its controls, and the incident that motivated it.

## Standing constraints

* **Nothing goes upstream** — not code, not issues (T36/T38).
* **Never edit `RecompiledFuncs/` to "fix" a bug.** It is generated.
* **Never commit from the `lib/N64ModernRuntime` working tree** — it carries
  local probe content that must not be published.
* **Do not commit ROMs or generated output.**
* **Do not enable system core dumps** — a core of this process is 11.8 GB
  (T63). Use `SNP_RDRAM_DUMP` and `scripts/rdram_peek.py`.
* **Runs are headless by default.** `scripts/display_isolate.sh` is the single
  source of isolation; never launch the binary directly (a guard refuses it).
* **`sudo` is the user's decision, not mine** — ask, do not run it.
* **Evidence cited before 2026-08-19 is unrecoverable** (T47) and must not be
  trusted. Preserve new evidence to the archive drive, never to `/tmp`.

## Method rules that were paid for

* **Name the composing step.** When an entry stitches verified parts into a
  story, say which step is the stitch and mark it unverified (T57).
* **Measure a new tool before trusting it.** Three shipped confident wrong
  answers in one session (T60/T62/T63, and again T64/T66).
* **A control that cannot fail is not a control** (T65).
* **Every negative names its scope inside the claim** — "nothing in splat's
  asm calls this", not "nothing calls this".
