# F1 / RT64 inspector sitting — run sheet

**Version 1, 2026-08-22.** Everything here is measured, and each rule cost a
dead run. Read it before launching, not during — **the working window is about
53 seconds** and there is no time to look anything up inside it.

Queue items this clears: **U9, U2, U3, U6.** Do them in that order.

---

## The one command

```bash
scripts/run_game.sh 240 /media/joh/extra/sin-punishment-archive/evidence/2026-08-22/inspector-depth.log SNP_VISIBLE=1
```

**`SNP_VISIBLE=1` GOES AT THE END, AS AN ARGUMENT — not as a shell prefix.**
Version 1 of this sheet used the prefix form. It works, but the run log records
its env column from the ARGUMENTS, so the run was written down as headless and
the changed-signature alarm called a user-triggered crash "a HEADLESS SIGSEGV
... a regression" (A310). `run_game.sh` now records the resolved mode either
way, and the argument form is still the one to use.

**Real display, never `xephyr`.** F1 does nothing under Xvfb or Xephyr
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
   ENTER. **START HAS BEEN MOVED OFF ENTER ONTO INSERT (T152)** so this is no
   longer the hazard it was — but typing in the panel is still worth avoiding,
   and **the remap is not yet confirmed by a run.** If you must enter an exact
   value: Ctrl+Click, type, then **click elsewhere** to commit on focus loss.
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

## STEP 0 — one keypress, confirms the START remap (T152)

Any time after the window appears: **press ENTER once.** Nothing should happen.
Then **press INSERT once** — that is now START, so it will skip the attract, so
**only do the INSERT half if you are willing to lose the attract for this run.**
Skipping ENTER-does-nothing is fine; skipping it means the remap stays unverified.

---

## STEP 1 — U9, the depth buffer. **REMOVED — IT CRASHES THE GAME**

**DO NOT DO THIS.** Attempted 2026-08-22: setting `View Framebuffer` to 0 in
the tutorial killed the run instantly (`rc=139` at 166 s). The slider value
sizes an unclamped loop over the frame's framebuffer pairs, and 0 forces one
iteration unconditionally — index 1 is not known to be safer, it forces two.
**The depth buffer is not currently reachable this way. Skip to STEP 2.**
The old instructions are struck out below for the record only.

<details><summary>the instruction that crashed it — do not follow</summary>

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

**What it would have meant:** a silhouette means the geometry *is* being
rasterised and lost in colour; flat depth means nothing was ever drawn there.
Both write zero colour and are indistinguishable in a frame grab (A274).

</details>

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
2. Did ENTER do nothing, and did INSERT start the game? (STEP 0)
3. The two slider labels and their ranges.
4. Draw call 0–5: duplicates per index, or clean?
5. Anything from the sweep, if you got there.
6. **Anything that contradicts what I have claimed.** It becomes its own ledger
   entry, never a quiet correction.

**"I could not tell" and "I did not get to it" are real answers.** A guess
recorded as an observation is worse than a gap, and this list is already longer
than 53 seconds comfortably holds.
