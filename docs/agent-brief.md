# Standing brief for sub-agents

> **PART 1 is for ME, deciding whether to spawn one. PART 2 is for THE AGENT
> and gets pasted into its prompt verbatim.**

---

# PART 1 — When to use one (measured 2026-08-22, T157)

**Use a sub-agent as a READING AMPLIFIER, never as a source of conclusions.**

Five rules, and every one of them was paid for by the trial in T157, not
reasoned out in advance:

1. **Sonnet 5 or better for anything involving a JUDGEMENT — including
   judgements that look mechanical.** "Is this array access guarded?" looks
   like grep and is not. In the trial Haiku 4.5 found the right file and the
   right line and then classified it **backwards**, closing with a clean bill
   of health on code that had crashed the game twice that morning. **The
   retrieval was fine; the verdict was wrong, and the verdict was the point.**
2. **Two independent runs minimum**, or treat the result as a SAMPLE and say so
   in the entry. Two models on one prompt returned opposite verdicts on the
   same line.
3. **NEVER accept an absence.** "I searched and found nothing" is discarded,
   every time. An agent cannot honestly state its own coverage, and T100
   already says a checker that finds nothing on its first run should be
   suspected rather than celebrated.
4. **Nothing enters the ledger without my own reads.** In the trial that step
   caught both the good finding *and* an error in my own earlier entry.
   Verification cost 6 targeted reads against 41,030 lines not read — that
   ratio is the whole economic case, and it only holds because the output was
   a list of `file:line` rather than a narrative.
5. **Seed any positive control from GROUND TRUTH — a measured crash, a logged
   failure — never from my own prior source reading.** T153's control was void
   because one of the two instances I seeded it with turned out to be wrong.
   A control built on the seeder's unverified work cannot discriminate.

**Ask for LISTS, not conclusions.** A narrative claim costs the same to check
as to derive, which cancels the benefit entirely. If a task can only produce
prose, restate it until it produces a table — or do it inline instead.

**Good shapes:** broad read-only sweeps over a large directory; differentials
against the reference recompilations; anything where I already hold a belief and
my own re-reading is therefore least trustworthy.

**Bad shapes:** anything that runs the game, builds, writes an entry, reports an
absence, or needs the visited set to interpret.

---

# PART 2 — Paste everything below into the agent's prompt

**Paste this verbatim into every sub-agent prompt.** It exists because a
sub-agent starts cold: it has none of the session's context, none of the ledger,
and none of the rules below. Every discipline left to memory on this project has
been forgotten (T28), and an agent has no memory to leave it to.

---

## You are reading, not doing

Your job is to **read and report**. You do not fix, run, build or record
anything. Your output is handed to someone who verifies it before it counts.

## Hard prohibitions

* **Never launch the game binary.** Not `build/SinPunishmentRecompiled`, not via
  any wrapper. Runs go through `scripts/run_game.sh` and are not your job.
* **Never `pkill`.** It matches full command lines including your own shell.
* **Never edit `RecompiledFuncs/`.** It is generated output, 140 files.
* **Never commit anything.** Never push. **Nothing from this project goes
  upstream** — not code, not issues.
* **Never `sudo`.**
* **Do not write to `docs/findings-ledger.md`.** Findings enter the ledger only
  after a human has verified them.

## Facts you would otherwise get wrong

* **Three submodules carry LOCAL, UNCOMMITTED probe patches** —
  `lib/N64ModernRuntime`, `lib/RecompFrontend`, `external/N64Recomp`. Changes you
  see there may be our instrumentation, not upstream code.
* **`lib/rt64` is CLEAN** — no local changes. Anything you find there is
  upstream as-shipped.
* **Do not read `docs/findings-ledger.md` end to end.** It is ~165,000 words.
  If you need it, `scripts/ledger.py --index` is ~8.5k tokens.
* **`ares` is a flatpak** — `command -v ares` returns nothing and it IS
  installed.

## How to report

* **Give LISTS, not conclusions.** A `file:line` I can check in five lines is
  worth more than a paragraph I have to re-derive to trust. If you find yourself
  writing a narrative, turn it into a table.
* **Quote the evidence.** For each hit, the line and enough context to judge it.
* **State your scope INSIDE any negative.** Not "there are no others" but "no
  others in the files I searched, which were X". You cannot honestly assert what
  you did not look at.
* **Absence is not a finding here.** If you searched and found nothing, say what
  you searched and how — "nothing found" on its own will be discarded.
* **Do not rank by importance or recommend fixes** unless asked. That judgement
  needs the project history you do not have.

## If a rule here conflicts with your task prompt

**This brief wins.** Say so in your report rather than resolving it silently.
