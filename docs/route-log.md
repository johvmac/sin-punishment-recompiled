# Routing log

Every explore/exploit decision, machine-rolled.
A gap in the numbering means a roll was skipped.

- roll #1: **EXPLOIT** (drew 0.349 vs eps 0.2) -> `A18` — The live question, now sharply framed: static data + no depth limit (A11) + genuinely deeper rec
- roll #1 OVERRIDDEN by user instruction: doing `B10` this checkpoint instead of the rolled `A18`. Logged so the trail stays honest — an unrecorded override makes the log decorative.
- roll #2: **EXPLOIT** (drew 0.341 vs eps 0.2) -> `A18` — The live question, now sharply framed: static data + no depth limit (A11) + genuinely deeper rec
- roll #3: **EXPLORE** (drew 0.038 vs eps 0.2) -> `B31` — Add Yay0 segments to tsumitobatsu.yaml, re-run splat, extend the symbol map. Phase-1 scope, not 
- roll #4: **EXPLOIT** (drew 0.286 vs eps 0.2) -> `A18` — The live question, now sharply framed: static data + no depth limit (A11) + genuinely deeper rec
- roll #5: **EXPLOIT** (drew 0.674 vs eps 0.2) -> `A18` — The live question, now sharply framed: static data + no depth limit (A11) + genuinely deeper rec
- roll #6: **EXPLOIT** (drew 0.749 vs eps 0.2) -> `A18` — The live question, now sharply framed: static data + no depth limit (A11) + genuinely deeper rec
- roll #7: **EXPLOIT** (drew 0.533 vs eps 0.2) -> `A37` — Next, and narrow: at a depth record, dump the ancestor chain and 0x801028EC's child-list pointer
- roll #8: **EXPLOIT** (drew 0.275 vs eps 0.2) -> `A37` — Next, and narrow: at a depth record, dump the ancestor chain and 0x801028EC's child-list pointer
- roll #9: **EXPLOIT** (drew 0.445 vs eps 0.2) -> `A37` — Next, and narrow: at a depth record, dump the ancestor chain and 0x801028EC's child-list pointer
- roll #10: **EXPLOIT** (drew 0.585 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #11: **EXPLOIT** (drew 0.226 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #12: **EXPLOIT** (drew 0.723 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #13: **EXPLOIT** (drew 0.564 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #14: **EXPLOIT** (drew 0.718 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #15: **EXPLOIT** (drew 0.407 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #16: **EXPLORE** (drew 0.175 vs eps 0.2) -> `A44` — Refine the model. A43 rules out "the function never restores"; it does not rule out a function t
- roll #17: **EXPLOIT** (drew 0.286 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #18: **EXPLOIT** (drew 0.642 vs eps 0.2) -> `A40` — Next: find the frame that leaks 0x18. One call per traversal decrements $sp by 0x18 and does not
- roll #19: **EXPLOIT** (drew 0.277 vs eps 0.2) -> `A53` — Re-cost after A51/A56. Both static leak models and the vtable-overrun idea are now ruled out. Re
- roll #20: **EXPLORE** (drew 0.087 vs eps 0.2) -> `B31` — Add Yay0 segments to tsumitobatsu.yaml, re-run splat, extend the symbol map. Phase-1 scope, not 
- roll #21: **EXPLOIT** (drew 0.862 vs eps 0.2) -> `A18` — NOW THE FRONTIER, with a concrete target (A74): node 0x801028EC. A72 settles the mechanism — +1 
- roll #22: **EXPLOIT** (drew 0.403 vs eps 0.2) -> `A80` — THE LIVE QUESTION, restated after A77/A78. Standing measurements: the walker's entry sp descends
- roll #23: **EXPLORE** (drew 0.111 vs eps 0.2) -> `B36` — Validate B35's derived unpack addresses against a running build before relying on them
- roll #24: **EXPLOIT** (drew 0.239 vs eps 0.2) -> `A80` — THE LIVE QUESTION, restated after A77/A78. Standing measurements: the walker's entry sp descends
- roll #25: **EXPLOIT** (drew 0.662 vs eps 0.2) -> `A80` — THE LIVE QUESTION, restated after A77/A78. Standing measurements: the walker's entry sp descends
- roll #26: **EXPLOIT** (drew 0.499 vs eps 0.2) -> `A80` — THE LIVE QUESTION, restated after A77/A78. Standing measurements: the walker's entry sp descends
- roll #27: **EXPLOIT** (drew 0.349 vs eps 0.2) -> `A80` — THE LIVE QUESTION, restated after A77/A78. Standing measurements: the walker's entry sp descends
- roll #28: **EXPLOIT** (drew 0.722 vs eps 0.2) -> `A86` — BLOCKER: an EARLY gfx stall now prevents reaching the drift onset at all. Trajectory of a degrad
- roll #29: **EXPLOIT** (drew 0.987 vs eps 0.2) -> `A80` — THE LIVE QUESTION, restated after A77/A78. Standing measurements: the walker's entry sp descends
- roll #30: **EXPLOIT** (drew 0.903 vs eps 0.2) -> `A95` — THE FRONTIER: the transition to the title screen emits no graphics tasks. Established: the white
- roll #31: **EXPLOIT** (drew 0.662 vs eps 0.2) -> `A95` — THE FRONTIER: the transition to the title screen emits no graphics tasks. Established: the white
- roll #32: **EXPLOIT** (drew 0.968 vs eps 0.3) -> `A99` — New failure, highly reproducible: SIGSEGV in the scene walker on THREAD 3 while walking the titl
- roll #33: **EXPLOIT** (drew 0.712 vs eps 0.3) -> `A99` — New failure, highly reproducible: SIGSEGV in the scene walker on THREAD 3 while walking the titl
- roll #34: **EXPLORE** (drew 0.165 vs eps 0.3) -> `A97` — Audio runs and produces PURE SILENCE — user-reported, now quantified. TASK: find why. First step
- roll #35: **EXPLOIT** (drew 0.576 vs eps 0.3) -> `A99` — New failure, highly reproducible: SIGSEGV in the scene walker on THREAD 3 while walking the titl

> **Note on #35 (added 2026-08-19, T37).** Roll #35 was **accidental** — it was
> produced by `scripts/route.py --help`, a flag the script did not have, which
> was silently ignored so the script took the no-argument path and rolled.
> It landed on EXPLOIT/A99 and thereby discarded roll **#34's pending
> EXPLORE -> A97**, which had not been worked yet.
>
> **Resolution: #34 stands, #35 is void.** Not because #35's target is
> unwelcome, but because accepting it would launder an unconsumed EXPLORE into
> an EXPLOIT — the precise bias this log exists to make visible (T14, T31:
> observed explore rate 13% against a nominal 20%). The next roll is **#36**.
>
> `route.py` now refuses unrecognised arguments instead of rolling.
- roll #36: **EXPLORE** (drew 0.294 vs eps 0.3) -> `T11` — 296 symbols leave an unclaimed gap (vram + size < next vram) — the BC-2 lead list. Most are genu
- roll #37: **EXPLOIT** (drew 0.404 vs eps 0.3) -> `A99` — New failure, highly reproducible: SIGSEGV in the scene walker on THREAD 3 while walking the titl
- roll #38: **EXPLOIT** (drew 0.871 vs eps 0.3) -> `A99` — New failure, highly reproducible: SIGSEGV in the scene walker on THREAD 3 while walking the titl
- roll #39: **EXPLORE** (drew 0.077 vs eps 0.3) -> `A96` — RE-COSTED 2026-08-19 (was cost=5): the sweep is now scripts/truncation_sweep.py and the lead lis
- roll #40: **EXPLOIT** (drew 0.738 vs eps 0.3) -> `A99` — New failure, highly reproducible: SIGSEGV in the scene walker on THREAD 3 while walking the titl
- roll #41: **EXPLOIT** (drew 0.492 vs eps 0.3) -> `A99` — >>> READ A106 FIRST (2026-08-19): the framing below is WRONG. This is a ONE-SHOT walk at t157, n
- roll #42: **EXPLORE** (drew 0.061 vs eps 0.3) -> `B36` — Re-anchored: this cited B35, which has never existed in this ledger (T21). The entry that actual
- roll #43: **EXPLORE** (drew 0.156 vs eps 0.3) -> `T11` — RE-COSTED 2026-08-19 by roll #36 (was cost=4; EXPLORE, one bounded check) — the "296" was never 
- roll #44: **EXPLORE** (drew 0.277 vs eps 0.3) -> `A53` — RE-SCOPED once the leak-hunt framing collapsed (see A80). Item (1) "leak is in the runtime/hook 
- roll #45: **EXPLOIT** (drew 0.688 vs eps 0.3) -> `A99` — >>> READ A106 FIRST (2026-08-19): the framing below is WRONG. This is a ONE-SHOT walk at t157, n
- roll #46: **EXPLORE** (drew 0.175 vs eps 0.3) -> `A103` — Strategic question raised by A102: guard-by-guard, or root cause? The title-screen scene walk hi
- roll #47: **EXPLORE** (drew 0.213 vs eps 0.3) -> `A99` — >>> 2026-08-19 (roll #45) READ A110, A111, A112 FIRST, THEN A106. A106 is corrected by A112 — it
- roll #48: **EXPLOIT** (drew 0.958 vs eps 0.3) -> `A103` — BOUNDED CHECK 2026-08-19 (roll #46): the strategic question stands, the factual premise is REFUT
- roll #49: **EXPLORE** (drew 0.063 vs eps 0.3) -> `A97` — Audio runs and produces PURE SILENCE — user-reported, now quantified. TASK: find why. >>> THE FI
- roll #50: **EXPLOIT** (drew 0.354 vs eps 0.3) -> `A99` — >>> 2026-08-19 (roll #45) READ A110, A111, A112 FIRST, THEN A106. A106 is corrected by A112 — it
- roll #51: **EXPLOIT** (drew 0.836 vs eps 0.3) -> `A99` — >>> 2026-08-19 (roll #45) READ A110, A111, A112 FIRST, THEN A106. A106 is corrected by A112 — it
- roll #52: **EXPLOIT** (drew 0.619 vs eps 0.3) -> `A99` — >>> 2026-08-19 (roll #45) READ A110, A111, A112 FIRST, THEN A106. A106 is corrected by A112 — it
- roll #53: **EXPLORE** (drew 0.082 vs eps 0.3) -> `A96` — BOUNDED CHECK 2026-08-19 (roll #39, EXPLORE): the top candidate is a REAL truncation, and the ga
- roll #54: **EXPLOIT** (drew 0.305 vs eps 0.3) -> `A99` — >>> 2026-08-19 (roll #45) READ A110, A111, A112 FIRST, THEN A106. A106 is corrected by A112 — it
- roll #55: **EXPLOIT** (drew 0.747 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #56: **EXPLOIT** (drew 0.308 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #57: **EXPLORE** (drew 0.038 vs eps 0.3) -> `A124` — The walk carries THREE PARALLEL ARRAYS, all indexed by one child byte, and NONE of them is bound
- roll #58: **EXPLORE** (drew 0.033 vs eps 0.3) -> `T11` — ovlfile12 is never loaded in the reachable window. SNP_OVL=1, 45s autostart, VERDICT=CLEAN: 37 o
- roll #59: **EXPLOIT** (drew 0.723 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #60: **EXPLORE** (drew 0.123 vs eps 0.3) -> `B36` — BOUNDED CHECK 2026-08-19 (roll #42): the tool RUNS and its output is self-consistent, but the va
- roll #61: **EXPLOIT** (drew 0.750 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #62: **EXPLORE** (drew 0.246 vs eps 0.3) -> `A97` — >>> ROLL #49 (2026-08-19) ANSWERED THE 'NEXT STEP' BELOW — read A116 first. SIG0 is the YIELD-RE
- roll #63: **EXPLOIT** (drew 0.498 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #64: **EXPLOIT** (drew 0.565 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #65: **EXPLORE** (drew 0.132 vs eps 0.3) -> `A97` — >>> ROLL #49 (2026-08-19) ANSWERED THE 'NEXT STEP' BELOW — read A116 first. SIG0 is the YIELD-RE
- roll #66: **EXPLOIT** (drew 0.811 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #67: **EXPLOIT** (drew 0.742 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #68: **EXPLOIT** (drew 0.846 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #69: **EXPLORE** (drew 0.080 vs eps 0.3) -> `A96` — DO NOT APPLY THE OLD TWO-OVERLAY FIX. func_800E4780 is defined in 23 overlays. The symbol file d
- roll #70: **EXPLOIT** (drew 0.781 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #71: **EXPLOIT** (drew 0.986 vs eps 0.3) -> `A99` — SIGSEGV in the scene walker on THREAD 3, walking the title scene. One-shot at t157, not per-fram
- roll #72: **EXPLORE** (drew 0.066 vs eps 0.3) -> `A97` — >>> ROLL #49 (2026-08-19) ANSWERED THE 'NEXT STEP' BELOW — read A116 first. SIG0 is the YIELD-RE
- roll #73: **EXPLORE** (drew 0.036 vs eps 0.3) -> `A96` — DO NOT APPLY THE OLD TWO-OVERLAY FIX. func_800E4780 is defined in 23 overlays. The symbol file d
- roll #74: **EXPLORE** (drew 0.029 vs eps 0.3) -> `A97` — >>> ROLL #49 (2026-08-19) ANSWERED THE 'NEXT STEP' BELOW — read A116 first. SIG0 is the YIELD-RE
