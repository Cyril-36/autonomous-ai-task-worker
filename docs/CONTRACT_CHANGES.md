# Contract changes

`worker/contracts.py` and `docs/INTERFACES.md` §1 are the contract between the backend and the
console. The project rule is that both change together in one commit titled `contract: …`.
Two changes were made in ordinary commits instead; this file records them and the commit that
reconciles them.

| Date | Change | Made in | Compatibility |
| --- | --- | --- | --- |
| 2026-10-04 | Removed `ToolCall` and `ToolResult` from `worker/contracts.py`. Neither was used by the backend or the console: tool calls travel as provider dicts, results as `step` event data. | `1affdc4` (ordinary commit) | No wire change. |
| 2026-10-04 | `question` event data gained optional `candidates: string[]` and `suggested: string` (`docs/INTERFACES.md` §1; console `Question` type). `suggested` is a remembered earlier choice and is never applied automatically. | `29108ee` (ordinary commit) | Additive and optional; older clients ignore the fields. `RunEvent.data` is a dict in `contracts.py`, so no Python type changed. |
| 2026-10-04 | Added authenticated `GET /api/runs/{run_id}/exports/{name}` and optional `EvidenceItem.download_url` for a verified, run-owned CSV. | This `contract:` commit | Additive; older clients still show the evidence path as text. |
| 2026-10-04 | Added `GoalType.sync_existing_invoice`, a source-backed correction of one existing invoice. | This `contract:` commit | Additive enum value; older clients need a display fallback. |
| 2026-10-04 | Added optional `paused` to `step` event data, so the console shows a step that waits for an approval or an answer as a wait, not a failure. | `contract:` commit with the console change | Additive and optional; older clients show the step as before. |

Both are reconciled in the `contract:` commit that adds this table.
