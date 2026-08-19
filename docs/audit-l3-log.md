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

