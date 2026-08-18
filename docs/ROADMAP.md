# Roadmap

Ordered by what unblocks the most, not by size. Live technical questions live in
`findings-ledger.md` (the OPEN rows); this file is for work that is *scheduled*
rather than *being investigated*.

## Now — the one open root cause

**A66 — RESOLVED 2026-08-18.** ~~A triggered stack leak.~~ The premise was refuted (A67/A77) and the real cause found and fixed: a truncated symbol, `ovlfile20_func_800E5634` (L7, user-confirmed).

The graphics thread loses `0x18` bytes of stack per frame until it overruns the
table of per-frame function pointers; once that is corrupt the thread still wakes
on schedule, finds nothing to call, and stops drawing. Both remaining symptoms —
the attract freeze and the post-START stall — are that one overrun.

What is now pinned down:

* The leaking call sits in `main_func_800BA1A4`, which runs **exactly once per
  frame** (its call count tracks the game's own frame counter precisely).
* That function is itself **balanced** (`-0x18` then `+0x18`, one return), so the
  leak is in one of its **11 direct callees** or its single **indirect** call.
* It is **triggered, not constant**: entry `sp` is exactly stable for **991
  frames**, then falls by exactly `0x18` on every frame from **992** onward.
* **No state global explains the onset** — scene, gate, selected render group and
  attract state are all unchanged across the frame it begins.

Ruled out along the way, each with a control: runaway recursion; a cycle in the
scene graph; a function that never restores the stack; an early return that skips
the restore; dispatch running off either lookup table; and an unresolved indirect
call (which would exit the process loudly, not leak).

**Next:** entry-`sp` probes cannot discriminate further, because once the parent
drifts every callee drifts with it. Measure entry-vs-exit per callee by hooking
each one's **epilogue instruction address** — `before_vram` at that address gives
an exit hook, which the tooling otherwise lacks.

`SNP_STACK_RELOC=4` masks it. It is a diagnostic, not a fix, and must not ship.

## Next — capability, cheap and high leverage

**A26 — add the `.main` segment to splat.** *(Config lives in the sibling repo `/home/joh/Documents/sin_and_punishment/splat-project/`, not here — T19.)* ROM `0x3E850`, vram `0x800A7070`,
size `0x2EA00`, ~620 functions. Today `scripts/decomp.sh` cannot see any of the
mid-level engine, and that blind spot already caused one confidently wrong
"dead code" conclusion. One segment entry plus a splat re-run — pure CPU.

**Check first:** a re-run regenerates `asm/`, which `decomp.sh` reads. Confirm
the existing files come back byte-identical before relying on anything after.

**T11 — triage the 296 symbol gaps.** `vram + size < next vram`. Most are
genuine data, so this is a triage list, not a mass fix — but a 0x78-byte gap is
what caused the START crash, so the class is proven dangerous.

## Then — Phase 1 completeness

**B31 — Yay0 asset segmentation.** Re-scoped: the compressed blobs are assets,
not code (ledger B37), so this buys asset extraction and nothing for debugging.
Real work for a complete port; not on the critical path.

**B36** — validate the derived unpack addresses against a running build before
relying on them.

## Publication — when the current bug is closed

These are deliberately *not* now. A half-finished investigation reads worse than
no writeup, and the story is much stronger once the root cause is fixed rather
than masked.

1. **Upstream the patches — one per day, in this order.** Assessed 2026-08-18.

   | # | patch | verdict |
   |---|---|---|
   | 1 | `N64ModernRuntime-vi-null-mode-fix` | **Ready.** 12 lines, one file, null-deref fix, generalises to any game. Start here |
   | 2 | `RecompFrontend-keyboard-defaults` | Likely fine; 72 lines, needs review for project-specific choices |
   | 3 | `N64ModernRuntime-pif-raw-si-responder` | 89 lines, the most substantial; needs the clearest repro |
   | 4 | `N64Recomp-rsp-sig0-fix` | **Do NOT submit as-is** — see below |

   **PR 1 is ready.** Our submodule sits exactly on upstream `main` (0 commits
   behind) and nothing has touched `ultramodern/src/events.cpp` since, so it
   applies cleanly. `update_vi()` dereferences `next_state->mode` with no null
   check; `ViState::mode` has no default initializer; and the only thing that
   populates it early — `set_dummy_vi()` — stops running the moment
   `is_game_started()` flips true, which happens before the game's MIPS code
   reaches `osViSetMode`. Verified in upstream source, not inferred.

   **Outstanding for PR 1:** a stated reproduction. We hit the crash; we have
   not confirmed we can still trigger it on demand by reverting the patch. Do
   that before opening, because "here is how to see it" is what gets a fix
   merged quickly.

   **PR 4 needs redesign first.** It changes `expected_c0_reg_value()` for
   `RSP_COP0_SP_STATUS` from `0` to `0x80` — globally, for every game — because
   *this* game's custom audio ucode polls for SIG0. Other titles expect 0, so as
   written it is a breaking change dressed as a bug fix, and its own comment
   calls it a hack. To be proposable it must become configurable (a per-project
   setting in the toml, defaulting to the current behaviour). That is a design
   conversation with upstream, not a patch — worth opening as an **issue** first.

2. **Write up the START crash.** The single best story here: a symbol declared
   `0x14` instead of `0x8C` silently truncated a function, dropping a
   registration, so a list pointer underflowed and the game segfaulted **four
   scene-loads later**. It is a complete chain — symptom, false leads, the
   measurement that settled it, the one-line fix, and confirmation. Target the
   README plus a standalone `docs/writeup-start-crash.md`.

3. **Write up the method.** The ledger and playbook are unusual artifacts: claims
   tagged by *how* they are known, withdrawn beliefs kept rather than deleted,
   a linter that flags entries resting on retracted foundations, and a
   machine-rolled explore/exploit router. Worth a short piece on why a debugging
   log needs epistemic status at all — the honest hook is that ~12 findings in
   one session were confidently wrong, and every one had real evidence behind it.

4. **README is the front door.** Most readers get no further. It should state
   what works, what does not, and how to reproduce — and be explicit that the
   project is AI-assisted. Being matter-of-fact about that reads better than
   being vague, and the interesting claim is not "I wrote this alone" but "I ran
   the investigation and built the tooling that kept it honest".

## Standing

- **Push to `fork` at least daily** — `scripts/daily_push.sh` (safe-by-default:
  stages an allow-list only, refuses on scratch hooks or a failing ledger check).
- Keep the README current whenever anything is pushed.
- Nothing proprietary in commits; review the real diff every time.
