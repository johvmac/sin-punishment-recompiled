# Findings ledger — the VISITED SET

**Read this file in full before expanding any node. It is deliberately short.**

`boot-debugging-2026-08-13.md` is a *journal* — chronological, 5,000+ lines,
expensive to search. This is the *index*: one line per fact, with a status. A
journal answers "what happened"; only this answers **"has this already been
checked?"**, which is the question that decides whether a node is worth
expanding.

Without it, the cheapest way to answer "do we know X?" is to re-derive X. That
is how the same ground gets covered twice — and a shortest-path search with no
visited set is not a shortest-path search.

## Status vocabulary (revised 2026-08-18)

The old EST/OUT/WD tags hid *how* something was known. Roughly a dozen entries
were wrong this session, and they did **not** fail for lack of evidence — every
one cited real evidence, correctly gathered. They failed because the **claim was
broader than the evidence supporting it**. So the tag now records the kind of
support, because the kinds have very different reliability.

| tag | meaning | track record |
|---|---|---|
| **INTERVENED** | Changed one input, watched the symptom move. | **Never wrong yet.** Strongest available. |
| **MEASURED** | A tool reported this value. The claim is the *literal* reading, nothing more. | **Never wrong yet.** |
| **READ** | What the code says. Good for "what does this do"; **not** evidence about what actually runs. | Reliable when kept to behaviour-in-principle. |
| **NEGATIVE(scope)** | "Nothing does X." **The scope MUST appear in the claim itself.** | **4 of our failures.** The single most dangerous form. |
| **INFERRED** | Composed from other entries into a story. | **3 of our failures.** Never proof. |
| **WD** | Was believed, later overturned. Never deleted. | — |
| **OPEN** | Live question. | — |

## Rules for this file

1. **A claim is established only if a test ran that could have contradicted it
   and didn't.** A grep returning nothing usually could not have. A watchpoint
   held across the whole failure window could — but only with a positive control
   showing the same tool fires elsewhere.
2. **Every negative names its scope inside the claim.** Not "nothing calls this"
   but "nothing in splat's asm calls this". This rule alone would have prevented
   a third of our errors, including the day we declared a working probe broken.
3. **Load-bearing claims** — anything a fix or a decision will rest on — carry
   **Observed / Falsifier / Checked**. Everything else stays one line; full
   rigour on every entry is unaffordable.
4. **Distinguish the number from its meaning.** "CALLBACK=0" is MEASURED; "the
   list was empty" is INFERRED. Record them as separate claims or not at all.
5. An entry that gets overturned becomes **WD** — never deleted. The overturned
   belief is exactly what a future session would otherwise re-derive.
6. Add the entry when the finding lands, not at session end.

## Load-bearing claims — full treatment

These are the claims decisions rest on. Each states what was *literally*
observed, what would falsify it, and whether that was checked.

### L1 — The START crash was a truncated symbol (fix applied)
- **Claim (MEASURED + INTERVENED):** `ovlfile02_func_800E4F34` was declared
  `size = 0x14`; the real function is `0x8C`. The generated C stopped after the
  first call, dropping the registration of the renderer's per-frame reset.
- **Observed:** generated C for that address contained 5 instructions ending at
  a `jal`; m2c of the same address emits 35 statements. splat's own `endlabel`
  and the next symbol both put the end at `0x800E4FC0`.
- **Falsifier:** the generated C containing the later statements, or splat
  agreeing with `0x14`, or the crash surviving the size correction.
- **Checked:** yes, all three. After the fix the missing registrations appear in
  a probe log and a 2h36m user-confirmed run never crashed (was 100% reliable).

### L2 — The attract freeze and the START stall are ONE bug
- **Claim (INTERVENED):** both are thread 4's stack overflowing onto the
  dispatch table at `0x8007AF0C`.
- **Observed:** a watchpoint caught `boot_func_800489C0` — a 4x4 matrix multiply
  that stages 16 floats on its own stack frame — writing the float `0.0463` over
  the function pointer. With `SNP_STACK_RELOC=4` graphics run through the START
  transition to 848 tasks at +30/s; without it the identical run stalls at ~360.
- **Falsifier:** the workaround failing to change the START symptom, or the
  clobbering write coming from somewhere other than thread 4's stack.
- **Checked:** yes. This is an intervention, which is why it is trusted.

### L3 — Thread 4's dispatch slots are NULLed at the stall
- **Claim (MEASURED):** `D_8007AF0C` and `D_8007AF10` hold valid addresses for
  12 samples, then read `0x00000000` for every sample to end of run.
- **Observed:** exactly that, via `SNP_WATCH` on both words.
- **Falsifier:** either slot holding a valid address after the stall.
- **Checked:** yes. **But note:** `func_80026598` legitimately calls
  `func_8004D500(0)`, so a NULL is not *by itself* proof of corruption — the
  corruption evidence is L2's float write, not this.

### L4 — The scene-graph data does not change during the failure
- **Claim (MEASURED, negative with a control):** neither the cycle node's child
  array (`0x8010273C`) nor the pointer to it (`0x8010278C`) is written between
  t=35s and t=62s, spanning the entire failure.
- **Observed:** two hardware watchpoints, zero hits.
- **Falsifier:** either watchpoint firing.
- **Checked:** yes — and the **positive control** is that the same tool fired
  immediately in its two other uses this session. Without that control these
  would be worthless non-results.

### L5 — The recursion genuinely gets deeper
- **Claim (MEASURED):** thread 4's stack low-water falls from `0x8007B748` to
  `0x8007AFE8` — 1,880 extra bytes — landing 220 bytes above the word L2 shows
  being clobbered.
- **Observed:** `low_sp` is an observed minimum stack pointer, not a tally, so
  it cannot be inflated by a miscounting loop.
- **Falsifier:** low_sp staying flat while the level counter rose (which would
  indict the counter instead).
- **Checked:** yes — the two moved together, so the depth growth is real even
  though the **`cycles=81` attribution remains unverified** (that detector has
  been wrong once already, see I2).

### L6 — splat's asm is not the whole ROM
- **Claim (MEASURED):** splat covers `0x80020000-0x8005FFFF` and `0x800E0000+`
  only; `0x80060000-0x800DFFFF` (620 functions) is absent — 5,853 `glabel`s vs
  6,827 recompiled functions.
- **Observed:** per-64KB histogram of `glabel` addresses, plus a symbol count.
- **Falsifier:** finding any `glabel` in the missing range.
- **Checked:** yes. **This is the rule-2 lesson:** two entries asserting
  "nothing in the ROM does X" were really "nothing in splat's asm does X", and
  both were wrong. Use `RecompiledFuncs/` for any completeness claim.

---

## Attract-mode freeze (gfx task 1240)

| # | status | finding | evidence |
|---|---|---|---|
| A1 | EST | Freeze is thread 4's scene walk overflowing its 8KB stack onto the callback table at `0x8007AF0C` | 2026-08-17; arithmetic closes to the byte |
| A2 | EST | `SNP_STACK_RELOC=4` runs past 1240 to 2650+, never stalls | 2026-08-18; user confirmed on screen |
| A3 | EST | Baseline before the walk = 5,488 bytes — **not** inflated | 2026-08-18; identical on relocated stack |
| A4 | WD | ~~"Walk grows +1 level per frame, forever, from t≈40s"~~ — **too coarse, and the shape matters.** It is flat at 9 levels from t=7 to t=31, then explodes to 31 by t=40 and 90 by t=43. Superseded by A13 | 2026-08-18 |
| A5a | MEASURED | The child data of node `0x80102784` is **static** — confirmed twice by different methods (`SNP_WATCH` sampling, then two watchpoints with zero hits, L4) | 2026-08-18 |
| A6 | **UN-WITHDRAWN** | **The withdrawal was itself wrong — the probe was right.** `func_80033758` ends: `var_s4_2 = arg0->unk8`; `while (*var_s4_2 != 0xFF) { recurse(child); var_s4_2 += 1; }`. Children **are** a `0xFF`-terminated byte array at `node+8`, exactly as the original probe assumed; `arg3` is a **flag** (0/1, selecting `func_800274F8` vs `func_80027244`), not a count. **Malformed child lists are back on the table for A10** | 2026-08-18; m2c on `func_80033758` |
| A11 | EST | **The walker has NO depth limit and NO visited set.** It recurses once per child byte with nothing to stop a node that lists itself or an ancestor. Child index `i` addresses `arg0 + i*0x14`, `arg1 + i*0x20`, `arg2 + i*4` — one corrupt index byte redirects all three arrays coherently, so the walk still looks structurally valid | 2026-08-18; m2c |
| A13 | EST | **A4's "+1 level per frame from t≈40" is too coarse — the real shape is a sudden explosion.** `SNP_WALK` thread 4, one run: `levels=9 depth=640 cycles=0` **rock stable from t=7 to t=31**, then `t=40: levels=31 cycles=22`, `t=43: levels=90 depth=2528 cycles=81`, then frozen. Graphics hold a **perfect +30/s until t=42** (gfx 1240) and stop at t=43. First cycle is logged at **gfx task 1160 (t≈39)** — so the cycle appears ~3s **before** the freeze, and everything is healthy for the 30s before that | 2026-08-18; `SNP_WALK=1`, 55s attract run |
| A14 | EST | The walker's call rate collapses at **t≈32** (2790/s -> 186/s), a full 10s **before** the first cycle and while graphics are still perfect. Most likely benign — attract switches to a smaller scene — but it must be excluded before reading t≈32 as the trigger | 2026-08-18 |
| A15 | EST | **A child index of `0` recurses into the SAME node** (`func_80033758(arg0 + idx*0x14, …)` with `idx = 0` re-passes `arg0`). The cycle node's child list at `0x8010273C` reads `01 FF 00 00 01 0A FF 00` — currently well-formed (`01`, terminator). **But if that `FF` at offset 1 is clobbered, the list becomes `01 00 00 01 0A …` — two index-`0` children, i.e. immediate infinite self-recursion.** This is a concrete, checkable mechanism for A12 | 2026-08-18; m2c + `SNP_WALK` bad-edge dump |
| A12 | OUT | ~~"The `0xFF` terminator is being clobbered one byte per frame"~~ — **refuted by two hardware watchpoints**, each armed at t=35s and held to t=62s across the whole failure: `0x8010273C` (the child array itself) **never written**, and `0x8010278C` (the `node+8` pointer to it) **never written**. Positive control: the same tool fired immediately in its two previous uses this session | 2026-08-18 |
| A16 | MEASURED | **The graph around the cycle node is genuinely static** — no write to `0x8010273C` or `0x8010278C` **between t=35s and t=62s**, spanning the whole failure — independently confirming A5 by a different method. So whatever changes, **it is not this data** | 2026-08-18; two watchpoints, zero hits |
| A17 | EST | **The depth growth is REAL, not a counter artefact.** `low_sp` — an actual observed minimum stack pointer, not a tally — falls from `0x8007B748` to `0x8007AFE8`, i.e. **1,880 extra bytes** of stack consumed, and lands 220 bytes above the dispatch table it goes on to clobber. Any explanation must account for genuinely deeper recursion | 2026-08-18; `SNP_WALK` low-water |
| A19 | MEASURED | **The walk's root changes exactly once, and early.** Per-frame root: `800E7D98` with **70** calls/frame up to frame ≈420, then `800EC8D4` with **93** calls/frame, both then constant. The switch is at **t≈14s — some 25s BEFORE the failure** (t≈39). `800EC8D4` is the same node that heads the cycle report's ancestor path | 2026-08-18; `[root]` probe |
| A20 | MEASURED | Calls-per-frame is **flat at 93** from the root switch through at least frame 750 (t≈25s). No gradual climb in walker work during that window | 2026-08-18 |
| A21 | **INCONCLUSIVE — instrument limit** | **The `[root]` probe says nothing about the failure window.** Its output stops at frame 750 (t≈25s), well before the t≈39 event. Its top-level detection is `sp + 64 >= max_sp_ever`, so once recursion deepens and a top-level call arrives at a slightly lower sp, frames stop being counted and it silently goes quiet. **Do not read the absence of later lines as "the walk stopped."** Fix: detect frame boundaries from the *caller* (`func_800261FC`), not from a stack-pointer heuristic | 2026-08-18 |
| A22 | MEASURED | **The top-level walk is re-rooted onto the "cycle" node itself.** Hooking `func_80033A40`/`func_80033AC4` — the walker's only two callers, so no heuristic is involved — the descriptor goes `800E7D98` -> `800EC8D4` -> **`80102784`**. That last address is exactly the node `SNP_WALK` reports as its own ancestor. **A node being used both as an in-graph node and as a top-level descriptor would make any visited-set detector cry "cycle" without anything being wrong** | 2026-08-18; `[top]` probe |
| A23 | MEASURED | **Top-level walk calls cease at n≈780 (t≈26s)** — while graphics continue happily to t=42. Two independent probes now agree the walk stops long before the freeze, so this is not the earlier probe's heuristic failing (A21) | 2026-08-18; `[top]` probe, wrapper-hooked |
| I6 | READ | **Corrected again — the `FFFF0000` is meaningful after all.** The walker tests `node->unk0 != 0xFFFF` as a **type** field, so a `+0` word of `FFFF0000` says the thing I logged as a "descriptor" **is itself a node**, of the non-rendering type. So `desc=` and "root node" are the same address, and A22's sequence is a sequence of root *nodes*. My first reading (a pointer) and my second (meaningless) were both wrong; the probe was right both times | 2026-08-18; m2c on `func_80033758` |
| A25 | MEASURED | **The accused subtree is CLEAN at the exact moment of the accusation.** 250 consecutive walker calls dumped from root `0x80102784`, landing at **t=39s / gfx task 1150-1160 — the same frame `SNP_WALK` reports its first cycle**. Result: **23 distinct nodes** spanning 22 array slots, 54 leaves (NULL child list), and **zero child lists containing index `0`** — so by A24 no cycle can exist here. Each node appears 11 times because 250 calls / 23 nodes ≈ **11 complete walks**, i.e. ordinary per-frame re-walking, not revisits within one traversal | 2026-08-18; `[dump]` probe |
| A5b | INFERRED | **Now very likely a detector artifact, not a finding.** A25 dumps the accused subtree in the accused frame and finds it structurally sound, and A24 shows a cycle is impossible without a zero child index, of which there are none. The remaining innocent explanation for `cycles=81` is a visited set that is not cleared between traversals or between frames. **Not yet proven** — that needs reading the detector's reset logic | 2026-08-18 |
| I7 | EST | **Instrument defect (6th), caught by cross-checking:** my `[dump]` probe read RDRAM bytes as `b[0..3]` with no endianness swap, so every 4-byte group came out reversed — `01 FF 00 00` printed as `00 00 FF 01`. It was caught only because `SNP_WALK` had independently printed the same address. **Byte-level RDRAM access in a hook needs the `^3` swap; word access does not.** Had I trusted it, I would have "found" a child index of `0` and declared a self-recursion bug that does not exist | 2026-08-18 |
| A27 | WD | ~~"The walk is always entered at the same stack depth, because `high_sp` is constant"~~ — **the inference was invalid.** `high_sp` is a running **maximum**, so it *cannot decrease* by construction. A statistic that can only rise is incapable of showing that entry depth fell. I used it to kill the "invoked from a deeper call chain" hypothesis; that hypothesis is **back open**, and A30 now points toward it | 2026-08-18 |
| A30 | MEASURED | **Evidence the entry depth DOES drop.** A traversal-boundary test of `sp >= 0x8007B9C8` (the observed top-level entry) fires normally up to traversal ~600 (t≈20s) and then **stops firing entirely**, while the walk keeps running to the t=42 freeze. Consistent with top-level entries moving to a *lower* sp — i.e. the walk being invoked from deeper in the call chain — which **corrects A27** — it is exactly what that entry wrongly ruled out | 2026-08-18; `[trav]` probe |
| A31 | MEASURED | Per-traversal `maxdepth` is **9 on every traversal sampled** (t≈0-20s), with `calls` stepping 70 -> 93 at the root change. No traversal in that window is deep. **Scope: healthy window only** — the probe stopped reporting before the failure (A30), so this says nothing about t>20s | 2026-08-18 |
| I8 | **FIXED, cheaply** | **Instrument defect (7th): hook statics are shared between threads.** Both thread 3 (`0x80067xxx`) and thread 4 (`0x8007Bxxx`) call the walker, so one shadow stack mixes two stacks and a low-sp call never pops the other's entries. **Fix: `static _Thread_local` — compiles clean, the generated funcs are built as C17.** Verified by rebuild (0 errors) and by the corrected probe reporting a single consistent entry sp per thread. Same class as I4/I5; this is now three of seven | 2026-08-18 | Both thread 3 (stack `0x80067xxx`) and thread 4 (`0x8007Bxxx`) call the walker, and traversal 0 reported `minsp=80067478` — thread 3's stack. With one shadow stack, a low-sp thread-3 call never pops thread-4 entries, so depth inflates. **Same class as I4/I5. Any per-thread probe must key on the thread, and a hook's statics are global** | 2026-08-18 |
| A28 | INFERRED | **Correction to A25 — "11 complete walks" was inferred, not measured.** The dump recorded no traversal boundary, so *11 walks x 23 nodes* and *one walk revisiting each node 11 times* fit the same 250 lines equally well. The second is a shared-subtree DAG (legal under A24: forward-only edges permit two parents sharing a child) and would inflate call counts **without** inflating depth. **Distinguishing them needs a traversal-boundary marker in the dump** | 2026-08-18 |
| A29 | INFERRED | **The arithmetic does not add up yet, and that is the live lead.** Depth is bounded by the longest forward chain, and the dumped subtree spans only 22 slots — so **90 levels cannot come from it**. Either the deep descent happens in a different, larger subtree than the one dumped, or the level counter is inflated by stale shadow-stack entries. `low_sp` falling 1,880 bytes at roughly 0x50 per frame is ~23 extra levels, **not 90** — so the counter and the stack disagree by about 4x | 2026-08-18 |
| A32 | MEASURED | **With per-thread state, thread 4's walk is healthy for as long as the probe can see it.** Every sampled traversal: `maxdepth=9`, entry sp a constant `0x8007B9C8`, `calls` 70 then 93 after the root change — through traversal 742 and ~60,000 calls (t≈25s). No traversal in that range is deep, and none fails to complete | 2026-08-18; `[trav2]`/`[live]` probes, `_Thread_local` |
| A33 | EST | **Probe-design lesson, not a finding about the game:** sampling every 20,000 calls is too coarse for this failure. The walk totals ~62-79k calls, so the deep descent lives in the **final few seconds / last few thousand calls**, and a fixed-interval sampler prints nothing there. Sample by *time near the end* or trigger on `maxdepth > 9`, not on a call-count modulus | 2026-08-18 |
| A34 | EST | **Boundary detection should be self-correcting.** Marking a traversal by "the shadow stack emptied" needs no constant and keeps working if the entry depth moves — unlike the hard-coded `sp >= 0x8007B9C8`, which silently stops marking anything the moment the assumption breaks. That failure mode is what produced the withdrawn A27, which this **corrects** | 2026-08-18 |
| A35 | MEASURED | **THE DESCENT, CAUGHT EXACTLY.** Anomaly-triggered probe, 81 depth records: depth climbs **9 -> 90 entirely inside ONE traversal (trav=750)**, and every single record is at **the same node `0x801028EC`**. Perfectly regular: sp falls by exactly **`0x18` per level**, and there are exactly **23 calls between consecutive levels** (nc 60822, 60845, 60868 … 62662). So one descent re-enters `0x801028EC` 80 times, walking 23 nodes each time | 2026-08-18; `[deep]` probe |
| A37 | MEASURED | **Answered — and it disproved its own premise.** The dump showed the accused node is a leaf with a NULL child list, so there is no edge to name and no loop to close. Superseded by A38/A39; the live question is now A40. Original: **Next, and narrow:** at a depth record, dump the ancestor chain and `0x801028EC`'s child-list pointer + bytes (with the `^3` swap). That names the edge that closes the loop. Everything needed is now pinned: traversal 750, node `0x801028EC`, ~23 calls per level, `0x18` of stack per level |  |
| A38 | MEASURED | **THE ACCUSED NODE IS A LEAF.** At every depth record d=10..15, `0x801028EC` has child-list pointer **`0x00000000`** — and the walker tests `if (child_list != NULL)` before recursing, so it **cannot recurse from there at all**. The five ancestors are identical at every record and all distinct (`801028D8 801028C4 801028B0 80102874 80102860`, each a forward `+0x14` step). **There is no cycle and no deepening recursion** | 2026-08-18; `[edge]` probe |
| A39 | INFERRED | **Reframe: this is a STACK LEAK, not runaway recursion.** The same bounded traversal runs repeatedly over static data, but the emulated `$sp` is **not fully restored** — one frame per traversal leaks `0x18` bytes, so my shadow stack retains exactly one extra entry each pass and "depth" is an artifact of that. It fits every measurement: `0x18` per level and 23 calls per level (A35) = **one leak per full 23-node traversal** (A25); a steadily falling `low_sp` (L5) with static data (L4) and no zero child index (A24, now vindicated). **A recompiler-level bug — a function whose epilogue does not restore `$sp`** |  |
| A36 | WD | ~~"23 calls per level means genuine recursive re-entry"~~ — the arithmetic was right, the reading was wrong. 23 calls per level is one full traversal per **leak**, not per recursion. A24 never needed overturning | 2026-08-18; A38 |
| A40 | OPEN | **Next: find the frame that leaks `0x18`.** One call per traversal decrements `$sp` by `0x18` and does not restore it. Candidates: a stubbed function still carrying a prologue, a mis-split symbol whose epilogue was truncated (the L1 class), or a hook-injected path. Compare `ctx->r29` at entry and exit of each function on the traversal path — or diff the generated prologue/epilogue pairs for a `-0x18` with no matching restore |  | The walker recurses into `arg0 + idx*0x14` where `idx` is a byte from the child list, so **every edge goes strictly forward in the node array** except `idx == 0`, which re-enters the same node. Therefore: no zero byte in any traversed child list => no cycle can exist, and any "revisit" a detector reports is either a shared subtree (a DAG diamond) or a detector error | 2026-08-18; m2c |
| A41 | MEASURED | **A free ROM-wide check for unbalanced stack adjustments now exists.** Scanning `RecompiledFuncs/` for `ctx->r29 = ADD32(ctx->r29, N)` per function: **244 of 6,827** decrement `$sp` with no matching positive of equal magnitude, **95 of them by exactly `0x18`**. Reusable for the whole class | 2026-08-18 |
| A42 | EST | **The check over-reports, and by how much matters.** `boot_func_80025E44` is among the 95 — it is thread 3's **non-returning** loop entry, which legitimately never restores. Any thread entry or no-return function looks identical to a leak. **Treat 244/95 as upper bounds, not findings** | 2026-08-18 |
| A43 | NEGATIVE(scene-walk path, whole-function scope) | **A whole-function missing restore does NOT explain A39.** Of the 95 exactly-`0x18` candidates, **none is on the scene-walk path** — the walker's callees are boot-segment (`0x80027xxx`/`0x80032xxx`) plus the type vtable at `D_80059748`, and the only boot entry in the list is the non-returning thread loop. Scope stated because the check only asks whether *any* matching restore exists anywhere in the function | 2026-08-18 |
| A44 | OPEN | **Refine the model.** A43 rules out "the function never restores"; it does **not** rule out a function that restores on its normal path but **returns early on a branch that skips the restore** — that passes A41's check and still leaks once per call. Next is a direct measurement, not another static sweep: log `ctx->r29` at entry and exit for the walker's direct callees and find the one whose exit is `0x18` below its entry |  |
| A45 | MEASURED | **THE LEAK IS BRACKETED.** Entry `$sp` logged at two levels, printing only on change, same frame window: `func_800261FC` (the per-frame callback) is **constant** through n=735-790, while `func_80033A40` (the walk wrapper, called from within it) drifts **exactly -0x18 per call from n=751 onward**. So the leaking frame is **between those two functions** — the chain is `func_800261FC` -> {`func_80031950`, `func_80026288`, `func_80031F50`} -> ... -> `func_80033A40` | 2026-08-18; `[cb ]`/`[wrp]` probes |
| A46 | MEASURED | The wrapper's entry `$sp` is **constant for the first 750 frames** and only then begins drifting — matching A35's descent onset at trav=750 exactly. **The leak is triggered by something at frame ~750, not present from boot** | 2026-08-18 |
| A47 | EST | Startup transient, not a leak: `func_800261FC`'s own entry `$sp` moves -0x20 on calls n=2 and n=3 only, then is stable. Do not mistake it for the defect | 2026-08-18 |
| A48 | MEASURED | **The drift onset is NOT at a fixed frame — it varies between runs.** One run began drifting at wrapper call n=751; a later identical-config run showed `sp` constant at `0x8007B9E0` with `d=0` through n=765. So it is **triggered by a game event, not a frame counter** — which also means any probe keyed to a fixed frame number will miss it on some runs | 2026-08-18; two `[wrp]` runs |
| I9 | EST | **Instrument defect (8th): `ctx->r31` is NOT a usable return address here.** It read `00000000` on all 30 samples. N64Recomp emits native C calls, so the MIPS `$ra` is not maintained as a live caller pointer. **Do not try to identify a caller from `ctx->r31`** — use a hook on the candidate callers instead | 2026-08-18 |
| A49 | OPEN | **Next for A45's bracket.** The three intermediates (`func_80031950`, `func_80026288`, `func_80031F50`) all show constant entry `sp` while the wrapper below them drifts, which a simple once-per-frame chain cannot explain. Leading candidate, **unmeasured**: the wrapper is re-entered at increasing nesting depth within a frame (a node-type handler at the `D_80059748` vtable re-triggering the render path). Test by counting wrapper entries **per frame** rather than in total |  |
| A50 | MEASURED | **The wrapper is entered exactly ONCE per frame — nesting refuted.** `entries=1` at every sampled frame, and `minsp` constant at `0x8007B9E0`. The frame counter itself stops once drift begins, because the boundary test is `sp == max` and **`sp` never returns to its maximum again** — which is independent confirmation that this is a true leak, not deeper nesting | 2026-08-18; `[per]` probe |
| A51 | NEGATIVE(whole boot segment, generated C) | **Neither static leak model explains it.** (a) *never restores*: 244 ROM-wide, none on the walk path (A43). (b) *early return skips the restore*: 219 functions have more return points than stack restores, and **zero of them are in the boot segment** — which is where the entire walk path lives. So the leak is **not a missing or skipped `addiu $sp` in generated code** | 2026-08-18 |
| A52 | **INCONCLUSIVE** | Read 48 words at the node-type vtable `0x80059748`: 36 look like pointers, 6 resolve to no recompiled function. **But three of those six (`800D4F00`, `800D5A70`, `800E4FE0`) are known DATA globals**, so the read plainly overran the table's real end. **The table length is unknown and must be established before this means anything** | 2026-08-18 |
| A53 | OPEN | **Re-cost after A51.** Cheap static avenues are exhausted. Remaining candidates, in cost order: (1) bound the vtable properly, then check its real targets; (2) the leak is in the **runtime/hook layer** rather than generated code — check whether any injected hook or `recomp_` shim perturbs `ctx->r29`; (3) `func_80027228` is called from both threads with varied deltas, so it needs a per-caller probe, not a global one |  |
| A54 | MEASURED | **The node-type vtable at `0x80059748` has exactly 18 entries.** Indices 0-17 are contiguous real functions (`0x800331B8`-`0x8003370C`, ~0x46-0x58 apart — a clean jump table); index 18 onward is a **different structure**, demonstrably the section table (index 25 = `0x0003E850`, the `.main` section's ROM offset; index 26 = `0x800A7070`, its vram). **A52 resolved: no vtable target is missing** | 2026-08-18; ROM read cross-checked against `RecompiledFuncs/` |
| A55 | INFERRED | **STRONG LEAD, not yet measured.** `SNP_WALK` reports **47 distinct types** with the walker's only guard being `type != 0xFFFF` — there is **no upper-bound check**. With an 18-entry table, any type >= 18 dispatches **past the end into the section table**, i.e. calls addresses like `0x0003E850` or `0x10008000`. In the recomp an indirect call to an unregistered address will not fault the way hardware would; a fallback that does not balance the stack would produce exactly the observed per-traversal leak. **Control:** log the dispatched type and flag any >= 18 | |
| A56 | OPEN | **Do A55's control first — it is one cheap probe** and would explain the leak, the onset varying by run (A48), and why no generated function is missing a restore (A51): the leak would not be in a recompiled function at all, but in the dispatch of a bogus pointer |  |
| A18 | OPEN | **The live question, now sharply framed:** static data + no depth limit (A11) + genuinely deeper recursion (A17) means the **traversal** changed, not the graph. Either the walk is entered from a different root/call site, or the "cycle" attribution is wrong. **Note the detector has already been wrong once (I2), so treat `cycles=81` as unverified.** Next: log the walk's *root* argument per frame — cheap, and it separates "deeper tree from a new root" from "re-entering the same nodes" |  |
| A7 | WD | ~~"Type `0xFFFF` is an out-of-range vtable dispatch"~~ — `0xFFFF` is dispatched throughout the healthy window | 2026-08-18 |
| A8 | OUT | Deadlock / scheduler bug — every thread cycles at 30Hz through the freeze | 2026-08-17; `SNP_VI_PROBE` rate counters |
| A9 | OUT | Stubbed functions on the attract path — 127 instrumented, zero called | 2026-08-17, re-confirmed 2026-08-18 **including with START pressed** |
| A10 | OPEN | **Merged into A18** — same question, sharper framing. The "+1 per frame" wording is withdrawn (A4); the real shape is A13 |  |
## START crash — **SOLVED 2026-08-18** (was: NULL deref in `boot_func_8003860C`)

**The answer, in four lines.** `symbols/sinpunishment.syms.toml` declared
`ovlfile02_func_800E4F34` as `size = 0x14`; the real function is `0x8C`. The
generated C therefore stopped after its first call, silently dropping the
`func_800B4EE0(0, 0)` that registers the renderer's per-frame reset. Scene 2 then
reset nothing, the list counts stayed stale from scene 20, the unconditional
rewind `ptr -= count*4` drove the pointers below their buffers, and the sort
dereferenced NULL. **Fix: `size = 0x8C`.** User-confirmed: no crash in 2h36m.

### Load-bearing — reuse these

| # | status | finding | evidence |
|---|---|---|---|
| B53 | EST | **ROOT CAUSE (class BC-2, "declared too short").** Truncated symbol, as above. Fails **silently**: no error, no stub, it compiles and runs | 2026-08-18; recompiled C vs m2c at the same address |
| B57 | EST | **USER-CONFIRMED, clean build.** START at t≈12s: no crash; ran 2h36m with non-gfx threads at +30/s throughout | 2026-08-18; user + 9,400s heartbeat |
| B58 | EST | **Visual proof the fix landed.** Screen fades to **white** on START — scene 2's init ends `func_80038214(-0x100 x4)`, a white fade and statement **8 of 9** (every other scene passes `0xFF x4`). Pre-fix it stopped at statement 1 | 2026-08-18; m2c + user |
| B45 | EST | **Crash mechanism, measured.** Healthy frame b1 `ptr=0x802BA6A0 n=83`, b2 `ptr=0x802B9EA0 n=7`; fatal frame same counts, `ptr=0x802BA554` / `0x802B9E84` — each down by exactly `count*4`, unrestored. Append raises the pointer, the rewind lowers it; they balance **only while appends happen** | 2026-08-18; `SNP_SORT=1` |
| B49 | EST | **The per-frame reset chain.** `func_800B4EE0` registers `func_800B4CE8` (list 0) -> each frame -> `func_8002A8E0` -> `func_8002A720` x2, zeroing both groups' counts and re-pointing their bases | 2026-08-18; `scripts/gdb_watch.sh` on `0x80067DA4`, caught `13 -> 0` |
| B50 | EST | **Registration signature:** `func_80026960(fn, size, list)` allocates `size + 0x10`, sets the countdown byte `+0` to **0** always. `arg1` is a **byte size**, `arg2` a **list index**. Nothing is ever deferred at registration | 2026-08-18; m2c |
| B14 | EST | Populate is a **registered-callback walk**: `func_80026A54(n)` walks list `n` of 5 at `D_80068A9C`, calling each entry's fn ptr (`+4`) with `entry+0x10`. A nonzero countdown byte (`+0`) skips, decrements, removes at 0 — real, but never starts nonzero (B50) | 2026-08-18; m2c |
| B15 | EST | Callback lists are managed by **resident** code (`func_80026900/60/A04/AF4/BDC/C34`); overlays register into them | 2026-08-18; asm xref |
| B16 | EST | `func_800263CC` (scene loader) empties all 6 lists via `func_80026900` **and** sets gate `D_80068A97 = 0`. `func_80026900` also resets the allocator arena wholesale — nothing leaks | 2026-08-18; m2c |
| B20 | EST | **ARCHITECTURE.** `func_80025E44` (thread 3) is a **scene loop, not a frame loop**: load scene -> `func_80026288()` **once** -> register per-frame callback `func_800261FC` -> spin until `D_80068A95` changes -> repeat. Thread 4 does all per-frame work. Hence only 3-4 driver calls per run | 2026-08-18; m2c |
| B25 | EST | In `func_800263CC` the clear-all runs at the **END**, after overlay loading; the only step before the driver is the input poll `func_80026024` | 2026-08-18; m2c |
| B27 | EST | **Scene init is an indirect call through a table** at `D_800591A0` (23 entries, `0xFFFFFFFF`-terminated, ROM `0x345A0`) | 2026-08-18; m2c + ROM read |
| B39 | EST | **Scene N ⇔ splat `fileN`, a clean bijection** — all 23 init addresses sit in the `overlay_0` window (`0x800E4780`) and each resolves to a function boundary in exactly one `.s`, files 1-23 in ROM order. Confirmed independently by the recompiler's `ovlfileNN_` prefixes | 2026-08-18 |
| B55 | EST | **Scene sequence on START = 23 (attract) -> 1 -> 20 -> 2.** The crash was always the *fourth* load | 2026-08-18; scene-number probe |
| B40 | EST | START is detected in attract's chained callback `func_800E6D4C` as `D_800681BE & 0x1000`; it sets `D_8012E4B8 = 3`, and the next frame sets `D_80068A95 = 1` | 2026-08-18; m2c |
| B19 | EST | `D_800681BE` = `D_800681B8 + 6`, the button word written through the pointer by `func_8004C2F8` | 2026-08-18; m2c |
| B4 | EST | Group descriptor: 3 lists at `+0xF8/+0x100/+0x108` with counts at `+0xFC/+0x104/+0x10C`, plus a 4th pair at `+0x114/+0x118` (stride `0x10`). Rewound in `func_8002AA90`, sorted via `func_8002AA3C` -> `func_800387A0` (runs only at `count >= 2`) | 2026-08-18; m2c |
| B5 | EST | Append direction is mode-dependent on `D_80068180` (the *selected* group, set by `func_8002AD54`): `0x80067CA0` up, `0x800677C0` down. The asymmetric rewind is **correct by design** | 2026-08-18; m2c |
| B9 | EST | Gate `D_80068A97`: `!=1` -> reset + 5 populate passes + driver; `==1` -> a path with **no** driver | 2026-08-18; m2c |
| B17 | EST | The game has its own transition guard (`func_800260DC`: 0 normal, 2 triggered, 1 loading) but it **never engages** — `D_80068A97 = 0` at all four thread-3 rewinds | 2026-08-18; `SNP_PHASE` |
| B32 | EST | `D_800599F0` is a **73-entry table covering only the compressed region** (`0x7C8680`-`0xA8CA40`): 28 Yay0 + 44 data, zero raw MIPS. Uncompressed overlays load via `func_8003A1D0` | 2026-08-18; ROM read |
| B34 | EST | **`0x800E4780` doubles as the compressed STAGING buffer.** `func_8003A290` DMAs there then decompresses to a **downward** allocator (`D_800744D8` from `D_800744D4`) | 2026-08-18; m2c |
| B37 | EST | **The 28 Yay0 blobs contain NO CODE — they are assets.** Positive control: known code overlays score 5/6/31/76 `addiu $sp` prologues, boot 502; all 27 chunks score **0**. `load_overlays()` no-ooping on them is CORRECT | 2026-08-18; `scripts/overlay_map.py` |
| B38 | EST | `scripts/overlay_map.py` computes every asset chunk's unpack address offline (base `0x802A0370`, 27 chunks, 23 scenes) with a working Yay0 decompressor | 2026-08-18 |

### Withdrawn — do NOT re-derive

| # | status | finding |
|---|---|---|
| B12 | WD | ~~"ROOT CAUSE: counts reset by overlay code, rewind in resident code"~~ — the reset is **resident** (B49) and reached from the main segment. Superseded by B53 |
| B41 | WD | ~~"Scene 1 defers its callback 12 frames"~~ — `0xC` is a byte size, not a frame count (B50) |
| B46 | WD | ~~"The crash is the deferral meeting an unguarded rewind"~~ — rested on B41 |
| B47 | WD | ~~"Nothing writes the counts; `func_8002A8E0` is dead code"~~ — **false, and the lesson is T10**: the xref was blind to the main segment. A watchpoint caught it executing |
| B43 | WD | ~~"`func_8002A8E0` has zero callers ROM-wide"~~ — same blind spot; its caller is `main_func_800B4CE8` |
| B42 | WD | ~~"Below the buffer holds previous frames' still-valid pointers, so it is benign on hardware"~~ — the slots are **all zero**, measured |
| B28/B29/B30 | WD | ~~"8 unmatched overlay loads are unrecompiled Yay0 **code**"~~ — retracted by B37; they are assets, and `0x800E4780` is their staging buffer (B34) |
| B21 | WD | ~~"Registering 0 callbacks on a scene's first frame is anomalous"~~ — and also ~~"normal"~~. It was neither: the registration code was missing from the build (B53) |
| B22 | WD | ~~"Nothing registered because the overlay was never recompiled"~~ — the overlay was recompiled; one function inside it was truncated |
| B3 | WD | ~~"Unreachable until the attract freeze was fixed"~~ — crashes 22s before the freeze |
| B6 | OUT | A stubbed mode-flag writer (`ovlfile04_func_800E48E4`) is stubbed but **never called in a full boot-to-START run** — `SNP_STUB_PROBE` instrumented 127 stubs and recorded zero calls, START included |
| B24 | OUT | The defensive list-truncation hook fires **0 times** in a START run |
| B52 | OUT | Allocator failure — heap handle valid at every registration; `func_80026900` resets the arena wholesale |

### Still open

| # | status | finding |
|---|---|---|
| B59 | EST | **The stall is a PRODUCER stop, not a consumer stall or a deadlock.** `SNP_CENSUS` across the transition: 33 (queue, thread, event) streams active before go to **exactly zero** after; 30 keep running at an unchanged ~30/s; **0 new**. Thread 4 is still woken on `0x8007d0e8` at 30/s but **stops sending to `0x800a3234`** (was 149 per 5s), and thread 17 — which consumed that queue and drove `0x8007ab7c` / `0x800a32a4` / `0x800a32dc` — goes completely silent. So the frame loop still ticks and simply **emits no graphics work** | 2026-08-18; `SNP_CENSUS=1`, scripted START at t=12s |
| B60 | EST | Scene 2's overlay has **no other truncated symbol**. Its two remaining size gaps (`func_800E47B4` declared `0x128`, `func_800E4E64` declared `0x30`) are **correct** — splat's own `endlabel` agrees with the symbol file and the recompiler emitted every instruction (81 and 12, spanning exactly to the declared end). The `.main` section has **zero** gaps. The gaps are unlabelled data, not defects | 2026-08-18; splat endlabel + generated-C address span |
| B61 | EST | **Thread map** (`SNP_STACKS=1`): t1 pri10 `0x80025CA4`; **t3 pri10 `0x80025E44` = the scene loop**; t3(!) pri70 `0x80052064`; **t4 pri50 `0x8004DD0C`**; t5 pri60 `0x8004D7C8`; t6 pri115 `0x8004EAD0`; t17 pri100 `0x8004E640`; t18 pri110 `0x8004E4A0`; t19 pri120 `0x8004E154` | 2026-08-18 |
| I5 | EST | **Instrument caveat: two different threads both report id 3** (`0x80025E44` and `0x80052064`, different priorities and stacks). Any per-thread probe keyed on id **conflates them** — the same defect class as I4. Re-read B59's "thread 3" rows with this in mind | 2026-08-18; `SNP_STACKS` |
| B62 | EST | **Thread 4's loop is a two-slot dispatcher.** `func_8004DD0C` blocks on queue `D_8007D0E8`, then: msg **1** -> call `D_8007AF0C(D_8007AB94)`; msg **2** -> call `D_8007AF10()`. **Both slots are plain function pointers, and a NULL slot means the message is consumed and nothing happens.** Set by `func_8004D500(fn)` -> `D_8007AF0C` and `func_8004D54C(fn)` -> `D_8007AF10` | 2026-08-18; m2c |
| B63 | EST | **CAUSE OF B56 LOCATED.** `SNP_WATCH` on both slots across the transition: `D_8007AF0C = 0x800261FC` and `D_8007AF10 = 0x80026598` for 12 samples, then **both `0x00000000` for every sample to end of run**. They are cleared exactly at the stall and **never restored**, so thread 4 keeps consuming its 30/s messages and dispatches nothing. This is precisely B59's "producer stop" | 2026-08-18; `SNP_WATCH=0x8007AF0C,0x8007AF10` |
| B64 | WD | ~~"The re-registration is missing / thread 3 fails to re-register"~~ — nothing fails to register. The slot is **overwritten**, not left unset | 2026-08-18; B65 |
| B65 | EST | **B56 IS BUG A — one defect, not two.** Watchpoint on `0x8007AF0C` armed before START caught **thread 4** writing `0x800261FC -> 0x3D3DCE39` (the float **0.0463**) from `boot_func_800489C0`, which is a **4x4 matrix multiply that stages its 16 results on its own stack frame** before copying them out. When thread 4's stack has run down far enough, that scratch buffer lands on the dispatch table. Identical address, mechanism and float-over-pointer signature as A1 | 2026-08-18; `scripts/gdb_watch.sh` + m2c |
| B66 | EST | **Behavioural confirmation:** with `SNP_STACK_RELOC=4` and scripted START at t=12s, graphics run **straight through the transition** to 848 tasks at t=29s, +30/s, **zero stalls** — where the same run without it stalls at 354-370. The one workaround kills both symptoms | 2026-08-18 |
| B56 | INTERVENED | **Resolved as a DUPLICATE of the attract freeze — see L2.** Not a separate bug; same stack overflow, same clobbered word, and the same workaround removes it. Kept for its symptom description, which looks nothing like bug A's:  The stall that replaced the crash: graphics run a clean 30fps to t=12s, drop to +16 at t=13s, then **stop dead at gfx_tasks=354** while non-gfx keeps +30/s for hours. Tied to the START transition, not wall-clock (scripted START at t=20s stalled at gfx 608 identically). Distinct from bug A, which stalls at gfx 1240 deep in attract |
| T11 | OPEN | 296 symbols leave an unclaimed gap (`vram + size < next vram`) — the BC-2 lead list. Most are genuine data, so **triage, do not mass-fix**; B53 shows 0x78 bytes is enough to break a scene silently |
| B36 | OPEN | Validate B35's derived unpack addresses against a running build before relying on them |
| B31 | OPEN | Add Yay0 segments to `tsumitobatsu.yaml`, re-run splat, extend the symbol map. Phase-1 scope, not debugging |
| B10 | MEASURED | **Answered by one 30s run — the explore jab paid off.** `D_80068180` held `0x80067CA0` on **all 29 samples** of a full attract run and never took the other group's value (`0x800677C0`), so there is nothing for two threads to disagree about. **Stated limit:** `SNP_WATCH` samples at 1Hz, so a sub-second toggle would be invisible — this is "constant at 1Hz across 30s", not "provably never changes". Also **I5**: two threads report id 3, so "thread 3 vs thread 4" was partly ill-posed | 2026-08-18; `SNP_WATCH=0x80068180` |

## Tools and methods

| # | status | finding |
|---|---|---|
| T12 | EST | **`run_game.sh`'s deadline used to live in the parent's `sleep`, so killing the parent orphaned the game** — 2h36m on 2026-08-18 when the session ended, with nothing reporting it. **FIXED:** a `setsid`-detached watchdog now holds a hard deadline (`SECS + 15`) in its own session and re-checks `comm` before firing, so a recycled PID is never hit; plus strays are reaped at startup. **Verified against the real failure mode**: wrapper SIGKILLed mid-run, game reaped ~21s later, zero left | 2026-08-18 |
| T13 | EST | Process hygiene on this machine: the binary name exceeds 15 chars so **`pgrep -x` never matches** — match `comm` = `SinPunishmentRe` instead. Never `pkill -f <binary>` (it matches its own command line); `pgrep -f` is likewise unreliable for *counting*, as it matches the running script too | 2026-08-18 |
| T1 | DEAD | **G6 / ares comparison.** gdb attach halts ares; memory stays readable, so polls return convincing all-static data. All prior ares results VOID |
| T2 | EST | `scripts/decomp.sh` (m2c over splat asm) — real C for any ROM function, free, no toolchain |
| T3 | WD | ~~"`grep -rn D_<addr> splat-project/asm/` is a **complete** ROM-wide xref"~~ — **it is not, and this caused a false "dead code" conclusion (B47).** See T10. The offset-grep half of the rule still holds: a global reached via a struct pointer shows no absolute reference, so grep the *offset* |
| T10 | EST | **splat's asm covers only `0x80020000-0x8005FFFF` and `0x800E0000+`. The whole `0x80060000-0x800DFFFF` "main" segment — 620 functions — is absent**, so any grep over `asm/` is blind to it. Totals: 5,853 `glabel`s in splat vs **6,827** functions the recompiler emits. **`RecompiledFuncs/` is the only complete index** — xref there (match `RECOMP_FUNC void <name>` for the enclosing function). Corollary: `scripts/decomp.sh` **cannot** decompile a main-segment function; read the generated C, or extend `tsumitobatsu.yaml` and re-run splat | 2026-08-18; per-64KB `glabel` histogram |
| T4 | EST | Overlays share VRAM; the same `func_800E9D8C` exists in several files. Always resolve the owning segment first |
| T5 | EST | GameShark cheat addresses are KSEG0, usable verbatim with `SNP_WATCH` |
| T6 | OUT | No public S&P decomp or symbol map exists. Stop searching |
| T8 | OUT | **decomp-permuter / objdiff / asm-differ do not apply to this project** (basis: their own docs). All three are *matching-decompilation* tools needing a target vs base comparison of compiled output. This is a **recompilation** project: MIPS -> C -> x86-64, so **in this pipeline** we never produce MIPS, have no target object, and have no C-to-match problem. m2c was useful because it runs asm -> C (a *reading* tool). **Filter for future tools: does it help us READ/MEASURE, or only MATCH?** | 2026-08-18; objdiff docs confirm it requires target+base objects |
| T9 | EST | **`build-debug/` exists** (`-Og -g`, RelWithDebInfo, 1.9GB, binary 236MB). gdb reports `file:line` into `RecompiledFuncs/`, so the `// 0x…:` comment above the line gives the exact MIPS instruction. Crash validated identical there (same 4-frame chain), so `-Og` did not perturb it | 2026-08-18 |
| B23 | EST | Faulting instruction is **`0x80038620: lwc1 $f4, 0x0($v0)`** — the first of the pivot's three float-key loads, i.e. `*array[i]`. Previously inferred; now read directly | 2026-08-18; debug build, `funcs_5.c:3347` |
| T7 | EST | Ghidra imports boot fine but covers **one base only**; descriptor globals are BSS and in no ROM image. splat+grep beats it for xrefs |

## Instrument defects found (4 in one session — assume the next probe is wrong too)

| # | defect | how it was caught |
|---|---|---|
| I1 | ares poll had no positive control — a halted emulator reads as "never changes" | active-stack control block |
| I2 | Cycle detector used strict `<` on sibling frames sharing a caller sp | known-healthy window reported 37 levels / 23 cycles |
| I3 | ~~`SNP_WALK`'s `longest_list`/`bad` read a structure that does not exist~~ — **RETRACTED 2026-08-18: the probe was correct** (A6). The "defect" was my reading of the generated C, not the probe. **A false instrument-defect finding is worse than the bug** — it discarded a working measurement and closed a live line of enquiry for a day | m2c on `func_80033758` |
| I4 | `SNP_PHASE` shared one per-frame counter across two threads | 169 identical warnings, each with an all-zero history |

**Pattern:** every one produced *plausible, confidently-wrong* output, and every
one was caught by a control rather than by inspection. Budget a control for each
probe; do not budget on being careful.
