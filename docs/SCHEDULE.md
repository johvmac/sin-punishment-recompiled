# Schedule

**These are the things that do not happen unless they are scheduled.** The
root-cause investigation is the *default* activity — it needs no slot, because
it is what a session does when nothing else is due. Upstreaming, triage and
writeups are the ones that quietly never get done, so they get dates.

One item per day, deliberately. Each should fit in well under an hour alongside
the main work.

Format is parsed by `scripts/route.py`, which prints anything due or overdue at
each checkpoint. Tick the box when done.

- [ ] **2026-08-19** — **Upstream PR 1**: `N64ModernRuntime-vi-null-mode-fix`.
      Reproduce first: revert the patch in `lib/N64ModernRuntime`, run, confirm
      the null dereference in `update_vi()`, restore. **Do not open the PR
      without a stated repro** — a maintainer should not have to take your word
      for a race. Then branch off upstream `main`, one commit, PR body =
      symptom / cause / fix / repro. Upstream is `N64Recomp/N64ModernRuntime`.
- [ ] **2026-08-20** — **A26**: add the `.main` segment to `tsumitobatsu.yaml` **in the sibling splat repo `/home/joh/Documents/sin_and_punishment/splat-project/` — it is NOT in this repo (T19)**
      (ROM `0x3E850`, vram `0x800A7070`, size `0x2EA00`). Verify the existing
      `asm/` files come back byte-identical **before** relying on anything, then
      confirm `scripts/decomp.sh main_func_800B4CE8` works. ~620 functions of
      mid-level engine become readable; this blind spot already caused one
      confidently wrong conclusion.
- [ ] **2026-08-21** — **Upstream PR 2**: `RecompFrontend-keyboard-defaults`.
      Read all 72 lines first and strip anything that is a *this project*
      preference rather than a sensible default.
- [ ] **2026-08-22** — **T11 triage**, bounded: take the **top 20** symbol gaps
      by size, check each against splat's `endlabel`, fix only genuine
      truncations. Do not attempt all 296; most are real data.
- [ ] **2026-08-23** — **Upstream PR 3**: `N64ModernRuntime-pif-raw-si-responder`
      (89 lines, the most substantial). Needs the clearest repro of the four.
- [ ] **2026-08-24** — **Upstream issue, not a PR**: RSP `SIG0`. Propose making
      `expected_c0_reg_value()` configurable per project. Submitting the current
      patch would change behaviour for **every** game to suit this one.

## Recurring

- **Daily 18:30** — `scripts/daily_push.sh` via cron. Automatic; no action
  needed unless it reports a refusal.
- **Every checkpoint** — `scripts/route.py` for the explore/exploit roll, which
  also surfaces anything due here.

## Not yet scheduled

The writeups (START crash, methodology) and the README rewrite are gated on
closing the current root cause. A half-finished investigation reads worse than
no writeup. See `ROADMAP.md`.
