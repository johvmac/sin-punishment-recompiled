# Schedule

**These are the things that do not happen unless they are scheduled.** The
root-cause investigation is the *default* activity — it needs no slot, because
it is what a session does when nothing else is due. Upstreaming, triage and
writeups are the ones that quietly never get done, so they get dates.

One item per day, deliberately. Each should fit in well under an hour alongside
the main work.

Format is parsed by `scripts/route.py`, which prints anything due or overdue at
each checkpoint. Tick the box when done.

- [x] **2026-08-19** — **Upstream PR 1**: `N64ModernRuntime-vi-null-mode-fix`.
      **DONE, but as an ISSUE, not a PR** —
      <https://github.com/N64Recomp/N64ModernRuntime/issues/154>. Repro was
      gathered as specified (3 runs per arm, fault measured at
      `comRegs.hStart`; see **L8**), then upstream's `CONTRIBUTING.md` turned
      out to **prohibit AI-generated code contributions** (**T36**), so it was
      filed as a bug report with no patch and an explicit disclosure.
      **Nothing further is owed on this item.**
- [x] **2026-08-20** — **A26 — DONE EARLY, 2026-08-19** (it became a prerequisite for the A99 frontier, see T42). Was: add the `.main` segment to `tsumitobatsu.yaml` **in the sibling splat repo `/home/joh/Documents/sin_and_punishment/splat-project/` — it is NOT in this repo (T19)**
      (ROM `0x3E850`, vram `0x800A7070`, size `0x2EA00`). Verify the existing
      `asm/` files come back byte-identical **before** relying on anything, then
      confirm `scripts/decomp.sh main_func_800B4CE8` works. ~620 functions of
      mid-level engine become readable; this blind spot already caused one
      confidently wrong conclusion.
- [x] **2026-08-21** — **DONE 2026-08-25 (roll #246), see A419.** Step 2 ran as
      specified — bounded, top-of-list first, hit rate recorded — but **not
      against splat's `endlabel`**, because A259/A281 established splat is
      guessing at these boundaries and A292 showed the ROM answers directly.
      **106 candidates outside `ovlfile12`, all classified: 92 CONTINUATION
      (87%), 3 SEPARATE, 6 UNCLEAR, 2 NO-CODE, 3 PADDING.** `truncation_sweep.py`,
      reading the generated C instead of the ROM, independently flags 81 of the
      92 and **none** of the 14 non-hits. **WHAT IS STILL OWED: exactly one of
      the 92 has a proven extent (A292, by hand). The rest are a lead list, and
      each needs its own read before a `size` is edited.** New tool
      `scripts/gap_classify.py`, three gates met.
      **AND THEN A420 (roll #247) TOOK THE VALUE BACK OUT: only 1 of the 92 is
      in a section that demonstrably loads, and it loses no drawing commands.
      Do NOT spend a slot editing these sizes — on the route we can reach they
      would change nothing.** Reopen only for a level that loads those overlays,
      or if the unsegmented compressed third is ever brought in.
      **T11 triage, RE-PLANNED 2026-08-19 (roll #36).**
      "Top 20 gaps by size" is the WRONG plan: **13 of the top 20 are
      `.ovlfile12`**, which would burn the whole budget re-deriving one
      structural fact. Run `scripts/symbol_gaps.py` first, then do these as
      **two separate questions**:
      1. ~~**Is `ovlfile12` ever loaded at runtime?**~~ **ANSWERED 2026-08-19
         (roll #58) — NO, over three runs including two that reach a fresh
         scene load at ~158s, with a positive control and a size-based check
         that does not depend on its ROM offset. See T11 (now closed) and A127.
         So step 1 is DONE and most of T11 did evaporate: file12's 67
         candidates are the LOWEST priority.** Step 2 below is the whole of
         what remains.
      2. **Triage the ~106 candidates OUTSIDE `ovlfile12`**, top-of-list first,
         each checked against splat's `endlabel`. Fix only genuine truncations
         (the L1/L7 class). Bounded: stop at 20 checked, record the hit rate.
      *(moved up from 08-22 when PR 2 was closed.)*

      > **NOT STARTED ON 2026-08-21, AND ITS BLOCKER HAS SINCE CLEARED.**
      > A258-A261 showed this is harder than the plan assumes and A262 was named
      > the prerequisite. **A262 was ANSWERED on 2026-08-21 by A292**, which
      > found one exit in 1,240 bytes of ovlfile07's own ROM and put the true
      > boundary at `0x518` rather than the declared `0x40` — by static proof,
      > overturning A149's refutation of A96. **So the prerequisite is met and
      > this is startable.** Note A261's warning before writing any checker for
      > it: four controls that are all truncation-flagged-or-not are ONE
      > control; vary the failure MODE.
- [x] **2026-08-21** — **CLOSED 2026-08-25 (roll #257, witness `2d5de0`). All
      five measurements are accounted for and NONE OF THE REMAINING ONES NEEDS
      THE PANEL, which is the point — the item was overdue for four days
      because every route into it required the user at a real display, and
      three of the five have since been answered by instruments that do not.**
      * **1 (frame stats) — DONE 2026-08-21, A285.**
      * **3 (View Depth Buffer) — DONE 2026-08-25, A421.** It was the highest-
        value item here and it was blocked by a crash of my own prescribing
        (A310); T203 clamped the unchecked loop, the user drove the slider to
        0 and to 1 with no crash, and the depth buffer was read for the first
        time on this project.
      * **4 (draw-call slider) — ANSWERED OFFLINE, A437.** The replay draws the
        submitted list into an EMPTY image, so a duplicate seen there cannot be
        residue — the one thing the slider could never rule out. Queue row U2
        is swept.
      * **5 (texture dump) — DONE 2026-08-21, A286** (queue row U4).
      * **2 (free camera) — NOT DONE, AND IT NO LONGER HAS ANYTHING TO FIND.**
        Its whole purpose was to separate *drawn off-screen* from *not drawn*.
        **A422 removed that question**: the scenery is absent from lists walked
        to `stop=end`, so there is nothing off-screen to fly to. **Do not
        re-queue it for A218.** It would become worth having again only for a
        scene whose geometry IS submitted and still invisible.
      **WHAT REMAINS ON THE PANEL IS U6 ONLY**, which this list's own status
      block marks LOW PRIORITY and PRODUCES NO EVIDENCE. **Do not re-open this
      item to run it.**
      *(User-requested 2026-08-20; sequenced AFTER the T11 triage above.)*
      **Setup is already done and verified** — `developer_mode` is `true` in
      `~/.config/sinpunishment/graphics.json` (backup at `.pre-devmode.bak`),
      a run with it on is CLEAN, and the census output is **identical over 400
      tasks** with it on versus off, so it does not perturb what is measured.
      145 `RT64::DebuggerInspector::*` symbols are in the binary including
      `enableFreeCamera` and `highlightDrawCall`. **The one thing NOT verified
      is that F1 opens the panel** — that needs a keypress into a deliberately
      input-isolated window, so it is the first ten seconds of this task.

      Run it visible: `SNP_ISO=xephyr scripts/run_game.sh 240 <log>`, get to the
      tutorial (~155 s), press **F1**. **THIS IS A USER-DRIVEN INSTRUMENT — I
      cannot click an ImGui panel.** Three measurements, in this order:

      1. **Frame stats → triangle count.** Cross-check against the census:
         ~525 `G_TRI2` + 32 `G_TRI1` ≈ **1,082 triangles/frame** submitted
         (A234). Two instruments on opposite sides of the renderer measuring
         the same quantity — **if they disagree, that is the finding**, and
         nothing below should be trusted until it is understood.
      2. **Free Camera → fly away from the origin.** Separates *drawn
         off-screen* from *not drawn*. If the city geometry is sitting outside
         the viewport, this is the only tool we have that finds it.
      3. **View Depth Buffer.** Separates *drawn black* from *not drawn* —
         geometry rasterised in black still writes depth, so a background
         silhouette in the depth buffer means a combiner/texture/lighting
         fault, not a geometry one.

      > **STATUS AT END OF 2026-08-21 — PART DONE, NOT TICKED. Read this before
      > re-running any of it.** The user sat through several attempts.
      > * **F1 works, but ONLY on a REAL display** — it does nothing under Xvfb
      >   or Xephyr, so the line above suggesting `SNP_ISO=xephyr` is WRONG.
      >   Use `SNP_VISIBLE=1`. **Nothing is recorded in real mode by design
      >   (T59), so the user's description is the only evidence.**
      > * **THE PANEL IS A HAZARD (A288):** three runs with it open died at
      >   37 / 70 / 88 s; keeping it CLOSED through the attract reached 190 s.
      >   Clicking **Resume** killed three runs. **Ctrl+Click text entry commits
      >   on ENTER, and ENTER is bound to START** — that skipped the attract and
      >   SIGSEGVed two runs (T134). **Drag the slider, never type.** Arrow keys
      >   cannot work (`NavEnableKeyboard` is never set).
      > * **1 (frame stats) — DONE**, → A285: draw calls 234/231/249/232 and
      >   triangles 1246/1244/1377/1242 across the tutorial, framebuffer pairs
      >   4→5 in attract, 1 on the start screen, 2 in the tutorial. A290/A293/
      >   A296 corroborate the pair counts from the census, independently.
      > * **4 (draw-call slider) — ATTEMPTED, INCONCLUSIVE.** From a paused
      >   tutorial frame the slider would only take −1, 0, 1; unpausing crashed
      >   the run. **But an earlier paused run DID allow scanning hundreds of
      >   draw calls (A245, ~164 of 256), so pausing is UNRELIABLE rather than
      >   useless, and nothing yet predicts which behaviour you get.**
      > * **3 (View Depth Buffer) — NOT DONE, and it is now the highest-value
      >   item on this list** (A289). A274 left "drawn black" and "never drawn"
      >   indistinguishable because both write zero colour; **depth does not
      >   care what colour something wrote.** One checkbox, not a 234-step
      >   sweep.
      > * **2 (free camera) — NOT DONE. 5 (texture dump) — the user located the
      >   button; no output has been confirmed.**
      > These live in `scripts/user_queue.py` as U2/U3/U6/U7 — **work the queue,
      > not this list**, so one sitting clears several.

      **Caution (T88 family):** this shows RT64's interpretation of the list,
      so it is authoritative for presence, identity and "is this geometry
      anywhere", and NOT for pixel-accuracy claims.

      **TWO MORE, added by the A243 survey — 4 is the highest-value item here:**

      4. **"View Draw Call" TRUNCATES, it does not highlight** — it renders
         only the first N draw calls, so the frame builds up one draw at a
         time. **Step it through a tutorial frame and watch when duplicate
         overlay elements appear.** If each copy arrives at its own draw call
         they are separately submitted; if a whole cluster arrives at ONE call
         they are not. A235 measured the submitted list flat, which predicts
         the second. **This settles A219's mechanism by eye in one paused
         frame** — do this before anything else if time is short.
      5. **"Start dumping textures"** (a button in the inspector) writes every
         unique texture the game loads to a directory, keyed by hash. Start it
         and let a run play through the tutorial — it gives you real assets to
         look through with nothing built. **It is NOT A227**: it captures what
         is USED, not what is PACKED, textures only, and only from the stretch
         we can reach.
- [x] **2026-08-22** — **DONE, see A327.** `SNP_POKE=0xADDR:0xVALUE[:size][,...]`
      lands in `ultramodern/src/events.cpp`, applied **every VI** from
      `vi_thread_func`. All three gates met, and the every-frame requirement
      turned out to be load-bearing rather than cautious: the game clobbers
      `0x80075DD6` three times during startup before our value sticks, so the
      one-shot fallback the item allowed for would have been overwritten and
      would have read as "the cheat does nothing".
      **The control discriminates the `^3` byte swizzle, not merely the write.**
      **STILL OWED FROM THIS ITEM — the optional "free win" was NOT done:**
      watching `0x800D5A9B` (energy/time, fixed across levels) for an
      "are we actually in a level yet?" signal, which T143 found the Mischief
      Makers harness waits on instead of sleeping. It needs no new code — the
      read facility already exists — so it is cheap whenever it is wanted.
      **Input scripting was deliberately NOT built; it is the next item.**

      **FIRST THING: a memory-poke facility, so the cheat
      codes can be used.** *(User-requested 2026-08-21 evening, deferred from
      that night explicitly.)*

      **WHY THIS AND NOT "BUILD THE DEBUG MENU":** T145 established the gap.
      We have `0x80075DD6` (**unlock levels**) from the libretro `(J)` set, and
      T5 confirms these are KSEG0 and usable verbatim. What we do **not** have
      is any way to WRITE to RDRAM — `SNP_WATCH` samples, `rdram_peek.py` reads
      a snapshot, and a grep of the runtime for a poke returns nothing. **Until
      a write exists, no cheat is usable and nothing else on this path can
      start.** That is why this is the item rather than the menu.

      **Bounded to the poke alone.** Do NOT also build input scripting in this
      slot; it is the next item, not this one.

      1. `SNP_POKE=0xADDR:0xVALUE[:size][,...]`, applied **every frame, not
         once** — a real cheat device re-applies continuously, and a one-shot
         write at startup is very likely to be overwritten by the game's own
         save/load. If it must be one-shot to start with, say so in the entry.
      2. **T71's three gates before its output is evidence:** a dry run that
         prints the writes it *would* make and exits; a control **verified to
         FAIL**, not merely to pass — the obvious one is poke-then-read-back
         through `SNP_WATCH` at the same address, which must report the new
         value and must report the OLD value when the poke is disabled; and a
         playbook write-up plus a Tool-inventory row in the same checkpoint.
      3. **CONTAMINATED BY DESIGN**, exactly like `send_key.py`. Any run using
         it is usable for *reaching a scene* and must **never** be cited as
         evidence of normal behaviour. Say so in the tool's own `--help`.

      **Free win available with the READ facility we already have, if there is
      time:** `0x800D5A9B` (energy/time) is **fixed across all levels**, so
      watching it gives an "are we actually in a level yet?" signal — which is
      what T143 found the Mischief Makers harness waits on instead of sleeping.
      Worth having regardless of whether the poke lands.

*(Nothing else scheduled. The two remaining upstream slots were removed —
see "Closed without doing" below.)*

## Closed without doing — kept so they are not re-derived

- **ALL remaining upstreaming (PR 3 / `pif-raw-si-responder`, and the RSP
  `SIG0` issue), was 2026-08-22 and 08-23. Closed 2026-08-19 (T38).**
  Upstream's reply to #154 asked us to **refrain from submitting AI-generated
  issue reports**, so the issue route that T36 had left open is closed too.
  Filing either would contradict an explicit request from the person who would
  have to read it. **Do not reopen these by finding a cleverer framing** — the
  constraint is not about format, it is that the work is AI-assisted.
  The patches stay in `patches/upstream/` and keep working locally.

- **Upstream PR 2** (`RecompFrontend-keyboard-defaults`), was 2026-08-21.
  **Closed 2026-08-19, not deferred.** Two independent reasons, either
  sufficient: (a) `RecompFrontend` carries the same org-wide policy prohibiting
  AI-generated code contributions (**T36**), so the 72-line patch cannot be
  submitted as code; and (b) unlike #154 there is **no bug to report instead** —
  keyboard defaults are a preference, and the original 2026-08-18 assessment
  already suspected some of those lines were *this project's* preference rather
  than a sensible default. So there is no issue-shaped residue either.
  **The patch stays in `patches/upstream/` and keeps working locally.**
  **Reopen only if** upstream changes the policy, or someone shows a default
  that is actually broken rather than merely not-our-taste.

## Recurring

- **Daily 18:30** — `scripts/daily_push.sh` via cron. Automatic; no action
  needed unless it reports a refusal.
- **Every checkpoint** — `scripts/route.py` for the explore/exploit roll, which
  also surfaces anything due here.

## Not yet scheduled

The writeups (START crash, methodology) and the README rewrite are gated on
closing the current root cause. A half-finished investigation reads worse than
no writeup. See `ROADMAP.md`.
