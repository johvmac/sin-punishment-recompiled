# Standing brief for sub-agents

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
