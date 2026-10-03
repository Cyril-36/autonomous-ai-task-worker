# Backend design

## Conclusion

The worker may report `completed` only after `worker.verify.verifier.verify` checks every code-derived obligation against the supplier portal, register, or exported file. A model tool call, page message, or successful POST cannot decide completion. The console reads the resulting `VerificationResult` and run events.

## From request to verified result

1. `worker.console.app.create_app` authenticates a demo user and submits a request through `RunService`. `DurableQueue` runs one task at a time and resumes queued or interrupted work after a restart.
2. `BrowserSession.start` signs in to the portal and register before the model sees either page. The model receives only bounded observations and typed tools. `NetworkGuard` restricts origins, blocks browser access to probe APIs, and aborts ungated writes.
3. `worker.verify.goals.commit_goal` checks the user's constraints and resolves source records with read-only probes. It freezes `GoalContract.sources`, field mappings, and obligations. A latest invoice is chosen by code from the portal issue dates; an ambiguous supplier or tied latest date requires a question.
4. `worker.policy.provenance.record_fact` copies a value from a stored observation. `worker.policy.gate.check_mutation` compares every obligation field to the frozen source, checks the fact's document and revision, and applies the register's versioned approval policy. `check_file_write` applies the same goal and path restrictions to exports.
5. Before a permitted browser POST, `worker.policy.pending.begin_pending` saves a `PendingMutation` with the server's one-time form token and intended values. `NetworkGuard.arm` allows one exact URL-encoded body. The register records the operation result and business change in one transaction.
6. `worker.policy.pending.reconcile` atomically asks the register to void or resolve the operation token. A committed response is checked against the saved record; a voided token permits a bounded retry; conflicting values block the run. `worker.runtime.recovery.reconcile_all` does this before resuming interrupted work.
7. `finish` invokes `verify`. Every obligation yields a `CheckResult`; the status and human summary come from those checks. For a reconciled single-record write, the next model turn offers only `finish`, so it cannot keep acting on stale form refs instead of verifying.

## Data and trust boundaries

| Boundary | Data or action | Enforcement |
| --- | --- | --- |
| Console to worker | Signed-in principal, request, approval or answer | `DemoAuth`, `RunService`, owner/admin visibility checks |
| Page to model | Visible text, document fields and short-lived element refs | `BrowserSession.snapshot`; untrusted-page delimiters in `build_messages` |
| Model to browser | Navigations, clicks and fills | `tools_for_phase`, `validate_call`, `WorkerLoop._dispatch`, `NetworkGuard` |
| Model to business write | Complete form body and source binding | `check_mutation`, `Approval`, `PendingMutation`, one-shot `NetworkAllowance` |
| Worker to verifier | Locked `GoalContract` and probe results | `verify` and read-only `Probes`; model summary is ignored for completion |
| Provider to budget | Usage and gateway INR cost | `Ledger.reserve` before dispatch; `Ledger.settle` from reported cost |

The model cannot issue arbitrary HTTP, JavaScript, shell commands, or direct probe calls. Browser form controls are chosen from the latest observation; fills use recorded facts, explicit user literals, or a code-checked source document ID. Passwords, cookies, and the provider key are kept out of model context and run events.

## Recovery and spending

`worker.store.Store` keeps runs, ordered events, approvals, questions and pending mutations in SQLite. Runtime state is checkpointed after steps. On restart, `DurableQueue.start` marks active runs interrupted and queues them; `WorkerLoop.run` reconciles pending operations before asking the model for another action. The register's operation token makes a lost response distinguishable from a missing write.

`worker.llm.ledger.Ledger` reserves a conservative estimate before each live request, includes open reservations when checking the ₹30 global and ₹4 per-run limits, and settles from the gateway's reported INR cost. A timeout or missing usage keeps the reservation charged. This is a local estimated limit, not a gateway-enforced hard ceiling. `config/pricing.toml` records the catalogue prices and date.

## Evaluation boundary

`evals/run.py` creates a separate portal DB, register DB, worker DB and workspace for each case at the frozen reference date. The fake-provider tier exercises real Chromium and guarded writes. `evals/oracle.py` reads raw tables and CSV files, independent of the worker's verifier, to count field correctness, duplicates, unauthorized writes and false completions. Additional controls test direct API authorization, approvals and network guards. The live tier uses Flash Lite and excludes cases whose fault exists only as a fake-model script; those exclusions are listed in `evals/LIVE_REPORT.md`.

The evidence supports behavior in these local sandbox apps. It does not establish reliability on arbitrary websites, scanned documents, production accounting systems, or concurrent worker processes.
