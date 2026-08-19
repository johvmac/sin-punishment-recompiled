# SHELVED — Research plan: mechanical enforcement of record integrity in long-horizon agents

> **THIS IS NOT PROJECT WORK.** It is a shelved research plan, written 2026-08-20
> at the user's request during a detour from the recomp. Nothing here is a task,
> a finding, or a commitment. It is in `docs/` so it is versioned and findable,
> not because it is on the critical path. **A future session should not act on
> this unless the user raises it.**
>
> Related, and separate: the process takeaways this detour produced for the
> recomp's own method were recorded in the ledger. This file is the part that
> was set aside.

---

## Conflict of interest, stated first

The system this plan proposes studying was built by the agent writing the plan,
which also assessed it as "ahead of the published work." That assessment is not
independent and should be discounted. The gates below are written to kill the
project cheaply, and that is deliberate.

---

## The research object

Not "prompting for debugging" — that field is crowded and mostly measures
one-shot patch success on curated GitHub issues.

> **In long-horizon agentic empirical work, the binding constraint is not
> reasoning capability but the integrity of the accumulated record — and record
> integrity can be enforced mechanically rather than instructed.**

The recurring one-line form: **a rule with no checker is a preference.**

Instances built in this repo, each of which could be an experimental condition:

* proof-of-execution tokens binding a claimed decision to an actual tool run (T98)
* write-time evidence gating rather than audit-time (T99)
* tiered review where each level reads only the level below's output (the ladder)
* baseline-bounded checkers reporting regressions, not accumulated debt (T94/T97)
* controls required to be *demonstrated failing* before being trusted (T65/T71)
* explicitly named inferential steps marked unverified (T57)

---

## Novelty risk — read this before anything else

Most individual mechanisms have prior art **in a different field**. The
contribution would be *transposition plus evidence*, not invention.

| mechanism | existing home | novelty |
|---|---|---|
| baseline-bounded warnings | static-analysis adoption (Tricorder; "why developers don't use static analysis tools") | **none** — decades old |
| falsifier / named unverified step | preregistration, lab-notebook practice | none |
| tiered review reading only lower output | audit and management theory | none |
| provenance-tracked memory | agent-memory literature | **possibly occupied** |
| proof-of-execution witness | nothing found | plausibly novel, but rare-event |

**Week-one action:** read *From Lossy to Verified: A Provenance-Aware Tiered
Memory for Agents* (arXiv 2602.17913). If it already performs the
agent-self-governance transposition **with evaluation**, novelty drops sharply
— pivot to the measurement contribution or drop the project.

---

## The problem that will sink this if ignored

**Fabrication and over-claiming are rare events.** This project recorded ONE
fabrication (T91) in ~90 rolls. That cannot power a study.

Three options; picking one is the central design decision:

1. **Induce the failure** — stress conditions, ambiguous evidence, token
   pressure. Risk: studying induced rather than natural behaviour.
2. **Study the common failure instead** — over-claiming (scope exceeding
   evidence) is frequent: 21 single-run recurrences plus several caught scope
   errors. Far better statistical footing.
3. **Go retrospective** — mine transcripts at scale. Needs a corpus.

**Recommendation: (2).** Centre the project on over-claiming, not fabrication.
Same underlying phenomenon, actually measurable, happens constantly.

---

## Phases, each ending in a pre-committed kill gate

### Phase 0 — the free dataset (1–2 weeks)

This repo is already a longitudinal record: ~270 ledger entries, 36 withdrawn
**with stated reasons**, plus audit logs, routing logs, and commit history
dating every claim. Retrospectively code every withdrawal by failure type.

**Gate:** do the reasons cluster into stable categories, with a second coder
reaching κ > 0.6 on 50 entries? **If the categories will not stabilise, the
dependent variable does not exist — stop here.** This is the cheapest possible
test of whether the whole idea is measurable.

Phase 0 alone is a defensible short case-study paper even if everything after
it is abandoned.

### Phase 1 — operationalise over-claiming (2–3 weeks)

Rubric: given a recorded claim and the evidence actually gathered, is the
claim's scope wider than the evidence supports? Validate against human labels;
test whether an LLM judge applies it reliably.

**Gate:** judge/human agreement ≥ 0.7. Below that the experiment cannot scale.

### Phase 2 — the ablation (4–6 weeks)

Corpus with **known ground truth** — Defects4J, BugsInPy, or injected faults.
**Not SWE-bench**, given the contamination finding (~94% of instances predate
common training cutoffs).

```
A  bare agent + tools
B  A + a persistent record (no checks)
C  B + write-time evidence gating
D  B + audit-time gating          <-- C vs D is the flagship
E  C + proof-of-execution witness
F  full system
```

**C vs D is the sharpest experiment available**: the *same check*, differing
only in when it fires. The project's claim is that timing is the entire
mechanism — the audit caught single-run claims 21 times and the class never
died. Crisp, falsifiable, cheap, and genuinely uncertain.

**Gate:** does any condition differ from baseline by a reportable margin at
n≈30 tasks × 3 seeds? **Decide NOW whether you would publish "these mechanisms
do not measurably help"** — pre-committing is what prevents p-hacking toward a
positive.

### Phase 3 — cost (1 week)

Overhead in tokens, wall-clock, tool calls. A discipline that doubles cost for
a 5% accuracy gain is a negative result dressed as a positive.

---

## Hypotheses

* **H1 (timing) — flagship.** Write-time gating reduces over-claiming more than
  the identical check applied post-hoc.
* **H2 (persistence).** Uncorrected false claims raise the error rate of *later*
  claims citing them. Tests whether record integrity compounds, which is the
  premise of the whole thing.
* **H3 (bounded alarms).** Compliance falls as standing warning count rises.
  Direct import from static-analysis literature; cheap replication.
* **H4 (verified controls).** Requiring a control to be demonstrated failing
  catches broken instruments that passing-only controls miss. Test by seeding
  deliberately broken probes.
* **H5 (witness).** Lowest priority — rare events, weakest power.

**Primary metric:** over-claim rate per recorded claim.
**Secondary:** final-answer accuracy, claims later withdrawn, cost per bug.

---

## Three-month scope

**Phase 0 + Phase 1 + H1 only.** Drop everything else.

* a coded retrospective of one real long-horizon debugging project
* a validated rubric for claim/evidence mismatch
* one clean ablation on a single hypothesis, known-ground-truth bugs

Target: workshop (LLM4Code, ICSE/FSE workshops) or MSR via the mining angle.
**Not ICSE main track** — that needs the full ablation across multiple projects.

---

## Threats to validity, to be stated rather than discovered by a reviewer

* **n=1 project, and the agent authored its own discipline.** Circular. The
  ablation is what breaks the circularity; do not skip it.
* **Observer effect.** The mechanisms exist because a human was catching errors.
  Isolating mechanism from supervision is genuinely hard.
* **Model drift.** Results may not survive the next model generation. Report
  versions.
* **External validity is the weakest flank.** Defects4J bugs are small and
  self-contained; a SIGSEGV in a recompiled N64 scene walker is not.

---

## Verdict

Viable **if** it studies over-claiming rather than fabrication, and **if** H1 is
treated as the paper. "Discipline helps" is not interesting — everyone nods and
nothing is learned. The sharper claim is: **the same check is effective or
useless depending only on when it fires.** If that holds it matters well beyond
debugging agents; if not, six weeks has bought a real answer.
