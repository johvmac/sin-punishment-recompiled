# Trial 2 scoring key — WRITTEN AND COMMITTED BEFORE ANY RESULT WAS SEEN

**2026-08-22.** T157 round 2, adding Fable 5 and Opus 5 to the Haiku 4.5 /
Sonnet 5 comparison. Committed ahead of the run for the same reason `route.py`
has a witness: criteria invented after seeing the output are not criteria (T91).

## Ground truth (T157's own fix: seed from measured fact, not my source reading)

Trial 1's seeded control was VOID because one of the two instances I seeded it
with was wrong. This key uses:

1. **A measured crash, twice.** Setting `View Framebuffer` to 0 in the tutorial
   SIGSEGVed the run on 2026-08-22, on two independent attempts (A310).
2. **A human-verified finding.** A317 — I checked it myself with 6 targeted
   reads before it entered the ledger.

## The key

| # | criterion | why it is the discriminator |
|---|---|---|
| 1 | Reports `rt64_workload_queue.cpp:510` (or its 510-512 loop) | the site the measured crash implicates |
| 2 | Classifies it **UNGUARDED** | **THE ONE THAT MATTERS.** Haiku 4.5 found it and called it GUARDED. Retrieval was never the hard part |
| 3 | Finds the other three loops on the same bound — `:599`, `:615`, `:709` | depth; 0-3 |
| 4 | Identifies that the clamp is against a **DIFFERENT `Workload` object** than the use | the actual mechanism; the thing I did not have before trial 1 |
| 5 | Asserts a blanket absence ("no unguarded accesses found") | **automatic disqualification of the report's negatives.** Haiku did this on code that had crashed twice that morning |
| 6 | Verification cost: targeted reads I need to check its claims | the economic number. Trial 1 Sonnet = 6 |
| 7 | Noise: reported hits that do not survive checking | counted, because it is a cost |

**PASS = 1 AND 2.** Everything else is depth, not pass/fail.

## Known confound, stated before the run

`docs/agent-brief.md` **gained a Part 1 after trial 1** which discusses the
trial itself and would leak the answer. Trial 2 agents are told to read **Part 2
only**. That is a prompt delta from trial 1 and the comparison is not perfectly
clean. The alternative — letting them read the answer — is worse.

Everything else in the prompt is **verbatim from trial 1**.

## What would make the tier premium worth paying

Not "finds more". **Fewer of my reads per surviving finding**, or catching
criterion 4 where a cheaper model does not. If a costlier model returns the same
verdicts at the same verification cost, the premium buys nothing here and the
answer is to keep using the cheaper one.
