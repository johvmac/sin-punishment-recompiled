# F1 / RT64 inspector sitting — run sheet

**Version 1, 2026-08-22.** Everything here is measured, and each rule cost a
dead run. Read it before launching, not during — **the working window is about
53 seconds** and there is no time to look anything up inside it.

Queue items this clears: **U9, U2, U3, U6.** Do them in that order.

---

## The one command

```bash
SNP_VISIBLE=1 scripts/run_game.sh 240 /media/joh/extra/sin-punishment-archive/evidence/2026-08-22/inspector-depth.log
```

**`SNP_VISIBLE=1`, never `xephyr`.** F1 does nothing under Xvfb or Xephyr
(A245) — this is the one task that must run on the real display.

**Nothing is recorded in real mode, by design (T59). Your description is the
only evidence that will exist.** Have somewhere to write.

---

## The timeline you are working against

| t | what | what you do |
|---|---|---|
| 0–155 s | attract sequence | **PANEL CLOSED.** Watch it (see below) |
| ~155 s | tutorial starts | **press F1 now** |
| 155–208 s | **the working window, ~53 s** | steps 1–5 |
| ~208 s+ | graphics submission stalls | **F1 is useless past here** — RT64 draws the panel during frame presentation, so once submission dies the panel opens nothing (T134) |

---

## Hard rules — each one killed a run

1. **KEEP THE PANEL CLOSED THROUGH THE ATTRACT.** Three runs with it open died
   at 37 / 70 / 88 s; keeping it closed reached 190 s (A288). One of those three
   had *zero* input, so this is not about the keyboard.
2. **DO NOT PAUSE. DO NOT CLICK RESUME.** Resume has killed three runs
   (A245 twice, A289 once). Every step below works on a running game.
3. **DRAG SLIDERS. NEVER TYPE.** Ctrl+Click opens a text box that commits on
   ENTER, and **ENTER is bound to the N64 START button** — it skipped the
   attract and SIGSEGVed two runs (T134). If you must enter an exact value:
   Ctrl+Click, type, then **click elsewhere** to commit on focus loss.
4. **ARROW KEYS DO NOT WORK, AND THAT IS NOT YOUR FAULT.** `NavEnableKeyboard`
   is never set in RT64, so ImGui keyboard navigation is off entirely. Do not
   retry it.
5. **F4 does not pause** — a global texture-replacement shortcut eats it. The
   panel has a Pause button that works, and rule 2 says do not use it.
6. **WRITE EACH ANSWER DOWN BEFORE MOVING TO THE NEXT CONTROL.** The run may
   die at any point. A step whose answer is in your head when it dies is a step
   that did not happen.

---

## While the attract plays (0–155 s) — free observation, costs nothing

You have two and a half minutes with nothing to do and the panel must stay shut.

**WATCH FOR MODEL WARPING.** You have reported warping in the attract that does
**not** appear in recordings, and three entries calling the logo window dark all
read recordings (A287's unresolved aside). This is a real display, so this is
the condition where it should show.

Say: **is it present at all this build**, which models, and roughly when.
"Not present anywhere in the attract" is a real answer — A246 names that as its
own falsifier.

---

## STEP 1 — U9, the depth buffer. **Highest value. Do it first.**

**It is TWO controls and the order matters** (A309). The checkbox is inside a
disabled block and its enabling control defaults to the disabling value, so
clicking the box first does nothing and looks broken.

1. Find **`View Framebuffer`** — a slider near the top of the panel.
2. **Drag it from −1 to 0.** In the tutorial it offers only **−1, 0, 1** — that
   is correct and not a fault (the tutorial uses 2 framebuffer pairs, A285).
3. **Now tick `View Depth Buffer`** — same row as that slider, immediately to
   its right. It only becomes clickable once step 2 is done.

**OBSERVE — this is the whole question:**

> Behind the character and the two pylons, where the environment should be:
> **is there a BACKGROUND SILHOUETTE in the depth view, or is that area FLAT?**

Then **drag `View Framebuffer` to 1** and say whether the two look different.

**What each answer means** (so you know why it matters, not so you decide it):
a silhouette means the geometry *is* being rasterised and is lost in colour — a
combiner, texture or lighting fault. Flat depth means nothing was ever drawn at
those pixels. Both currently write zero colour and are indistinguishable in a
frame grab (A274); depth does not care what colour something wrote.

---

## STEP 2 — read two labels. **Free, five seconds, settles an open question.**

There are two sliders near each other. Last sitting, one of them offered only
−1, 0, 1 and we assumed it was the draw-call one — but that is exactly
`View Framebuffer`'s range in the tutorial, and nobody recorded which was under
the cursor (A309 flags A289 on this).

**OBSERVE:** read the **labels** and report the range of each:

* `View Framebuffer` — reads −1 to ___
* `View Draw Call` — reads −1 to ___

If `View Draw Call` runs to ~230 or so, the "pausing collapses the workload"
finding loses its only instance.

---

## STEP 3 — U2, duplicate overlay clutter

On a tutorial frame showing the multiplied overlay clutter:

1. **Drag `View Draw Call` to 0, then 1.** Exact 0 is one pixel wide and easy
   to overshoot — **anything up to about 5 answers this just as well. Do not
   fight the slider.**
2. Climb slowly through the low indexes.

**OBSERVE:**

> Do the duplicate copies appear **one per index** as you climb — or is the
> truncated frame **CLEAN of duplicates at every index**?

Clean means the residue lives in the buffer, not in the submitted list (which
is what A247 predicts). Copies arriving per index would reopen A219.

---

## STEP 4 — U3, background sweep. **Only if the run is still alive.**

`View Draw Call` **truncates** — it renders the first N calls, so the frame
builds up. **Sweep, do not step:** 0, 50, 100, 150, 200, 232, then narrow
around anything that appears.

**OBSERVE:** at which index, if any, does **background scenery** appear behind
the character and pylons — and what do the last few indexes add?

**If STEP 1 gave a clear answer, this may be redundant. Say so and stop.**

---

## STEP 5 — U6, only with spare time. **Produces no evidence.**

Press **F3** (`ViewRDRAM`) on a tutorial frame and describe what changes.
Marked non-evidence deliberately: we know what the flag does to the present
path but not its exact semantics, so nothing from it can be cited yet.

---

## If it dies

Expected, not a failure of yours. Note **roughly when** and **what you had just
touched** — that is data about A288's hazard, which still has four candidate
triggers and only three data points.

---

## What to tell me afterwards

1. Attract warping — present or not, which models, roughly when.
2. **Depth view: silhouette or flat?** And did framebuffer 0 and 1 differ?
3. The two slider labels and their ranges.
4. Draw call 0–5: duplicates per index, or clean?
5. Anything from the sweep, if you got there.
6. **Anything that contradicts what I have claimed.** It becomes its own ledger
   entry, never a quiet correction.

**"I could not tell" and "I did not get to it" are real answers.** A guess
recorded as an observation is worse than a gap, and this list is already longer
than 53 seconds comfortably holds.
