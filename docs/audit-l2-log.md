# L2 audit log

Daily digests. Each reads ONLY the L1 blocks in `audit-log.md`. The weekly L3 review reads ONLY this file.

## L2 #1 — covering L1 audits 1..6
- L1 blocks digested: 6
- **defects by class (this window / all prior):**
  - `single-run` (T22): 19 / 0 — **NEW**
  - `no-control` (I1/I13): 41 / 0 — **NEW**
  - `churn` (I14): 35 / 0 — **NEW**
  - `no-evidence` (A24/B35): 23 / 0 — **NEW**
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #2 — covering L1 audits -..-
- no new L1 blocks since the last L2. Nothing to digest.
- quiet: yes (streak 1; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #3 — covering L1 audits 7..7
- L1 blocks digested: 1
- **defects by class (this window / all prior):**
  - `single-run` (T22): 1 / 19 — **recurs**
  - `no-control` (I1/I13): 0 / 41 — **quiet**
  - `churn` (I14): 1 / 35 — **recurs**
  - `no-evidence` (A24/B35): 0 / 23 — **quiet**
- **DID THE FIX HOLD? These classes recurred despite tooling: `single-run`, `churn`.** A class that recurs after a fix means the fix addressed an instance, not the class.
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #4 — covering L1 audits -..-
- no new L1 blocks since the last L2. Nothing to digest.
- quiet: yes (streak 1; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #5 — covering L1 audits 8..8
- L1 blocks digested: 1
- **defects by class (this window / all prior):**
  - `single-run` (T22): 1 / 20 — **recurs**
  - `no-control` (I1/I13): 0 / 41 — **quiet**
  - `churn` (I14): 0 / 36 — **quiet**
  - `no-evidence` (A24/B35): 0 / 23 — **quiet**
- **DID THE FIX HOLD? These classes recurred despite tooling: `single-run`.** A class that recurs after a fix means the fix addressed an instance, not the class.
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #6 — covering L1 audits 9..13
- L1 blocks digested: 5
- **defects by class (this window / all prior):**
  - `single-run` (T22): 14 / 21 — **recurs**
  - `no-control` (I1/I13): 9 / 41 — **recurs**
  - `churn` (I14): 3 / 36 — **recurs**
  - `no-evidence` (A24/B35): 1 / 23 — **recurs**
- **DID THE FIX HOLD? These classes recurred despite tooling: `single-run`, `no-control`, `churn`, `no-evidence`.** A class that recurs after a fix means the fix addressed an instance, not the class.
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #7 — covering L1 audits 14..16
- L1 blocks digested: 3
- **defects by class (this window / all prior):**
  - `single-run` (T22): 1 / 35 — **recurs**
  - `no-control` (I1/I13): 0 / 50 — **quiet**
  - `churn` (I14): 0 / 39 — **quiet**
  - `no-evidence` (A24/B35): 1 / 24 — **recurs**
- **DID THE FIX HOLD? These classes recurred despite tooling: `single-run`, `no-evidence`.** A class that recurs after a fix means the fix addressed an instance, not the class.
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #8 — covering L1 audits 17..17
- L1 blocks digested: 1
- no defects reported in this window
- quiet: yes (streak 1; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #9 — covering L1 audits 18..21
- L1 blocks digested: 4
- **defects by class (raised this window / all prior / FIXED this window / still open):**
  - `single-run` (T22): 1 / 36 / 1 / 0 — **raised, all fixed**
  - `no-control` (I1/I13): 0 / 50 / 0 / 0 — **quiet**
  - `churn` (I14): 0 / 39 / 0 / 0 — **quiet**
  - `no-evidence` (A24/B35): 0 / 25 / 0 / 0 — **quiet**
- every defect raised in this window was FIXED (1 resolved, 0 still open). **Found-and-fixed is the loop working, not a recurrence.**
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #10 — covering L1 audits 22..22
- L1 blocks digested: 1
- **defects by class (raised this window / all prior / FIXED this window / still open):**
  - `single-run` (T22): 0 / 37 / 0 / 0 — **quiet**
  - `no-control` (I1/I13): 0 / 50 / 0 / 0 — **quiet**
  - `churn` (I14): 1 / 39 / 0 / 0 — **recurs**
  - `no-evidence` (A24/B35): 0 / 25 / 0 / 0 — **quiet**
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #11 — covering L1 audits 23..23
- L1 blocks digested: 1
- no defects reported in this window
- quiet: yes (streak 1; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #12 — covering L1 audits 24..25
- L1 blocks digested: 2
- **defects by class (raised this window / all prior / FIXED this window / still open):**
  - `single-run` (T22): 0 / 37 / 0 / 0 — **quiet**
  - `no-control` (I1/I13): 0 / 50 / 0 / 0 — **quiet**
  - `churn` (I14): 2 / 40 / 0 / 0 — **recurs**
  - `no-evidence` (A24/B35): 0 / 25 / 0 / 0 — **quiet**
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.


**ANSWER to #12's question — yes, `churn` IS the broader-than-evidence class
this window, and it is already diagnosed rather than merely counted.** Both
churn entries trace to one root: **an absence read from an instrument that could
not have seen a presence.** T207 (created and withdrawn inside an hour) claimed
the user's status page had no input controls, from a grep of static HTML for
buttons that are built client-side. A455's coverage script reported `.main` as
100% named because its pattern missed `main_func_`; that one was caught by the
number being implausible, which is luck, not a control.

**The mechanical trace L2 says this failure does not leave — it partly does, and
it is this class recurring.** The candidate rule, logged in
`docs/protocols-draft.md` rather than promoted: *a checkpoint reporting an
ABSENCE must name the instrument and state what a positive would have looked
like, inside the entry.* Both would have been caught by it before writing.

Not proposing a checker yet: the rule has been applied deliberately exactly once
(the status-page publish, where the positive control failed and stopped a
mistake before it happened). One success is not grounds for automation.
## L2 #13 — covering L1 audits 26..27
- L1 blocks digested: 2
- **defects by class (raised this window / all prior / FIXED this window / still open):**
  - `single-run` (T22): 0 / 37 / 0 / 0 — **quiet**
  - `no-control` (I1/I13): 0 / 50 / 0 / 0 — **quiet**
  - `churn` (I14): 1 / 42 / 0 / 0 — **recurs**
  - `no-evidence` (A24/B35): 0 / 25 / 0 / 0 — **quiet**
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #14 — covering L1 audits -..-
- no new L1 blocks since the last L2. Nothing to digest.
- quiet: **n/a — NOTHING WAS DIGESTED, so this is not evidence of calm.** Streak HELD at 0. L1 is behind; run `scripts/audit.py`.
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #15 — covering L1 audits 28..33
- L1 blocks digested: 6
- **defects by class (raised this window / all prior / FIXED this window / still open):**
  - `single-run` (T22): 0 / 37 / 0 / 0 — **quiet**
  - `no-control` (I1/I13): 2 / 50 / 2 / 2 — **UNRESOLVED**
  - `churn` (I14): 0 / 43 / 0 / 0 — **quiet**
  - `no-evidence` (A24/B35): 1 / 25 / 1 / 0 — **raised, all fixed**
  - `under-explore` (T14): 1 / 0 / 0 / 0 — **NEW**
- **DID THE FIX HOLD? These classes have instances STILL OPEN: `no-control`.** A class that stays open after a fix means the fix addressed an instance, not the class.
- quiet: no (streak 0; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #16 — covering L1 audits 34..36
- L1 blocks digested: 3
- no defects reported in this window
- quiet: yes (streak 1; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

## L2 #17 — covering L1 audits 37..38
- L1 blocks digested: 2
- no defects reported in this window
- quiet: yes (streak 2; at 2, drop L2 to weekly)
- **L2 is a digest for a human, not a verdict.** The failure that dominates here — a claim broader than its evidence — leaves no mechanical trace. Scan the classes above and ask whether any of them is that.

