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
* **CLIPPING — the one measured worry.** The capture peaks at full scale
  (A447), which can mean audible crackle/distortion on loud passages. Listen
  for harshness where the music gets busy. "Loud but clean" and "crackles when
  loud" are different findings; say which.
* **Stutter, dropouts, wrong pitch, one channel only** — any of the classic
  stream failures.
* **Does it survive the whole run** — through the attract, past START, into
  the tutorial, up to the stall?

> Why it matters: A97 is held open ONLY for this verdict. "Sounded right
> throughout" closes a 25-day investigation; any defect you can name becomes
> its first sharp follow-up. Either answer is a real result.

## 2. THE LAST TEN SECONDS BEFORE IT DIES — the scene is formally unidentified

* **What is on screen in the final ~10 seconds?** Name it in your own words.
* **Does the screen go FULLY black before the crash?** For roughly how long?
* Is it a **static screen, an animation, or a transition** between two things?
* Does anything visibly glitch, tear, or freeze *before* the death?

> Why it matters: A164 says ~10s of title screen ends at 157.2s, the screen goes
> fully black, and the crash lands at 158.2s — **but the scene at the fault is
> formally NOT ESTABLISHED**, and I have twice mislabelled scenes from samples.
> A name from you closes it.

## 3. THE TITLE SCREEN — I claim it is frame-for-frame correct

After a START press the title should render: green 罪と罰 / SIN AND PUNISHMENT
logo, プッシュ スタート, © 2000 Nintendo.

* Does it look **right**, or is anything **missing, mis-coloured, or in the
  wrong place**?
* Any **corruption**: missing layers, garbage pixels, wrong background.

> Why it matters: A162 claims our build draws it "matching the reference capture
> frame for frame". That is my comparison of stills. A "looks wrong to me"
> from you overrides it.

## 4. HOW IT DIES — a crash, a freeze and a clean exit look identical in a log

* Does it **vanish**, **freeze on a frame**, or **fade/exit tidily**?
* Roughly **when**? (expected: ~158s with no input, ~45–55s after START)
* Is the last frame **black**, or a frozen picture?

> Why it matters: the run log records a return code. It cannot tell a freeze
> from a crash, and that distinction has changed our diagnosis before.

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

* it **gets past ~158s** (or past ~55s post-START) **without dying**
* the crash moves to a **different time, function, or fault address**
* a **scene we have never seen** appears
* **audio starts working**
* the crash becomes a **freeze**, or vice versa

# IF YOU DISAGREE WITH SOMETHING I HAVE WRITTEN

Say so plainly, and **the disagreement gets recorded as a finding, not as a
correction to be quietly absorbed.** Both previous times you caught a scene
error, the useful part was not the fix — it was that the *class* of error
(quantifier too broad) became visible. That only happens if the disagreement is
written down as its own entry.

# AFTER THE RUN

`scripts/observed_run.sh` appends a dated stanza to `docs/observed-runs.md` with
the build hash and your answers, and saves a **game-only** audio capture beside
the video. **A run with no recorded outcome did not
happen** — same rule as the ledger: recorded either way, including "everything
looked exactly as expected", which is itself evidence.
