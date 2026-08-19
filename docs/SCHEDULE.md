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
- [ ] **2026-08-21** — **T11 triage, RE-PLANNED 2026-08-19 (roll #36).**
      "Top 20 gaps by size" is the WRONG plan: **13 of the top 20 are
      `.ovlfile12`**, which would burn the whole budget re-deriving one
      structural fact. Run `scripts/symbol_gaps.py` first, then do these as
      **two separate questions**:
      1. **Is `ovlfile12` ever loaded at runtime?** (`scripts/overlay_map.py`.)
         It holds 84% of all unclaimed bytes and 46 of its 67 candidates have a
         declared size <= 0x10 — a symbol table that was never populated, not 67
         truncations. If it never loads, most of T11 evaporates. **Do this
         first; it is one check and it re-prices everything else.**
      2. **Triage the ~106 candidates OUTSIDE `ovlfile12`**, top-of-list first,
         each checked against splat's `endlabel`. Fix only genuine truncations
         (the L1/L7 class). Bounded: stop at 20 checked, record the hit rate.
      *(moved up from 08-22 when PR 2 was closed.)*
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
