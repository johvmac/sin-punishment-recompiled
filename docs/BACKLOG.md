# Small owed jobs

**For genuine remainder time only.** The frontier comes first, always: this
exists because a session with ten minutes left and no big job that fits used to
close early (T161), not because tidying is worth doing instead of the work.

**Every item here is something already OWED** — a count that drifted, a check
not re-run since its script changed, a flag left unanswered, evidence not yet
preserved. **Nothing invented.** If an item cannot be shown to be done or not
done, it does not belong here.

Written and read by `scripts/backlog.py`. Add with `add`, close with `close`.

| id | opened | status | job | why it is owed |
|---|---|---|---|---|
| B1 | 2026-08-22 | OPEN | The `session-log.md` row for the 12:25 session records 3m27s for a stretch that ran ~20 minutes | Marked unreliable in the file; cause unknown. The obvious explanation (self-check clobbering live state) was checked and ruled out |
| B2 | 2026-08-22 | OPEN | Re-check every inventory row in `diagnostic-playbook.md` that states a control count | The `observed_run.sh` row said 5 when it was 8 (T150 found it, T160 fixed it). One drifted, so the class recurs |
| B3 | 2026-08-22 | OPEN | Adopt the context audit from T163 — run `/context` at session start and drop MCP servers this project never uses | Read and recorded, never acted on |
| B4 | 2026-08-22 | OPEN | Add the subagent CONTEXT-ISOLATION rationale to `docs/agent-brief.md` | T163 found it absent: the brief argues delegation only, and isolation is a separate reason to hand off a bulky read |
| B5 | 2026-08-22 | CLOSED 2026-08-22 | Add `evidence/` to `.gitignore` | A checkpoint wrote three run logs into the repo by accident; they were moved to the archive and the mistake made non-committable |
