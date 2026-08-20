# Retrospective — 2026-08-20 (one-off L4 pass)

**User-directed; no roll consumed.** This deliberately violates the audit
ladder's read-only-the-level-below cost rule — it is a one-off, not a precedent.

**Conflict of interest, stated:** the auditor wrote the work being audited, and
the record shows the user catching errors the auditor did not. Method used to
compensate: every count below is extracted from the ledger, route log, run log,
audit logs, or git — never from recollection. Prose interprets; it does not
assert anything a table doesn't support. Judgements are marked as judgements.

Numbers as of this pass: **294 ledger entries** (37 WD, 7 corrected-in-part,
27 EST, 9 CLOSED), **104 rolls** (69 EXPLOIT / 35 EXPLORE, no gaps),
**93 logged runs** (33 crashed-as-expected, 28 clean, 14 degraded, 10 unknown
for lack of SNP_HEARTBEAT, 3 contaminated, 5 legacy-unrecorded), **105
T-entries**, **17 I-entries**.

---

# PART I — The A99 narrative

## The bottom line, first

A99 has consumed **40 of 104 rolls (38%)** and ~50 ledger entries (~17%) across
three days (2026-08-18 → 20). Of those ~50 entries, **~15 are withdrawn or
corrected-in-part (~30%)**. The user's sense that it has been "running in
circles" is correct, but the circling is **localized**: the fault was
characterized precisely within a day (A102/A122), and the waste concentrates in
**one false premise that stood from roll #84 to roll #103 (~15 rolls)** while a
sequence of individually well-controlled experiments ran on top of it.

The bug is still open. What is genuinely established is listed at the end of
this part; it is substantial.

## Act structure

### Act 0 — Discovery, and two wrong answers on day one (Aug 18; A99–A102)

Crash found: SIGSEGV at t≈158 s, thread "[Game] 3". First explanation — "NULL
dereference" (A100) — was **wrong within hours**: derived from a misaligned
`x/i` disassembly and a wrong assumption about which register held the rdram
base. A101 dismissed a probe that had *actually caught the fault* because two
threads' counts were conflated.

**A102 fixed both and still stands:** the value is a non-zero garbage pointer
`0x02000000`, dereferenced because the game's own guard tests only for zero.
*Pattern set on day one: observations survive; inferences around them die.*

### Act 1 — The static descent (Aug 19; A105–A121, ~rolls 38–50)

m2c-driven chain tracing from the walker's argument into overlay data:
identified the scene overlay (ovlfile25, A120), proved residency and
single-load (A121), proved the node arrays structurally perfect (A110).
Four entries lost their inferential halves same-session (A105, A109, A112,
A115) — **every static READ survived; every mechanism guessed on top of one
died.** Cheap deaths: caught by the falsifier-stating habit, mostly same-day.

### Act 2 — The target moves (A122)

gdb on the debug build read the fault directly: the faulting address is
**heap, `obj+8` = `0x8013C278`** — not overlay data. The whole Act-1 framing
(bad static data) was for the *outermost* call; the crash is ~4 recursion
levels in, after `$s0` has been reassigned. **Act 1's conclusions weren't
wrong, but they answered a different question than the crash was asking.**
Roughly 8 rolls had been spent on the wrong layer — not knowably wrong at the
time, but worth counting.

### Act 3 — The stack that lied (rolls 57–64; A125–A132) — **Circle #1**

Four self-consistent, mutually incompatible readings of the fault-time stack
(A125, A128, A130, A132). Root cause of the circle: **an RDRAM snapshot cannot
distinguish a live frame from a leftover** (T69), and gdb's backtrace is not a
recursion depth here. A130's "corruption" story was refuted by A132: three
walker frames, no corruption. Cost: ~5 rolls. Broken by a *principle*, not by
more data: call chains must be established by logging entry arguments, where a
leftover cannot appear — which became `gdb_trace.sh`.

### Act 4 — The wrong crash (rolls 67–87; A136–A142, A159–A160)

A second, unrelated crash (the SP-yield assert) intercepted ~4 in 10 runs and
contaminated negatives (T72: a negative from a run that didn't reproduce the
event is not a negative). A138 inferred causation from n=1 vs n=1 and was
withdrawn. A142 root-caused the yield crash statically; A159 formally declared
A99 unmeasurable until it was fixed; **A160 fixed and shipped it — the
project's first behaviour change in days, and a real, durable win that came out
of the A99 hunt as collateral.**

### Act 5 — The overrun that wasn't (interleaved, rolls 61–92; A126–129, A148, A153, A163, A165, A168)

The 18-entry vtable sits directly below the overlay table, so "dispatch runs
off the end" was attractive. It was killed *properly*: all three dispatch
sites measured, each with a condition derived from its own targets (after
A163's borrowed-range lesson produced 77k meaningless hits), each repeated —
`:300` twice (0.43% agreement), `:436` twice (1.5%), `:598` twice. **~6 rolls,
zero hits across ~600k cumulative dispatches.** Expensive, but these are real
negatives with controls, and the hypothesis is banned in the handoff so it
cannot be re-proposed. This is what honest exhaustion looks like.

### Act 6 — The paradox declared (rolls 70–88; A140/A141/A148 vs A157) — **Circle #3 begins**

A157 statically enumerated the walker: `$s0` written in exactly two places,
straight-line prologue, one return — and concluded three runtime measurements
"cannot all be right." The right instinct (attack the inconsistency) attached
to the wrong object: it **dismissed A141's measurement** via a reach-count
comparison that A166 later showed was an across-arm-window artifact. A141 was
right. **A dismissal was made on a lower evidence bar than the claim it
dismissed** — the first of two times this happened to the same entry.

### Act 7 — The same-run era (rolls 90–104, Aug 20; A166–A184)

The two-site tool (T81) ended across-run comparison, and the experiments were
individually clean — positive controls on conditions, exact-value pairing,
whole-run arming, thread logging. They demolished, in order: the A140/A148
"conflict" (different frames — A166), sp-as-frame-identity (A173, correcting
three entries), line-table attribution (A177), thread confusion (A178), and
finally the epilogue-restore path at 209,649 reaches (A180 — **A141 vindicated
a second time**).

At which point every possibility *inside the frame* was excluded, and the frame
itself broke (A183): **"exactly two writers" had been counted inside one
function, but `ctx` is one struct per thread — 9,199 write sites exist, and
every callee writes `$s0`.** The "paradox" was the expected behaviour of a
shared register, misread as an impossibility for ~15 rolls. A184 then cut
9,199 down to **194 functions that clobber `$s0` without restoring it**, and
cleared `:436`'s main-segment targets against that list.

### Where it stands (judgement, marked as such)

For the first time since A122 moved the target, the question is plausibly
*well-formed*: **which callee, reached under the walker's dispatches or
transitively, leaves `$s0` pointing into the object array?** Two cheap,
decisive next steps are already recorded: log the `:436`/`:598` target
addresses and cross them against the 194 (one run), or build the watchpoint
mode (the only enumeration-free instrument).

## The three circles, compared

| circle | span | cost | root cause | what broke it |
|---|---|---|---|---|
| Stack readings | A125–A132 | ~5 rolls | snapshot can't tell live from leftover | a principle (T69) + a tool |
| Vtable overrun | A126–A168 | ~6 rolls | attractive hypothesis, fragmented negatives | full enumeration + repeats + a ban |
| Closure paradox | A157–A183 | **~15 rolls** | **false premise, never re-examined** | premise finally attacked (A180→A183) |

**The common structure:** every experiment inside each circle was disciplined —
controls, repeats, scoped claims. The discipline system polices *measurements*
and *instruments*. **Nothing in it polices premises or question-framing**, and
that is where all three circles lived. Circle 3 is the purest case: the
moment an "impossible" result appeared (A157, roll #84), the correct move was
to enumerate the premises and attack the least-verified one; instead, six more
experiments ran under the premise, each excluding another *possibility within
it*. The premise itself — "two writers" — was checked only at roll #103, and
fell in two greps.

Secondary lesson, paid twice by the same entry: **A141 was dismissed twice on
plausibility arguments and vindicated twice by measurement.** Dismissing a
measured claim currently requires less evidence than making one.

## What A99 has actually established (the asset list — all with controls, all standing)

1. **Fault mechanism, exactly:** `*(obj+8) = 0x02000000`, dereferenced through
   a zero-only guard; `obj = 0x8013C270`; thread 63 (A102/A122/A162).
2. **Reproduction, two paths, same registers**, on video: t≈158 s no-input,
   ~45–55 s post-START (A162, A164).
3. **Scene neighbourhood measured:** ~10 s of title screen, then fully black
   ~0.7–1.0 s, then the fault. Scene formally unidentified (A164).
4. **The overlay:** ovlfile25, resident, loads exactly once (A120/A121).
5. **All three dispatch families in-range, each repeated** (A153/A163/A165/A168).
6. **The walker itself:** two `$sp` writes, two `$s0` writes in-body,
   straight-line prologue, one return — static claim now empirically supported.
7. **The descent:** two distinct walks in the final seconds; the fatal pair
   walks `0x8013C27x` objects; parent→child handover read directly
   (`$s0`-before-assignment) without using sp (A172/A176 surviving halves).
8. **The mechanism class, sized:** 194 non-restoring `$s0` writers; `:436`
   main-segment targets clean (A184).
9. **Collateral:** the yield crash root-caused, fixed, shipped (A142/A160).

---

# PART II — Whole-project practice audit

## Where progress actually came from

The project has **root-caused three crashes and shipped or verified fixes for
them**: the attract freeze (A1; mitigation verified to 2650+ s), the START
crash (B53, class BC-2 "declared too short"), and the yield crash (A160,
shipped 2026-08-19, four structural predictions stated before the recompile).
Plus smaller confirmed fixes (A80's truncated symbol, user-confirmed; B67's
swapped framebuffer symbols). A97 is decoded to a specific malformed recompile
config with three named blockers; A99 is characterized as above.

Practices traceable to those wins (judgement, but each is cited in the win's
own entry):

* **Bug-class recognition** (BC-1..4): B53 and A80 were solved *as instances
  of a class*, cheaply, after the first instance was paid for in full.
* **Static-first reading with m2c, cross-checked live:** the highest
  survival-rate evidence type in the ledger (Act 1's READs all stand).
* **Controls that can fail:** caught the RDRAM byte-swap (A179), the
  pw-record silence (T102), the dead condition (A172's positive control) —
  each *before* a wrong conclusion shipped. Post-T71, no instrument error has
  reached a recorded conclusion; pre-T71, at least five did (T60/62/63/64/66).
* **Run recording** (T83): produced A164, refuted A161, enabled the observed-run
  policy.
* **User observation** (T101): refuted A169 on its first use; the user's ears
  plus a three-trial null control resolved the startup-blip attribution in
  under an hour.
* **Same-run comparison** (T81): dissolved a "contradiction" two entries had
  been built on.
* **eps-greedy routing:** EXPLORE rolls found stale/dead items historically and
  delivered both of today's A97 breakthroughs (A174, A179 were EXPLORE rolls).

## Failure census (all 37 WD + correction chains, classified)

| class | recorded incidents | checker today? | recurred after its checker existed? |
|---|---|---|---|
| Inference beyond evidence / quantifier too wide | ~14 (A100, A109, A112, A115, A161, A39/66/72/74/75 family, B41/B46…) | partial (negatives-must-name-scope) | yes — A161 postdates the rule |
| Instrument trusted unmeasured | ~12 (I1–I17 overlap, T60/62/63/64/66, A101) | **T71 three gates** | **no conclusion-reaching escape since** |
| Scope error (T40 class: predicate narrower than claim) | ~8 (A56/A111, A148→A152, T90, T95, A182, A183) | none general | **yes — three today** |
| Premise/framing error | newly named (A183; arguably A125 family) | **none** | n/a |
| Cross-run composition | 3 (A157's dismissal, A164's stills confusion, A179/A182) | none (T57 is prose) | yes |
| Causation from coincidence | 2 (A138, B46) | none | rare |
| Citation rot (dangling/withdrawn) | ~6 | yes, two checks | caught same-day now (3 catches today) |
| Process omission (inventory, --help, /tmp) | 3 clusters (T37, T89/90, T95) | yes (lint_tools ×3 checks) | no |
| Fabrication | 1 (T91) | witness (T98) | none since |

**Reading of the table (judgement):** the classes with mechanical checkers have
stopped recurring or are caught same-day. The classes still recurring —
scope errors, cross-run composition, premise errors — are exactly the ones
where the rule exists only as prose. T57 ("name the composing step") is the
starkest: written, cited, and violated at least twice afterwards.

## Who caught what (from explicit attributions in the record)

* **The user:** ≥8, including several of the worst — A93, A161 (both scene
  quantifiers), the A169 refutation (heard audio), the startup-blip insistence
  that forced the null control, the run-length overgeneralization, route.py's
  fake cost ranking, the handoff cadence misuse (T92), and the "have you been
  writing this up?" prompt that produced T95/T96/T105.
* **Checkers/tools:** ≥10 today alone (citation checks ×3, lint_tools ×2,
  rdram_peek's byte-order control, route discrimination test, ragged-row guard,
  audit L1 single-run flags ×2 — both of which led to real repeats).
* **Random EXPLORE rolls:** 2 recorded (stale splat config; unwritten entry).
* **Self, same-session:** 12 entries carry same-day corrections — the healthiest
  number in this section, and it has risen over time.

## Discipline effectiveness (each standing mechanism, one line)

| mechanism | verdict | evidence |
|---|---|---|
| T71 tool gates | **working** | 4/4 instrument errors today caught pre-conclusion |
| check_ledger citation checks | **working** | 3 same-day catches today |
| write-time single-run (T99) | **working** (behaviour-shaping) | A167/A168/A170 all ran second runs |
| roll witness (T98) | untested against its threat | no fabrication since; cheap to keep |
| observed runs + audio capture (T101/T102) | **high yield** | refuted A169 on first use |
| audit ladder L1 | working | 2 flags → 2 real repeats |
| audit ladder L2/L3 | mixed | surfaced recurrence; own defect (T93) found only by review |
| guards (launch/desktop/recording) | working | zero desktop leaks since T59; one over-broad refusal (acceptable) |
| negatives-name-scope | **paid off visibly** | A169's caveat made its refutation a refinement, not a crisis |
| T57 composing-step rule | **prose-only, failing** | violated ≥2× after being written |
| routing + eps | working | see progress section |

---

# PART III — Ranked fixes (proposed, none applied)

Ranked by (incidents it would have prevented ÷ cost). Costs are judgements.

1. **The impossible-result rule (premise audit).** When a checkpoint concludes
   "these measurements cannot all be right" (or equivalent), the *next*
   checkpoint on that item must enumerate the premises under the contradiction
   and attack the least-verified one — not run another experiment under them.
   Playbook rule + one line in the handoff. *Would have saved ~12–15 rolls in
   Circle 3, likely ~3 in Circle 1.* Cost: an hour.

2. **Instrument-semantics reference.** A short playbook table: what `ctx`
   is (one struct per THREAD — not per frame), what a value read at a
   breakpoint means, that a breakpoint fires *before* its line, sp/frame/thread
   identity rules, sign-extension (I17), snapshot liveness (T69). Grown as
   measured, one line per fact. *The two-writers frame and the sp-pairing both
   die at birth against this table.* Cost: an hour, then maintenance.

3. **`gdb_trace.sh --watch` mode** (T71-gated). A conditional watchpoint on a
   `ctx` field — the only instrument that doesn't require enumerating writer
   sites, and A99's recorded next-best step. Cost: one checkpoint.

4. **`ledger.py --chain <id>`.** Mechanical narrative skeleton: follow an
   entry's correction/citation graph chronologically. This retrospective's
   Part I took hours; the skeleton is derivable in seconds, and circles become
   visible while they are happening. Cost: one checkpoint, plus self-check.

5. **The dismissal bar.** Overturning a MEASURED entry requires evidence at
   the same standard as making one (same-run or same-window); a plausibility
   argument may *flag* but not *dismiss*. A141 was wrongly dismissed twice.
   Prose rule; a checker is possible later (a "CORRECTED by X" where X is not
   MEASURED could warn). Cost: an hour for the prose.

6. **`SNP_HEARTBEAT` default-on in run_game.sh.** 10 of 93 runs have verdict
   UNKNOWN purely for its absence — wasted verdicts. Cost: minutes, plus its
   self-test.

7. **T57 gets a checker or gets demoted.** "Name the composing step" is the
   most-violated prose rule. Either check_ledger warns when an entry combines
   two run-artifacts from different dates without a composing-step marker
   (heuristic, will have false positives), or the rule is folded into the
   entry template so it's structural. Cost: half a checkpoint.

## Limits of this pass

n=1 project; the classifier and the classified are the same agent; "who
caught it" relies on attributions I wrote at the time (the user should
spot-check that column); rolls are a coarse cost unit; and counterfactual
savings ("would have saved N rolls") are estimates, not measurements.
Anything not recorded at the time is treated as unknowable (T47 applies to
memory too).
