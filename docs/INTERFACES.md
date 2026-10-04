# Interfaces

The console (`console/`) and the backend (`worker/`, `sandbox/`, `evals/`, `config/`) were built in parallel against this contract. Types live in `worker/contracts.py`; this file fixes the wire format.

- **§1 is frozen.** Both sides build against it. Change it only by editing this file and `worker/contracts.py` together and telling the other side.
- §2–§3 are backend-internal and may be refined; keep them in sync here.

All JSON uses snake_case. Datetimes are ISO 8601 UTC with `Z`. Money is a decimal **string** with two places (`"48250.00"`), never a float.

---

## §1 Console API (frozen) — served by the backend on `http://127.0.0.1:8100`

The frontend is a static SPA. In development it runs on Vite (`:5173`) and proxies `/api` to `:8100`. In production the backend serves `console/dist/` at `/` and falls back to `index.html` for unknown non-`/api` paths.

### Errors
Every non-2xx response is `{"error": {"code": "<snake_case>", "message": "<human readable>"}}`.

| Status | Codes used |
| --- | --- |
| 401 | `not_signed_in`, `bad_credentials` |
| 403 | `forbidden` (e.g. another user's run, approving without rights) |
| 404 | `not_found` |
| 409 | `conflict` (e.g. answering a run that isn't awaiting input; deciding an approval that isn't pending), `approval_expired` |
| 422 | `invalid_request` |
| 429 / 402 | `budget_exhausted` (global spending limit reached; new runs refused) |

### Session (cookie `console_session`, HttpOnly, SameSite=Lax)
| Method & path | Body | Response |
| --- | --- | --- |
| `GET /api/demo-users` | — | `200 DemoUser[]` (unauthenticated; used by the sign-in picker) |
| `POST /api/session` | `{"email": str, "password": str}` | `200 Principal` + cookie · `401 bad_credentials` |
| `GET /api/me` | — | `200 Principal` · `401 not_signed_in` |
| `DELETE /api/session` | — | `204` |

`DemoUser = {email, display_name, role, assigned_suppliers: string[], password_hint: string}`. Demo passwords are sandbox-only and documented in the README.

### Runs
Visibility: operators see only runs they started; admins see all. Every endpoint below returns `403 forbidden` for a run the caller can't see.

| Method & path | Body | Response |
| --- | --- | --- |
| `GET /api/examples` | — | `200 [{"title": str, "request": str, "notes": str}]` (task suggestions) |
| `GET /api/runs` | — | `200 RunSummary[]`, newest first |
| `POST /api/runs` | `{"request": str}` (1–2000 chars) | `201 RunSummary` · `422` · `402 budget_exhausted` |
| `GET /api/runs/{run_id}` | — | `200 RunDetail` |
| `GET /api/runs/{run_id}/events?after={seq}` | — | `200 RunEvent[]` with `seq > after`, ascending |
| `GET /api/runs/{run_id}/stream` | header `Last-Event-ID` optional | `text/event-stream` (below) |
| `POST /api/runs/{run_id}/answer` | `{"text": str}` | `202` · `409 conflict` unless `awaiting_input` |
| `POST /api/runs/{run_id}/approvals/{approval_id}` | `{"decision": "approve" \| "reject", "note": str?}` | `200 Approval` · `403` unless initiator or admin · `409 conflict` / `409 approval_expired` |
| `POST /api/runs/{run_id}/cancel` | — | `202` (run ends `failed`, reason `cancelled_by_user`) |
| `GET /api/runs/{run_id}/artifacts/{name}` | — | `200 image/png` (step screenshots; same visibility rule) |
| `GET /api/runs/{run_id}/exports/{name}` | — | `200 text/csv` attachment only when the latest passing verification names that run-owned export; same visibility rule |
| `GET /api/budget` | — | `200 Budget` |

```ts
type RunDetail = {
  summary: RunSummary;
  contract: GoalContract | null;
  plan: { steps: PlanStep[]; revision: number };
  facts: Fact[];
  approvals: Approval[];
  question: { question_id: string; text: string } | null;   // set while awaiting_input
  verification: VerificationResult | null;
  pending: PendingMutation[];
  budget: Budget;
  last_seq: number;
};
type Budget = {
  run_spent_inr?: string; run_limit_inr?: string;           // present on RunDetail
  global_spent_inr: string; global_reserved_inr: string; global_limit_inr: string;
  estimated: true;                                         // always true: estimated local limit (spec §8.2)
};
```
`RunSummary`, `Principal`, `GoalContract`, `PlanStep`, `Fact`, `Approval`, `PendingMutation`, `VerificationResult` serialize exactly as the pydantic models in `worker/contracts.py`.
`GoalType.sync_existing_invoice` means correcting one existing register invoice to match its frozen supplier portal source. It requires approval for the existing-record change and independent read-back verification.
`EvidenceItem.download_url` is optional and points to the authenticated CSV route for a verified export.

### Live stream — `GET /api/runs/{run_id}/stream`
- Each message: `id: <seq>`, `event: <type>`, `data: <RunEvent JSON>`.
- On connect, the server first replays events with `seq > Last-Event-ID` (or all events when the header is absent), then streams live.
- A `: keepalive` comment every 15 s.
- After a `run_status` event with a terminal status (`completed, partial, blocked, failed, unsupported`), the server sends `event: end` and closes. A run that later resumes (e.g. after `interrupted`) is a new stream connection.
- `seq` is strictly increasing per run, starting at 1. The client de-duplicates by `seq`.

### Event `data` shapes (by `RunEvent.type`)
| type | data |
| --- | --- |
| `run_status` | `{status: RunStatus, reason?: string}` |
| `phase` | `{phase: "setup" \| "discover" \| "execute" \| "verify" \| "done"}` |
| `plan` | `{steps: PlanStep[], revision: number, reason?: string}` |
| `step` | `{step: number, tool: string, args: object (secrets redacted), ok: boolean, summary: string, url?: string, observation_id?: string, screenshot?: string (artifact name), error_code?: string, duration_ms: number, skipped?: boolean, paused?: boolean (waiting for an approval or an answer, not a failure)}` |
| `fact` | `Fact` + `{step: number}` |
| `contract` | `{action: "committed" \| "revised" \| "rejected", reason?: string, contract?: GoalContract}` |
| `gate` | `{step: number, allowed: boolean, code: GateCode, reason: string, mutation?: {action_url: string, fields: object, target_label?: string}}` |
| `approval` | `Approval` (emitted on request and on every status change) |
| `question` | `{question_id: string, text: string, candidates?: string[], suggested?: string}` (`suggested`: this user's earlier choice from memory; never applied automatically) |
| `answer` | `{question_id: string, text: string, by: string}` |
| `pending` | `PendingMutation` (emitted on every state change) |
| `verification` | `VerificationResult` (emitted after each verify round) |
| `cost` | `{run_spent_inr: string, run_limit_inr: string, global_spent_inr: string, global_limit_inr: string, prompt_tokens: number, completion_tokens: number, model: string}` |
| `error` | `{code: string, message: string, retryable: boolean}` |

Secrets never appear in any event: no passwords, cookies, session tokens, API keys or form tokens (`form_token` is shown as `"•••"`).

---

## §2 Sandbox apps (backend-internal)

### Supplier portal — `:8101`
- `GET /login`, `POST /login` → cookie `portal_session`. The runtime signs in during run setup (spec §2.1).
- `GET /invoices?page=&supplier=` (10 per page), `GET /invoices/{doc_id}`
- `GET /messages`, `GET /messages/{doc_id}`
- Detail pages render `<article data-doc-id data-revision data-kind>` containing a `<dl>`. Invoice labels: `Supplier, Invoice number, Issue date, Due date, Amount, Currency, Notes`. Message labels: `From, Supplier, Subject, Date, Contact name, Contact email, Remittance email, Body`.
- Probe-only API (`X-Probe-Key` header): `GET /api/invoices?supplier_id=`, `GET /api/documents/{doc_id}`.

### Internal register — `:8102`
- `GET /login`, `POST /login` → cookie `reg_session`.
- `GET /invoices?supplier_id=&due_before=`, `GET /invoices/new`, `POST /invoices`, `GET /invoices/{id}`, `GET /invoices/{id}/edit`, `POST /invoices/{id}`.
- `GET /suppliers`, `GET /suppliers/{id}`, `GET /suppliers/{id}/edit`, `POST /suppliers/{id}`.
- `GET /policy`, `POST /policy` (admin only), `POST /admin/assignments` (admin only).
- Every form carries a hidden single-use `form_token`. Update forms also carry a hidden `version`.
- API (bearer session; probes and the runtime only): `GET /api/invoices`, `GET /api/suppliers`, `GET /api/policy`, `POST /api/invoices` (direct-API write, same authz), `GET /api/operations/{token}`, `POST /api/operations/{token}/void`, `POST /api/_faults` (admin).

## §3 Backend internal interfaces
- `LLMProvider.complete(messages, tools, max_tokens) -> LLMResponse{content, tool_calls: ToolCall[], usage{prompt_tokens, completion_tokens}|None, model}`; `FakeProvider` is scripted for offline tests.
- `Probes` (read-only HTTP to §2 APIs): `portal_invoices`, `portal_document`, `register_invoices`, `register_suppliers`, `register_policy`, `operation_status`, `void_operation`, `workspace_csv`.
- `RunService` (used by console routes): `submit(principal, request) -> RunSummary`, `detail(run_id)`, `events(run_id, after)`, `subscribe(run_id)`, `answer(run_id, principal, text)`, `decide(run_id, approval_id, principal, decision, note)`, `cancel(run_id, principal)`.
