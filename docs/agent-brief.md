# Standing brief for sub-agents

> **PART 1 is for ME, deciding whether to spawn one. PART 2 is for THE AGENT
> and gets pasted into its prompt verbatim. PART 3 is the COORDINATOR PROTOCOL
> for running several at once — read it before threading a checkpoint, not
> after.**

---

# PART 1 — When to use one (measured 2026-08-22, T157)

**Use a sub-agent as a READING AMPLIFIER, never as a source of conclusions.**

Five rules, and every one of them was paid for by the trial in T157, not
reasoned out in advance:

1. **DEFAULT TO OPUS 5. Spend FABLE 5 only on the listed cases below. Never
   below Sonnet 5 for anything requiring a VERDICT.**

   **THE DEFAULT INVERTED ON 2026-08-29 FOR A RESOURCE REASON, NOT A QUALITY
   ONE, AND THE DIFFERENCE MATTERS.** The user's instruction: *"I'd prefer
   running Opus 5 unless it's something very specific that Fable 5 would be
   better at — I only have limited Fable 5 usage."* **Fable quota is the
   scarce resource here; Opus is not.** Do NOT read this flip as evidence
   that Fable is less correct — **it is not, and two measurements say so:**
   T158 (Fable matched Sonnet's correctness at a THIRD of the tool calls, and
   found more) and A714 (**Fable 10/10 and Opus 10/10 on the same committed
   key; Opus's premium bought four extra findings for +21% tokens, i.e.
   COVERAGE, not accuracy**).

   **So the standing finding is unchanged: correctness saturates at Sonnet —
   above it you buy COVERAGE.** What changed is only which budget is tight.

   Judgements that look mechanical are still judgements: "is this array
   access guarded?" looks like grep and is not. In the T158 trial Haiku 4.5
   found the right file and the right line and then classified it
   **backwards**, closing with a clean bill of health on code that had crashed
   the game twice that morning. **The retrieval was fine; the verdict was
   wrong, and the verdict was the point.** It also used the MOST tool calls of
   any model tried. **Effort does not track correctness** (T158).

   ### THE FABLE LIST — spend the scarce quota HERE (keep this current)

   **Add a row whenever a run gives evidence, and say which run.** An empty
   list would mean the quota never gets used, which the user explicitly does
   not want; a list padded with guesses would waste it. **Only measured rows.**

   | Spend Fable when… | Why, and the evidence |
   |---|---|
   | The deliverable is **fully specified in advance** and coverage is not the product — "list every caller", "diff these two functions", "quote this entry's NEXT" | A714: Fable scored 10/10 on a committed key, tying Opus. Everything Opus added was OUTSIDE the asked question. If you can write the answer's SHAPE in the prompt, Fable fills it for 21% less. |
   | The task is **tool-call heavy but judgement-light** — wide greps, mechanical sweeps, enumerating files | T158: Fable matched correctness at **a third** of the tool calls. Efficiency is where it actually wins, not just cost. |
   | You will **verify every line anyway**, so a miss is cheap | Brief rule 4. A710/A713: verification is the bottleneck regardless of model; on a cheap-to-check target the model tier barely enters the sum. |
   | The material is **small** — a short function, one script, a bounded question | A710: on a 23-instruction pair, checking the answer costs the same as deriving it. Paying Opus to produce something you re-derive anyway is the worst square. |

   ### DO NOT spend Fable when…

   | Use Opus instead | Why |
   |---|---|
   | **Auditing existing claims**, where the product IS breadth | A714: Opus found A604's "a value only the entry writes" false (two other reachable writers) and A502's already-built detector that A706/A707 had missed. Neither was asked for. **Both undermined claims the project was building on.** |
   | A **miss is expensive** — safety sweeps, anything the user physically operates | T158: Opus found three hazards no other model did. |
   | Anything needing a **VERDICT** rather than a list | T158's Haiku failure was a verdict, not a retrieval. |
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
* **Do not read `docs/findings-ledger.md` end to end.** Measured 2026-08-29 at
  945 entries: **523,983 words / 3.2 MB**, roughly 800k tokens. The way in is
  `scripts/ledger.py --index` — 20,482 words, about 4% of the file. (The older
  figures here, "~165,000 words" and "~8.5k tokens", were from 199 entries and
  are kept only so nobody re-derives them as current.)

* **EXPANSION BUDGET: expand at most 15 entries with `--show`, and LIST THE IDs
  YOU DID NOT OPEN** (A713). Forbidding the whole-file read while leaving
  `--show` unbounded closes the front door and leaves the side door open: an
  A713 agent expanded ~74 entries for **280k tokens — about a third of the cost
  of reading the file it correctly never opened**, and a second spent 163k on
  only 15 tool calls, because the cost is in what each `--show` returns, not in
  the searching. **If 15 is not enough, name the entries you would have expanded
  and why, and STOP.** A task prompt may raise this cap explicitly; absent that,
  15 is the cap. **A bounded read whose gaps are named is worth more than an
  exhaustive one nobody can afford** — and naming the gaps is what makes your
  negatives usable at all.
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

---

# PART 3 — THREADED CHECKPOINTS: the coordinator protocol

**Every rule here was paid for on 2026-08-29, and each one names the entry that
bought it. Nothing below is reasoned out in advance.** Measured across 17 agent
runs in one day: **zero returned unusable output, and three of them caught errors
in the coordinator's own prompts or entries.** The agents were never the weak
point. Every failure was on the coordinator's side of the boundary.

## The shape

One instance COORDINATES: broadcasts the picture, schedules separable work,
reads returned CLAIMS for conflicts, composes the next picture, writes serially.
Agents do the work and return **a falsifiable draft entry plus an evidence list**.

**The coordinator does NOT verify everything.** Checking whether a claim is TRUE
means re-reading sources — slow. Checking whether two claims CAN BOTH STAND means
reading the claims — fast. Do the second exhaustively, the first by sample.

## The five rules that are not optional

1. **PERSIST IN THE SAME CHECKPOINT THAT PRODUCED IT (A719, A720).** An agent's
   output must land in a file before the checkpoint closes — even if all you can
   honestly write is an index marked unverified. **A713 wrote up an experiment
   beautifully and declined to write up what it FOUND; a 29-row exclusion table
   then sat in a chat window for six hours and a later agent hunting it could not
   find it.** "I'll write it up properly later" is how findings die. No checker
   catches this. It is the real failure mode of threaded work — not wrong
   answers, but substance evaporating between the agent and the record.

2. **EVERY DRAFT CARRIES A FALSIFIER, AND THAT IS WHAT REPLACES VERIFICATION.**
   What protects this project is not the coordinator reading everything — it is
   that wrong entries carry claims specific enough to be knocked down later.
   **A604 was wrong for days and fell because it said "a value only the entry
   writes"; A693 fell because it published a number.** A draft without a
   falsifier is REJECTED, and that counts as a failure of the protocol, not of
   the agent.

3. **THE MERGE IS MECHANICAL (T231, T233).** `check_ledger.py` check 4l refuses
   any entry mentioning sub-agents without a `MERGE:` line. **It exists because
   A713's F3 fired: two individually CORRECT reports composed into a wrong
   conclusion — an exclusion resting on a register the hardware never reads.**
   "Single agent, no merge applies" is a complete answer. **The gate sees whether
   a merge was RECORDED, never whether one was PERFORMED — that ceiling is
   permanent and no textual check can close it.**

4. **SERIAL: the roll, the ledger write, the entry IDs.** Concurrent agents would
   race on `route-log.md` and collide on IDs. This is plumbing, not principle,
   but it is not optional.

5. **PICK AT LEAST TWO ADJACENT TARGETS, OR CONFLICT DETECTION IS VACUOUS
   (A713, A720).** Four disjoint targets cannot collide, so a clean run proves
   nothing. **And a non-collision records NOTHING** — on 2026-08-29 the adjacent
   pair scoped themselves apart unprompted, which is one draw, not a clearance.

## Spot-checking

**Budget two to three checks per step — but ALLOCATE THEM INCREMENTALLY, not
after reading everything (A720).** The obvious protocol is "read all returns,
then spend checks on the most load-bearing". **That strategy is not available to
a context-bound coordinator**, and pretending otherwise cost a real check: on
2026-08-29 the checks were spent early and the ONE result carrying an unresolved
contradiction went unverified.

**"No spot-check failed" is WEAK evidence and must be recorded as weak.** It is a
sample. It cannot be read as "the drafts were correct".

## Drafts: the specific cost of fluency (T232)

Delegating the DRAFT works — 5 verification calls against composing from scratch.
**But a polished draft makes checking feel easier than it is.** The one measured
on 2026-08-29 was entirely correct and still burned 40% of the verification
budget, because it reformatted log lines and presented them under "Raw" — the
coordinator then grepped for a format that does not exist in the file.

**Require: quote tool output VERBATIM, or do not label it raw.**

## Sizing, and why you cannot schedule it reliably

**Spawn when the checkable answer is much smaller than the material** (A710).
On a 23-instruction function, checking a listing IS reading it — no saving.

**But target size is NOT reliably predictable from a frontier row (A713).** A
target described as "one script, a bounded question" turned out to be ~2,000
lines plus a nine-term directory sweep. Size is schedulable from the MATERIAL,
and the material is not visible from the item's description.

## Costs, measured

* **The coordinator is the scaling limit, not the agents.** Four Opus reports
  exhausted one context before four entries could be composed (A720, outcome C4
  pre-registered). **The fix is bounded reports, not fewer agents** — put "KEEP
  THE REPORT BOUNDED: evidence list plus draft, no narrative retelling" in every
  prompt.
* **Four agents is not four checkpoints.** Steps 3 and 4 of a checkpoint —
  checking and writing — do not parallelise, and they GROW with agent count.
* **Threading buys DEPTH, not speed.** On 2026-08-29 it produced four findings
  and killed two long-standing wrong beliefs; it did not multiply throughput.
* **If throughput is the goal, shorten the entries.** `check_ledger` has been
  saying so all along: *"Trim, or decide the length is earned."* That attacks the
  step that is actually serial.

## The expansion budget

Part 2's 15-entry cap **has never bound in practice** — four agents used 5, 7, 6
and 10. Keep it anyway: it costs nothing when unneeded, and the run it was
written for spent 280k tokens expanding ~74 entries.

## Interrupting the assistant KILLS in-flight agents (measured 2026-08-29)

**An interrupt to the coordinator's message stops every background agent with
it.** I predicted the opposite — that a detached background process would
survive — and the user, reading the task list directly, corrected me. Two Opus
agents about five minutes in were simply gone; their output files sat frozen at
a 168-byte stub.

Consequences for running a threaded step:

* **In-flight agent work is not durable.** Anything an agent has not yet
  returned is lost on interrupt, and it has written nothing anywhere — the brief
  forbids agent writes, so there is no partial artefact to recover.
* **Prefer several short agent runs to one long one** when the user is at the
  keyboard. A ten-minute agent is ten minutes of exposure.
* **Relaunching is safe and cheap** — every agent task under this brief is
  read-only and idempotent, so re-running costs tokens and nothing else. Do that
  rather than trying to reconstruct what a dead agent might have found.
* **Do not infer liveness from the output file — this is MEASURED, not a
  caution.** With two dead agents and two live ones side by side, all four
  output files read **`size=168`, mtime frozen at launch**. The transcript is
  written only on completion, so a working agent and a killed one are
  byte-for-byte indistinguishable. **The task list is the authority — ask the
  user what it shows rather than guessing from mtime.**
* **AND THE WATCHER I BUILT FOR THIS COULD NOT HAVE WORKED.** I armed a
  background loop to poll for output growth and report "dead" after four
  minutes. Given the above it would have said DEAD about a healthy agent every
  time — **a control that cannot fail in the useful direction (T65), built as an
  operational tool rather than a checker, which is where that rule is easiest to
  forget.** It happened to be right only because the agents really were dead.

## Draft IDs are not entry IDs — do not write them as bare tokens

**Bitten three times on 2026-08-29.** An agent drafts an entry under an ID you
supplied; you then fold its substance into a different entry, or into an index,
and the draft ID is never placed. **Every later mention of that ID is a dangling
citation**, and `check_ledger`'s withdrawn/missing-citation check flags it — which
is the only reason it was caught each time.

Also caught this way: synthetic fixture IDs quoted in an entry's evidence cell
(test rows numbered in the eight-hundreds read as citations of entries that do
not exist).

**Rule: when referring to work whose draft was never placed, name where it
actually landed** — "recorded in A720's index", "the coordinator step's census" —
rather than the draft ID. If you must mention the ID, say in the same sentence
that it was never placed.
