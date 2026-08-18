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
