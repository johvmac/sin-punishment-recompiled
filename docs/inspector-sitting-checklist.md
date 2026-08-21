# F1 / RT64 inspector sitting — run sheet

**Version 2, 2026-08-22.** Replaces v1 entirely. v1's first step crashed the
game (A310) and is gone, not struck out — a sheet read at speed should not
contain instructions you must remember not to follow.

**Build `53a41b75`** (START moved off ENTER, T152). Runs before 08:34 today were
on `c14b30b5`.

**TWO RUNS, IN THIS ORDER.** Run 1 is safe and carries the highest-value
question. Run 2 is the hazardous one and comes second on purpose.

---

## The rule that replaced v1's step 1

**NEVER TOUCH `View Framebuffer`.** Setting it to 0 in the tutorial killed the
run instantly on 2026-08-22. The slider value sizes an unclamped loop over the
frame's framebuffer pairs, and **index 1 is not known to be safer — it forces
two iterations rather than one.** The depth buffer is not reachable this way.
`View Draw Call` is a different control and is the one we want.

---

# RUN 1 — Xephyr, no panel, ~4 min. **The control arm.**

**CLEAR THE PROMPT LINE FIRST — press Ctrl-U, or Enter on an empty line.** On
2026-08-22 the previous command was still sitting unexecuted on the line and the
next one pasted onto its end, fusing two tokens into a nonsense path and sending
the run to the real display (A312). `run_game.sh` now refuses the result, but
the cheap habit is to start from an empty line.

```bash
scripts/run_game.sh 240 /media/joh/extra/sin-punishment-archive/evidence/2026-08-22/warp-xephyr.log SNP_ISO=xephyr
```

Windowed, input isolated, **and recorded** — so this run produces a video I can
check against your eyes.

**DO NOT PRESS F1. DO NOT PRESS ANYTHING.** Just watch.

## What to watch for, in two specific places

1. **The attract soldiers** — the ones you reported still warping.
2. **The room with three characters together, shortly before the gun-spinning
   shot** (that shot is just before the start screen). This is the scene you
   reported for the first time today and nobody has ever looked for.

**OBSERVE, for each:** warping present or absent, and if present, how strong.
You described it as *"a LITTLE like Z-fighting but much more dramatic"* — say
whether what you see here matches that, is milder, or is absent.

> **Please answer this run on its own terms.** You already suspect warping is
> absent in this mode, and it would be easy to see what we expect. "Absent" and
> "present" are equally good answers and the second one is more interesting,
> because it would kill the display-mode theory cheaply.

---

# RUN 2 — real display, ~4 min. **Hazardous. Panel work.**

```bash
scripts/run_game.sh 240 /media/joh/extra/sin-punishment-archive/evidence/2026-08-22/inspector-drawcall.log SNP_VISIBLE=1
```

`SNP_VISIBLE=1` **at the end, as an argument** — not as a shell prefix, or the
run log records the wrong mode (A310). **Nothing is recorded in real mode by
design, so your description is the only evidence that will exist.**

## Timeline

| t | what | you |
|---|---|---|
| 0–155 s | attract | **PANEL CLOSED.** Watch the same two scenes as run 1 |
| ~155 s | tutorial starts | **press F1 now** |
| 155–208 s | **~53 s of working time** | steps 2 and 3 |
| ~208 s+ | submission stalls | **F1 is dead past here** |

## Hard rules — each cost a dead run

1. **PANEL CLOSED THROUGH THE ATTRACT.** Three runs with it open died at
   37/70/88 s; closed reached 190 s (A288). One had *zero* input, so this is not
   about the keyboard.
2. **NEVER `View Framebuffer`.** See above.
3. **DO NOT PAUSE. DO NOT CLICK RESUME.** Resume has killed three runs.
4. **DRAG, DO NOT TYPE.** START is now INSERT rather than ENTER (T152), so the
   old ENTER trap should be gone — but that remap is **not yet confirmed**, so
   behave as if it were still armed.
5. **ARROW KEYS DO NOTHING AND THAT IS NOT YOUR FAULT** — ImGui keyboard nav is
   off entirely in RT64. Do not retry.
6. **WRITE EACH ANSWER DOWN BEFORE THE NEXT CONTROL.** The run may die at any
   moment. An answer in your head when it dies is a step that did not happen.

## STEP 0 — during the attract, one keypress (T152)

**Press ENTER once. Nothing should happen.** That confirms START is off ENTER.

**Do NOT press INSERT this run** — INSERT is START now, and it would skip the
attract and cost you the warping observation.

## STEP 1 — the attract, panel shut. **The positive arm.**

Same two scenes as run 1: the soldiers, and the three-character room before the
gun spinning. **Present or absent, and how strong compared to run 1.**

## STEP 2 — read two labels. Five seconds, no risk, settles an open question.

Open F1 at ~155 s. Before touching anything, read the **labels**:

* `View Framebuffer` — reads −1 to ___   *(read it, do not drag it)*
* `View Draw Call` — reads −1 to ___

Last sitting a slider offered only −1, 0, 1 and we assumed it was the draw-call
one — but that is exactly `View Framebuffer`'s range in the tutorial, and nobody
recorded which was under the cursor (A309). **If `View Draw Call` runs to ~230,
the "pausing collapses the workload" finding loses its only instance.**

## STEP 3 — `View Draw Call`, climbing. U2 then U3, one control.

This slider **truncates**: it renders only the first N draw calls, so the frame
builds up as you climb. It worked before — A245 scanned to ~164 of 256.

**3a (U2) — low indexes.** Drag to 0, then 1, then climb slowly to about 5.
Exact 0 is one pixel wide; **anything up to ~5 answers this. Do not fight it.**

> On a frame showing the multiplied overlay clutter: do the duplicate copies
> appear **one per index** as you climb — or is the truncated frame **CLEAN of
> duplicates at every index**?

Clean means the residue lives in the buffer, not the submitted list (A247
predicts this). Copies per index would reopen A219.

**3b (U3) — sweep, do not step.** 50, 100, 150, 200, then the top.

> At which index, if any, does **background scenery** appear behind the
> character and the two pylons — and what do the last few indexes add?

The tutorial submits *more* triangles than the attract that renders correctly
(A263), yet shows a character, two pylons and black. Background appearing at
some index → it is drawn and lost downstream. Never appearing → it goes
off-screen or is discarded. **Different fixes, and nothing currently separates
them** — this is the only route left to that question now that the depth-buffer
route is dead.

## STEP 4 — only with spare time. Produces no evidence.

Press **F3** and describe what changes. Non-citable until its semantics are read.

---

## If it dies

Expected. Note **when** and **what you had just touched** — that is data on a
hazard that now has one confirmed trigger and several unconfirmed ones.

## What to tell me

1. **Run 1 (Xephyr): warping in the soldiers? In the three-character room?**
2. **Run 2 (real): the same two, and how they compare to run 1.**
3. Did ENTER do nothing?
4. The two slider labels and their ranges.
5. Draw call 0–5: duplicates per index, or clean?
6. The sweep: any background, and at what index?
7. **Anything contradicting what I have claimed.** It becomes its own entry,
   never a quiet correction.

**"I could not tell" and "I did not get to it" are real answers.** A guess
recorded as an observation is worse than a gap.
