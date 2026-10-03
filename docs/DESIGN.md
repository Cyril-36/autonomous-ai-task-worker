# Design

**In one sentence:** the model decides what to do next; code decides what is allowed, where every value came from, and whether the work is actually done.

Each section below gives the conclusion first, then the code that makes it true.

## 1. A run, end to end

**A request becomes a locked goal before anything can change, and a verified result before it counts as done.**

`WorkerLoop.run` (`worker/runtime/loop.py`) drives each run through four phases:

| Phase | What happens | Code |
| --- | --- | --- |
| setup | Runtime signs in to both apps as the requesting user; the model never sees credentials | `BrowserSession.start` |
| discover | Read-only. The model looks around and proposes a goal | `tools_for_phase("discover")` offers no write tools |
| execute | The model reads sources, records facts, fills and submits forms | `_record_facts`, `_fill_form`, `_submit` |
| verify | Code reads the systems back and decides the status | `verify` → `VerificationResult` |

Every turn, `build_messages` (`worker/runtime/prompts.py`) sends: the fixed instructions, the company context from `Apps.describe()`, the request, the locked goal (`describe_goal`), the facts so far, the model's last 12 actions with their results, and the last three page observations wrapped as `<untrusted_page>`. Tool calls run one at a time; once a call changes the page, the rest of that turn is skipped so the model never acts on a stale page.

## 2. Generalization: task knowledge is data

**The instructions and tools are identical for every goal type; what differs is data.** `test_instructions_and_tools_are_identical_for_every_goal_type` checks this.

- `config/apps.yaml` (loaded by `Apps`, `worker/runtime/apps.py`) describes each app's pages in words and each goal type's procedure: where sources are read (`read: portal.invoice`) and where values go (`write: register.new_invoice`, or `register.supplier_edit` with `write_id: supplier`). `Apps.url` turns `open_page(app, page, id)` into a URL; the model never sees a host or port.
- A goal type in `worker/verify/goals.py` declares how sources are resolved, the field map (form field ← document label) and the obligations.
- A probe in `worker/verify/probes.py` reads results back for the verifier.

**Why task-level tools.** With raw `navigate(url)`, `fill(ref)` and `click(ref)`, live traces showed the model filling the wrong element, mixing up ports and re-typing values. The model now names *labels and facts*; code resolves them:

- `open_page(app, page, id)` → a named page, with HTTP errors reported as errors.
- `record_facts(labels)` → `record_fact` copies each labelled value from the stored `Observation` into a `Fact` keyed `<doc_id>.<label>`, carrying `observation_id`, `doc_id`, `revision` and the normalized value. The model never supplies a value.
- `fill_form([{label, fact}])` → `find_by_label` resolves each visible label to one element (select names include their options, so prefix matching is allowed; ambiguity is an error listing the fields).
- `submit_form()` → re-reads the page, finds the single submit control, then goes through `_submit`.

When a goal is locked, `_goal_facts` adds the values the goal already fixes (`goal.supplier`, each source's `document_id`), so the model never re-types them.

## 3. Understanding the request

**The model proposes; `commit_goal` checks the proposal against the request and resolves the sources itself.**

`commit_goal(proposal, request_text, probes)` (`worker/verify/goals.py`) returns a `GoalContract` or a `GoalRejection`:

- The supplier must resolve to exactly one supplier and be named in the request; two matches → `needs_clarification` with candidates, which becomes a question to the user.
- "Latest/newest" requests must use the `latest` selector; a number the user never wrote is refused.
- Caps and dates must be ones the user wrote: `numbers_in` reads digits and number words; `dates_in` reads ISO, "1 November 2026", "November 1, 2026", "15th of November 2026" and day-first "15/11/2026".
- Sources are resolved by code: the latest invoice by issue date, an invoice by number, a frozen batch (eligible invoices at commit time, capped, with the rest listed as remaining), or the supplier's latest contact message. The model's proposed document must match.
- Rejections without candidates go back to the model with the reason, telling it to fix the goal from the request and ask only if the request is silent. An unknown goal type ends the run as `unsupported`.

`commit_goal` asks the model to restate the requested action first (`requested_action`), which reduced forced goals for requests the system does not support.

## 4. Writes

**A write happens only if the gate allows it, the network guard sees exactly the approved body, and a pending record exists before the click.**

`_submit` (`loop.py`) builds a `MutationIntent` from the live form (`capture_form`, hidden fields included) and calls `check_mutation` (`worker/policy/gate.py`), which requires:

- execute phase and a locked goal;
- the write bound to one frozen `SourceRef`, and every obligation field equal to that source's value for the mapped label (`field_map`), including select controls;
- no unresolved pending write on the same target;
- approval when policy requires it (amount ≥ ₹1,00,000, remittance change): `create_approval` binds the intent hash, target version and policy version, with a 15-minute expiry; `validate_approval` refuses expired, reused or stale approvals.

Then `begin_pending` writes a `PendingMutation` (`state=dispatching`) to `worker.db`, `NetworkGuard.arm` permits one POST whose parsed body equals the gated fields exactly, and the click happens. `NetworkGuard` also blocks off-sandbox origins, `/api/` paths and service workers, and closes pages that land off-site after a redirect.

## 5. Unknown outcomes and restarts

**A lost response is settled by asking the register about the form's one-time token, never by looking at the page.**

`reconcile(pending, probes)` (`worker/policy/pending.py`) voids the token if it has not committed (so a late request cannot commit afterwards) and reads the result: committed with the intended values → done, no retry; voided → safe to retry with a fresh form; committed with other values → conflict, ask the user. `reconcile_all` runs these before a resumed run calls the model, so a crash between click and response leaves exactly one record.

## 6. Verification and status

**`completed` is derived only from `verify`, and the summary is rendered from its checks, not from model text.**

`verify(contract, probes)` (`worker/verify/verifier.py`) evaluates every obligation through read-only probes: record count, field equality with the source, latest-ness, batch completeness against the frozen set, export rows against the register, contact fields, and approval recorded. All pass → `completed`; batch beyond cap → `partial`; otherwise the failed checks go back to the model (up to 2 rounds) and an unrepairable run ends `failed` with the verifier's reason. The stall detector (`StallDetector`) counts only real progress (a new fact, a successful write, a changed page), so repeated plans or snapshots cannot keep a run alive.

## 7. Spending

**Each model call reserves its worst-case cost before it is sent.**

`Ledger.reserve` (`worker/llm/ledger.py`) estimates from the serialized request size plus `max_tokens`, refuses calls that would exceed the run (₹4) or global (₹50) limit, and `Ledger.settle` records the gateway's reported cost. Timeouts keep the full reservation. This is an estimated local limit, not a provider guarantee.

## 8. Evaluation

**Three tiers, scored by an oracle that reads the databases and files directly and never trusts the worker.**

- `evals/scenarios.yaml`: development scenarios, including faults (failed save, commit-then-timeout, corrupted save, relabelled form), permission refusals, approvals and prompt injection; plus 11 guard controls that attack the gate directly.
- `evals/heldout.yaml`: tasks written before any run and never tuned on.
- `evals/understanding.yaml`: 24 requests scored on the goal locked, the question asked or the refusal (`score_understanding`); runs stop at the goal, so repeating is cheap.

`inspect_case` (`evals/oracle.py`) compares register rows with portal documents field by field, checks exports against the register, supplier records, duplicates and unauthorized writes, and labels each miss with `failure_category` (step limit, stall, verifier caught, asked instead, misread request, missed refusal). A fake-model pass proves the plumbing; only live runs measure the agent.
