# Observation checklist — what YOU should look for in a user-observed run

**Version 1, 2026-08-20.** Launch with `scripts/observed_run.sh`, which prints
this file before starting so you are not reading it afterwards from memory.

## Why this exists

Two failure classes motivate it, and they are different:

1. **I have been wrong twice about what is on screen** (A93, A161). Both times
   the *observation* was right and the **quantifier** was wrong — "at these two
   sampled instants" silently became "never". Sampling cannot support a claim
   about all the moments it did not sample. You watching continuously can.
2. **I cannot perceive audio AT ALL.** Until 2026-08-20 the pipeline had no
   audio input whatsoever — **A97 is entirely about audio silence, and every
   claim in it rested on reading source code, never on hearing anything.**
   Game-only audio is now captured (T102) so the answer outlives the run, but
   **a waveform still cannot tell me whether something sounds WRONG** —
   buzzing, wrong pitch, the wrong music. Ten seconds of you listening
   outranks all of it.

There is a third, quieter reason: the two of us can drift on what "the current
state" is. A shared look resets that.

## When this runs

* **THE FIRST TASK OF EACH DAY (T103).** `route.py` refuses to roll until this
  is done or deferred with a reason. No roll is consumed by the refusal. A day with no work does not
  need one — that is ceremony, and ceremony makes real checks easy to skip
  (T100 records the same mistake in the audit ladder's calendar trigger).
* **IT NEVER PILES UP (T151, the user's rule, 2026-08-22).** The gate asks "is
  there one for TODAY", never "how many were missed". **Miss a day — or a week —
  and the next working day still owes exactly ONE run, never two.** Nothing is
  owed for days you did not work on the project, and nothing needs catching up.
  This is a promise about *your* time: a check that bills you for days you were
  away is one you will stop doing, and then it protects nothing.
* **Immediately whenever something observable changes**, in particular:
  * a run survives past the known crash point without dying,
  * the crash signature changes (different function, line, or registers),
  * a scene appears that we have no reference frame for,
  * audio appears where there was none.

`check_ledger.py` nags for the daily case and flags the progress case from the
run log. **The nag is not the authority — if you want to look, look.**

---

# THE CHECKLIST

Work top to bottom. **Items marked ⚑ are things I cannot check myself at all**;
your answer is the only evidence that will ever exist for them.

## 1. ⚑ AUDIO — REWRITTEN 2026-08-25: the sound is ON, and this run closes A97

**The state changed completely on 2026-08-25 (A447): the silence was a
recompilation layout error, it is fixed, and you already heard sound and said
"it sounded perfect to me". This run is the FORMAL verdict you deferred to it.**

* **Is it the right music?** You have heard the real game's opening and
  tutorial (the paced ares reference, A436). Same tunes, same moments?
* **Sound effects and menu blips** — present, and matching what the reference
  had at the same points?
* ~~**CLIPPING — the one measured worry.**~~ **DROPPED 2026-08-25 (A459) — DO
  NOT SPEND ATTENTION ON THIS.** The capture does peak at full scale, but so
  does the real game's, to six identical digits, and **the reference hits full
  scale nearly twice as often as we do** (1,041 against 568). Peaking was a
  property of the capture path, not of our mixer. Loudness matches the real
  game within **0.09 dB**.
* **WHAT REPLACED IT, and it is a genuinely open question (A460).** After
  fixing the recorder's sample rate, one statistic still disagrees with the
  reference by 2.3x — a measure of repeated/held samples. It could be a real
  defect or it could just be that our attract and the reference's are not the
  same performance. **What it would SOUND like if real: a faint stutter,
  buzz, graininess, or notes that seem to "stick" or repeat.** Listen for
  texture rather than volume. **If it all sounds smooth, say so — that is the
  answer that makes the number a content artefact and closes it.**
* **THIS IS THE FIRST RUN RECORDED AT THE CORRECT RATE.** Every previous
  capture went through two resamples (A460). If something sounds different
  from last time, that may be why — and it is worth saying.
* **Stutter, dropouts, wrong pitch, one channel only** — any of the classic
  stream failures.
* **Does it survive the whole run** — through the attract, past START, into
  the tutorial, up to the stall?

### ⚑⚑ THE ONE THAT MATTERS MOST THIS RUN (added 2026-08-27) — DOES THE SOUND STAY WITH THE PICTURE?

**Judge it twice, and compare: once in the first twenty seconds, and again in
the last minute.** Does a sound land when the thing that makes it happens on
screen — an impact, a menu blip, a music change at a scene cut? Or does it
arrive late, and is it arriving *later* at the end than it was at the start?

**Why you and not a probe.** Overnight I measured the audio pipeline producing
far more sound than the output device can play, at a fixed ratio, so a backlog
accumulates. That measurement can say we *generate* too much. **It cannot say
whether any of it reaches your ears** — if the excess is being thrown away
somewhere downstream, the backlog is a number in a log and nothing else. There
is no probe I can write that settles that. You listening for one run does.

**I am deliberately not telling you what I expect to happen**, and that is not
coyness — a stated expectation collects agreement instead of a judgement, which
is the same reason my labels are never shown beside the labelling task. The
prediction is written down and timestamped from last night, so it cannot be
adjusted afterwards to match whatever you say. **Both answers are a real
result, and "it stayed in sync the whole way" is the more interesting one.**

> Why it matters: A97 is held open ONLY for this verdict. "Sounded right
> throughout" closes a 25-day investigation; any defect you can name becomes
> its first sharp follow-up. Either answer is a real result.

## 2. ⚑ THE MOMENT IT STOPS — REWRITTEN 2026-08-25/26. IT IS NOT A CRASH.

**This section used to ask about "the crash at 158 s". That framing is dead.**
A450/A451 measured it: **nothing crashes and nothing blocks.** The picture
freezes at around **205–213 s**, the task engine keeps dispatching tens of
thousands of handlers, and the audio keeps playing. The old text would have
sent you looking a minute early at the wrong thing.

**The single most valuable observation you can make this run:**

* **When the picture freezes — does the SOUND keep going?** For how long?
  Does it keep going right to the end, loop, or fade? *(I measure that it
  does, but a measurement of amplitude is not hearing it.)*
* **What is frozen on screen at that moment?** Name it in your own words.
* **⚑ THE LIVE QUESTION (A451).** The real game's tutorial constantly pauses
  on instruction cards and then **resumes**. Ours enters one of those pauses
  and **never leaves**. So: **does the freeze look like the game waiting
  mid-instruction — a text card up, character posed, as if expecting
  something — or like a hard lock mid-motion?** Those point at different
  faults and nothing but your eyes distinguishes them.
* Does anything visibly glitch, tear, or stutter in the ~10 s *before* it
  stops, or does it stop cleanly from full motion?
* Does the screen ever go **fully black** at any point near it?

> Why it matters: for twenty-odd checkpoints this was hunted as a thing that
> JAMS. Nothing jams. The question is now what should have started the next
> scene and did not — and "was it waiting, or was it stuck" is the fork.

## 3. THE TITLE SCREEN — I claim it is frame-for-frame correct

After a START press the title should render: green 罪と罰 / SIN AND PUNISHMENT
logo, プッシュ スタート, © 2000 Nintendo.

* Does it look **right**, or is anything **missing, mis-coloured, or in the
  wrong place**?
* Any **corruption**: missing layers, garbage pixels, wrong background.

> Why it matters: A162 claims our build draws it "matching the reference capture
> frame for frame". That is my comparison of stills. A "looks wrong to me"
> from you overrides it.

## 4. ~~HOW IT DIES~~ — RETIRED 2026-08-27. IT CONTRADICTED SECTION 2.

**This section asked "roughly when does it die? expected ~158s" while section 2
of this same document says in bold that the crash-at-158s framing is DEAD.** One
checklist cannot ask you to time a death it elsewhere tells you does not happen.
A450/A451 measured it: nothing crashes, nothing blocks — the picture freezes at
~205–213 s and the engine, the audio and the frame-swap machinery all run on.

**Section 2 is where the ending is now described, and it is the one to read.**
Nothing is lost by deleting this: every question here is either answered by the
run log or asked better in section 2.

> The general lesson, and it is why this is struck through rather than quietly
> removed: **a stale prompt does not merely fail to collect an answer — it aims
> your attention at a question that is already closed**, and this procedure
> spends the one resource the project cannot regenerate.

## 5. ⚑ THE SKYBOX, IN THE SOLDIERS SHOT (added 2026-08-25, user-requested)

**The shot:** the attract scene with the green soldiers — the one whose
reconstruction is `task 1500` in the draw-call stepper. Not the pylon shot, not
the tutorial. **If the attract does not reach it before the run ends, say so
rather than reporting on a different scene** — scene identity has been wrong
twice from sampling (A93, A161) and both times the observation was right and
the quantifier wrong.

**Why it is worth your eyes.** In the offline reconstruction that shot leaves a
region blank in the **top left** where every other attract frame is filled.
Task 2400 draws its sky as ordinary geometry; **this one apparently does not.**
The reconstruction cannot settle it, because it draws triangles only and
**ignores `G_TEXRECT` entirely — 18-20 of them per frame** — which is how N64
games usually paint a sky.

**So the question is precisely:**

* **Is there a sky in that shot at all** on screen, or is that region flat
  black / a solid colour?
* If there IS a sky — does it look **correct**, or wrong in some way (banding,
  a stuck frame, a repeated strip, the wrong colour)?
* Does it **move with the camera**, or sit fixed on screen?

**A "there is obviously a sky and it looks fine" is a real and useful answer**
— it would mean the blank is purely my renderer's blind spot and nothing is
wrong with the game there. Please do not hunt for a defect to report.

## 7. ~~THE ~12 SECONDS BEFORE THE TUTORIAL~~ — ANSWERED 2026-08-29, RETIRED

**It is the TITLE SCREEN** (A685). The 罪と罰 card, © 2000 Nintendo. It submits
no geometry to the draw gate and touches no scenery table **because it is 2D**,
which is the correct behaviour and not a fault.

**The user answered "didn't notice anything" and was right.** I recorded that as
a weak negative when it was simply correct — and the answer was already sitting
in a recording I had. **I asked a person before I looked at my own video.** The
lesson is the ordering, not the outcome: a question that a frame can answer
should never be spent on the user's attention.

## 6. GENERAL FEEL — the things no scalar catches

* **Frame rate**: smooth, or stuttering/slideshow?
* **Input**: does pressing START visibly do anything?
* Anything that simply **looks wrong** and is not on this list. This line is the
  most valuable one here — the list encodes what I already expect, and what I
  already expect is exactly where I am least likely to be surprised.

---

# WHAT COUNTS AS PROGRESS

Any of these means **stop and tell me**, because several ledger entries assume
the opposite:

* the picture **gets past ~205–213 s** without freezing, or freezes somewhere new
* the freeze **resolves on its own** and play continues — the real game's
  tutorial pauses constantly and every one of its 78 pauses resumes (A451)
* a **scene we have never seen** appears
* **the sound and the picture come apart**, or having come apart, come back
* anything **actually crashes** — it stopped doing that, so a crash is now news

~~* it gets past ~158s without dying / the crash moves / audio starts working~~
**— RETIRED 2026-08-27 with section 4, same reason: the crash framing is dead
(A450/A451) and the audio has worked since A447. Criteria that can never fire
make the list feel complete while checking nothing.**

# IF YOU DISAGREE WITH SOMETHING I HAVE WRITTEN

Say so plainly, and **the disagreement gets recorded as a finding, not as a
correction to be quietly absorbed.** Both previous times you caught a scene
error, the useful part was not the fix — it was that the *class* of error
(quantifier too broad) became visible. That only happens if the disagreement is
written down as its own entry.

# IF YOU CANNOT SAY WHERE — POINT AT IT INSTEAD (T150, wired 2026-08-29)

**Every recorded run now has an ELAN project sitting beside it**, generated by
`scripts/eaf_make.py` with the video AND the game-only audio both linked, and
two empty tiers: **faults** and **scene identity**. Open the `.eaf` next to the
`.mp4` in the evidence folder for that date.

**Why this is here.** A description like *"something looked off in the attract"*
costs a round trip: I have to guess which shot, and guessing scene identity is
the error this project has made twice (A93, A161). **A mark on a timeline costs
you a keystroke and costs me nothing** — `TIME_ORDER` in the saved file gives me
the exact millisecond, so I can pull the frame.

**It is the file you get by hitting SAVE.** Not an export (T150, your
correction 2026-08-22). The tiers arrive EMPTY on purpose — a pre-filled marker
would be an answer key, and A383 measured your labels disagreeing with a
unanimous machine consensus on 3 of 5 entries, so showing you my expectation
would destroy the only independent reading we get.

**You are never obliged to.** Prose is fine and always has been. This exists for
the case where you know something is wrong and the words are the hard part.

# AFTER THE RUN

`scripts/observed_run.sh` appends a dated stanza to `docs/observed-runs.md` with
the build hash and your answers, and saves a **game-only** audio capture beside
the video. **A run with no recorded outcome did not
happen** — same rule as the ledger: recorded either way, including "everything
looked exactly as expected", which is itself evidence.
