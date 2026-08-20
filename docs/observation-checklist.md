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

## 1. ⚑ AUDIO — highest value, and we have zero evidence of any kind

* **Is there ANY sound at all?** Music, sound effects, voice, menu blips.
* If there is sound: **is it correct, or is it damaged?** Buzzing, clicking,
  static, stuttering, wrong pitch, one channel only.
* **When does it start?** At boot, at the title, only in certain scenes?
* **Does it change or stop** at any point during the run?

> Why it matters: A97's current state is "audio silence only — the crash half
> was fixed". If you hear anything at all, that claim is wrong and A97 needs
> restating. If you hear silence, it is the first actual evidence for it.

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

## 5. GENERAL FEEL — the things no scalar catches

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
