# F1 / RT64 inspector sitting — run sheet

**Version 3, 2026-08-25. Replaces v2 entirely.** v2's two runs were about the
`View Draw Call` slider and the warping question; **both have since been
answered** — A332 (the user, at the panel) falsified A316's residue reading, and
the picture kept animating at every slider setting. A sheet read at speed must
not contain steps whose question is already closed.

**THE ONE QUESTION THIS SITTING EXISTS FOR:** is the missing scenery **drawn
black**, or **never drawn at all**? Geometry rasterised in black still writes
depth. Depth does not care what colour something wrote. **One checkbox
separates two causes that need completely different fixes** — and A274 left
them indistinguishable because both write zero colour.

---

## READ THIS FIRST — the route was a SIGSEGV until today

**`View Depth Buffer` is `ImGui::BeginDisabled(framebufferIndex < 0)`.** It
cannot be ticked until `View Framebuffer` is moved off −1 — and moving it to 0
is what **killed a run 11 s into the tutorial on 2026-08-22 (A310)**.

The loop that did it sized itself from the slider with no clamp against the
workload actually being rendered. **That is now clamped** (`rt64_workload_queue.cpp`,
2026-08-25). The `framebufferIndex < 0` path is unchanged, so ordinary runs
cannot be affected.

> **THE CLAMP IS UNVERIFIED AND YOUR RUN IS ITS FIRST TEST.** F1 does nothing
> under Xvfb or Xephyr (A245), so the panel cannot be exercised headless — there
> is no way for me to prove this works before you click. **A headless
> non-perturbation run confirms only that normal rendering is unchanged.** If it
> still dies at step 3, that is a real result and the answer is a backtrace, not
> another attempt.

---

## Pre-flight — I do these on your word, before you touch anything

| # | check | why |
|---|---|---|
| 1 | build is the clamped one, snapshot label `FBCLAMP` | v2's sheet named a build three days stale |
| 2 | `developer_mode: true` in `graphics.json` | no panel without it. **Currently true** |
| 3 | **restore `graphics.json` from `.bak-2026-08-25`** | this session set it to 240p `Original` for an unrelated experiment and you said it is *"stretched as all heck"*. **A stretched image is a confound in a sitting whose entire output is your description.** Say if you would rather keep it |
| 4 | no stray `Xvfb` / `Xephyr` / game processes — **`ps -eo comm= \| grep -c '^SinPunishmentRe'`** | **NOT `pgrep -x`**: the binary name is 23 chars against `comm`'s 15-char cap, so `-x` reports 0 unconditionally (T13, 2026-08-18; re-learned T204) |
| 5 | headless non-perturbation run reaches the canonical stall (6169 tasks) | proves the clamp did not change ordinary rendering |

---

# THE RUN — real display, ~4 minutes of your time

**Clear the prompt line first (Ctrl-U).** On 2026-08-22 a leftover command fused
with the next one and sent a run to the real display (A312).

```bash
scripts/run_game.sh 240 /media/joh/extra/sin-punishment-archive/evidence/2026-08-25/inspector-depth.log SNP_VISIBLE=1
```

`SNP_VISIBLE=1` **at the end, as an argument** — not as a shell prefix, or the
run log records the wrong mode (A310, fixed at source but the habit stands).
**Nothing is recorded in real mode by design (T59), so your description is the
only evidence that will exist.**

## Timeline

| t | what | you |
|---|---|---|
| 0–155 s | attract | **PANEL CLOSED.** Do not press F1 |
| ~155 s | tutorial starts | **press F1 now** |
| 155–208 s | **~53 s of working time** | steps 1–3 below |
| ~208 s+ | submission stalls | panel is dead past here |

**Why the panel stays closed through the attract:** open-through-attract killed
three runs at 37 / 70 / 88 s (A288); opened AT the tutorial, runs completed
normally (A316, A289 to 190 s). 3 deaths against 2 survivals — a pattern, not a
rule, so it is worth obeying and not worth trusting.

## The three steps

1. **Press F1** once the tutorial is up.
2. **DRAG `View Framebuffer` from −1 to 0.** Drag it. **Never type.** Ctrl+Click
   opens text entry which commits on ENTER, and ENTER is bound to START — that
   skipped the attract and SIGSEGVed two runs (T134). **This is the step that
   used to crash.** If the game dies here, stop; say so, and we take a backtrace
   next time rather than retrying.
3. **Tick `View Depth Buffer`.**

## What I need you to tell me — and it is one thing

**In the region that is BLACK in the normal view, does the depth buffer show a
silhouette — shapes, edges, a gradient — or is it flat/empty there?**

* **Silhouette present** → the geometry IS being rasterised and IS writing
  depth. It is drawn, in black. That points at combiner / texture / lighting,
  and it means every "missing geometry" theory is wrong.
* **Flat or empty** → nothing is being rasterised there at all. That points at
  geometry, culling or transform.

Either answer closes half the search. **Say which you see, not which you
expected** — and if it is ambiguous, say ambiguous, because a hedged true answer
is worth more than a confident guess.

## Hard rules — each one cost a dead run

* **NEVER type into any field.** Drag only. (T134)
* **NEVER click `Resume`.** It killed three runs.
* **Arrow keys do nothing** — `NavEnableKeyboard` is never set.
* **Do not reopen the panel if you close it.**

## If there is spare time (only if steps 1–3 went cleanly)

**U6, low priority, produces no evidence:** press **F3** (`ViewRDRAM`) and
describe what appears. Exploratory only — nothing is blocked on it.
