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

**Review runs on a ladder, and each level reads only the level below's output:**
L0 every checkpoint (`check_ledger` + the roll), L1 every ~10 rolls
(`scripts/audit.py`), L2 daily (`scripts/audit_l2.py`), L3 weekly
(`scripts/audit_l3.py`). `check_ledger.py` nags when any is due, and its hook
**exits 2 on an overdue level** so the nag cannot be missed. Never let a level
read raw data — that is what makes it cheap enough to actually happen.

**The handoff's FIRST FIVE MINUTES is a SESSION-START check, not a per-checkpoint
one.** Between checkpoints, re-run only what your own last checkpoint could have
invalidated — the ledger check, the roll, and the self-test of any script you
edited. Re-running the guard pair and the stray-process check when no game ran
and no hook changed is ceremony, and ceremony makes a real check easy to skip.

**OPEN every checkpoint by announcing the roll** — verdict, draw, eps and
target — **before doing any of the work.** A roll reported only in the write-up
cannot be told apart from one rationalised after the fact, and that is the whole
thing the roll exists to prevent.

**Close every checkpoint with one plain-language sentence saying what it
achieved — AT THE VERY END of the write-up, not the start (T124); it is a
closing line. `scripts/ledger.py --sowhat` pulls up recent ones, and
USER-DIRECTED work gets one too, even though no roll was consumed** — no hex, no entry IDs, no tool names. If the honest answer is
"nothing moved forward, I fixed a measuring instrument", say that; exposing
that distinction is the whole point of the sentence.

`route.py` prints both requirements — the opening one above the roll line, the
closing one at the end — and `scripts/test_route.py` asserts each is defined,
is printed, and (for the opening one) is printed *before* the roll it refers to.

**THE CLOSING SENTENCE ALSO GOES IN THE ENTRY, as `SO WHAT: <sentence>` (T120).**
Saying it aloud is not enough: it was the only part of a checkpoint with no
mechanical check, and it is the part that got skipped — on the same checkpoint
that drifted. `check_ledger.py` now asks at write time, and it checks the
sentence is **plain**, not merely present: an address, an entry ID, a filename
or a register fails it. Everything that was checked survived; the one thing
that was not, did not.

## New tools — three gates (T71)

Before a new tool's output counts as evidence:
1. **Dry run first.** If it generates a script or command, it must be able to
   print what it would do and exit. Look at that before the first real run.
2. **A control that can fail.** A positive control that discriminates, or a
   `--self-check` verified to FAIL when the tool is broken — not merely to pass
   when it works.
3. **Written up in the playbook in the same checkpoint**, naming its purpose,
   its controls, and the incident that motivated it.

## User-observed runs (T101)

**THE FIRST TASK OF EACH DAY**, and immediately on anything observable
changing. **`route.py` REFUSES TO ROLL until it is done or explicitly
deferred** (`--defer '<reason>'`, reason mandatory); no roll is consumed by
the refusal and all other work is unaffected. I cannot clear the gate myself,
which is why a deferral clears it — **the rule is not "it happened", it is
"it was not silently skipped"** — a run past the crash point, a changed fault signature, a new scene,
audio appearing. Run `scripts/observed_run.sh`; it prints
`docs/observation-checklist.md` first and records the outcome **either way**.

**IT NEVER ACCUMULATES, AND NOTHING RECURRING ON THIS PROJECT MAY (T151, the
user's rule).** A day with no work on the project owes nothing. The gate asks
"is there one for TODAY", never "how many were missed", and it only fires when a
roll is attempted — so idle days create no debt. **Miss three days and the next
working day still owes ONE run, never two.** These checks spend the USER'S time;
one that bills them for days they were not here is one they will abandon, and
then the safeguard is gone. **Any new recurring check is activity-gated, not
calendar-gated** — and check the code before claiming an existing one already is.

Two things I cannot check: **I cannot HEAR audio** — but it is CAPTURED on
observed runs (T102) and **amplitude is measurable, which is not the same as
hearing** (A265: another recompiled N64 game run headless on this machine reads
−24 dB while ours reads a flat −91 dB, so the silence is the game, not the
recorder and not headlessness). ~~the recorder captures video only, so A97 rests
entirely on reading source~~ — that was true of `run_game.sh` only, and the
conclusion never followed. And **scene identity has been wrong twice from
sampling** (A93, A161 — the observation right, the quantifier wrong). **A disagreement from the user becomes its own ledger entry,
never a quiet correction.**

## Sub-agents are sanctioned, with measured limits (T157/T158)

**`docs/agent-brief.md` is the single source** — Part 1 decides whether to spawn
one, Part 2 is pasted into the prompt verbatim. Do not restate its rules
anywhere; a second copy goes stale.

The three that must be true before spawning: **default Fable 5, Opus 5 when a
miss is expensive, never below Sonnet 5 for anything requiring a verdict**; ask
for **lists, not conclusions**, because a narrative costs the same to check as
to derive; and **nothing enters the ledger without my own reads** — an agent's
absence is never evidence.

## When I need the user, I STOP (T154)

**Their instruction, 2026-08-22.** The moment the work needs their hands, eyes
or ears: **stop, say so at the TOP of the message, and do nothing else until
they answer.** Not at the end of a write-up, not after finishing the other
things I could have done meanwhile.

**This deliberately OVERRIDES "do everything that does not depend on the answer
first."** That habit is what buried the ask last time — a run was launched into
the background and I carried on writing entries while they were at the keyboard.
Work done while they wait is work done with their attention already spent.

Say **what** is needed, **how long** it takes, and **what is blocked** on it. One
ask at a time. Never start a background task that will need them mid-flight.

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
* **A control that cannot fail is not a control** (T65), and **a control that
  greps its own file is the usual way one stops discriminating** — three
  instances now (T100). Assemble the needle from parts; never exempt the file.
* **A new checker whose FIRST real run finds nothing should be suspected,
  not celebrated** (T100). Working checkers surprise you on day one.
* **A CONTRADICTION IS A PREMISE AUDIT, NOT A NEW EXPERIMENT** (T107). If a
  checkpoint concludes measurements "cannot all be right", the next one on
  that item **enumerates the premises and attacks the least-verified**, and may
  not run another experiment under them. A99's third circle cost ~15 rolls to
  a premise that fell in two greps.
* **A MEASURED entry may be FLAGGED by an argument but only OVERTURNED by
  measurement** (T107) — same-run/same-window, or a static proof. A141 was
  dismissed twice on plausibility and vindicated twice by measurement.
* **Every negative names its scope inside the claim** — "nothing in splat's
  asm calls this", not "nothing calls this".
* **A single-run claim answers for itself, in the entry** (T99). If an
  entry cites one run log, `check_ledger.py` now asks at write time —
  repeat it, cite a second log, or write **`ONE RUN IS ENOUGH: <reason>`**.
  Asked now because asked-at-audit-time has failed 21 times.
