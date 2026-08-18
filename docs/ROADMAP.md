# Roadmap

Ordered by what unblocks the most, not by size. Live technical questions live in
`findings-ledger.md` (the OPEN rows); this file is for work that is *scheduled*
rather than *being investigated*.

## Now — the one open root cause

**A18 / A35 — the recursive descent.** One traversal re-enters node
`0x801028EC` eighty times, 23 calls and `0x18` of stack per level, until it
overruns onto the dispatch table at `0x8007AF0C`. That single overflow causes
**both** remaining symptoms: the attract freeze and the post-START stall.

Next step is narrow and already specified (ledger A37): at a depth record, dump
the ancestor chain and that node's child-list pointer and bytes (with the `^3`
swap), which names the edge closing the loop.

`SNP_STACK_RELOC=4` masks it. It is a diagnostic, not a fix, and must not ship.

## Next — capability, cheap and high leverage

**A26 — add the `.main` segment to splat.** ROM `0x3E850`, vram `0x800A7070`,
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

1. **Upstream the patches.** `patches/upstream/` holds four real fixes to
   N64ModernRuntime, N64Recomp and RecompFrontend. Contributions to other
   people's projects carry more weight than a solo repo, because they mean
   working inside someone else's constraints and review. Check each still
   applies to current upstream, then open PRs one at a time.

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
