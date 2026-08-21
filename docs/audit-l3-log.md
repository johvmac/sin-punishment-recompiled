# L3 audit log

Weekly reviews. Each reads ONLY the L2 digests in `audit-l2-log.md`.

## L3 #1 — covering L2 digests 1..1
- L2 digests reviewed: 1
- ~~**defects per digest: 118.0 -> 0.0 — FALLING**~~ **VOID: a direction asserted from a SINGLE digest.** The window was split in half regardless of size, so the empty second half scored 0 and the tool reported a fall. Corrected the same day; L3 now refuses a direction below 2 digests. The correct line for this block is: defects this digest: 118, no trend claimed.
- no class recurred across this window
- quiet: yes (streak 1)
- **L3 asks whether the METHOD is improving, not whether any finding is right.** If a class recurs after a fix, the fix was aimed at an instance.

## L3 #2 — covering L2 digests 2..2
- L2 digests reviewed: 1
- defects this digest: 0. **NO TREND CLAIMED — a direction needs at least 2 digests.**
- no class recurred across this window
- quiet: yes (streak 2)
- **L3 asks whether the METHOD is improving, not whether any finding is right.** If a class recurs after a fix, the fix was aimed at an instance.

## L3 #3 — covering L2 digests 3..3
- L2 digests reviewed: 1
- defects this digest: 2. **NO TREND CLAIMED — a direction needs at least 2 digests.**
- **classes that RECUR despite tooling — a fix that addressed an instance, not the class:**
  - `churn`: recurred in L2 #3
  - `single-run`: recurred in L2 #3
- quiet: yes (streak 3)
- **L3 asks whether the METHOD is improving, not whether any finding is right.** If a class recurs after a fix, the fix was aimed at an instance.

## L3 #4 — covering L2 digests 4..7
- L2 digests reviewed: 4
- **defects per digest: 0.5 -> 14.5 — RISING** (over 4 digests)
- **THIS DIRECTION IS CONFOUNDED — do not read it as progress.** A falling count cannot be told apart from having stopped noticing, and better discipline RAISES the count first (self-correction and error are the same signal). Only a fall in USER-CAUGHT defects would be unambiguous, and the ladder does not yet separate those (T100).
- **classes that RECUR despite tooling — a fix that addressed an instance, not the class:**
  - `churn`: recurred in L2 #6
  - `no-control`: recurred in L2 #6
  - `no-evidence`: recurred in L2 #6, #7
  - `single-run`: recurred in L2 #5, #6, #7
- quiet: no (streak 0)
- **L3 asks whether the METHOD is improving, not whether any finding is right.** If a class recurs after a fix, the fix was aimed at an instance.

