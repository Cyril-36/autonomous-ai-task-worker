# Retrospective

What was built in the roughly 24 hours available (3 Oct 2026, 18:49 IST, to 4 Oct, late morning), what the model spend went on, and what I would add or do differently with more time and a larger API budget.

Results are in the [README](../README.md); diagrams are in [ARCHITECTURE.md](ARCHITECTURE.md).

## What was built

| Area | What exists |
| --- | --- |
| Sandbox company | A supplier portal and an internal invoice register (FastAPI + SQLite) with real sign-in, per-supplier permissions enforced by the register, policy (approval threshold), one-time form tokens and fault injection (503s, a save that commits and then times out, a second form layout) |
| Worker | A loop that drives Chromium through task-level tools, locks a goal before any write, gates every write on provenance, permissions and approvals, records each save before sending it, reconciles unknown outcomes, and calls a run `completed` only after an independent read-back |
| Goal types | Register an invoice, check-or-register, register a batch, update a supplier contact (with approval), export due invoices to CSV, correct an existing invoice to match its source |
| Human in the loop | Clarifying questions with choices, confirmation when the request is unclear, approvals bound to exact values, the target record version, the policy version and a 15-minute expiry. A per-user memory suggests earlier choices but never applies them |
| Console | Sign-in, tasks, a live timeline over server-sent events, approval and question cards, a code-built plan, the explanation panel ("Why it did that"), evidence with read-back checks and page captures, and a spending meter |
| Evaluation | Scripted fake model (free, in CI), a live development set, a held-out set written before any run, an understanding tier that stops at the goal, 11 guard controls, and an oracle that snapshots the register and audits every write by actor |
| Packaging | `make setup` / `make dev`, a Docker image and `compose.yaml`, GitHub Actions CI |

### How the work went

1. **Design first (evening of 3 Oct).** A written spec with the sandbox, the trust boundaries (model decides, code allows) and the evaluation plan, before any code.
2. **Sandbox apps, guarded browser, write gate, verifier.** Built test-first; the scripted fake model drove every flow before any paid call.
3. **First live pass: 6/15.** The model was given raw tools (`navigate(url)`, `click(ref)`, `fill(ref)`). It typed invoice numbers into the Supplier field, mixed up the two apps' ports and re-typed values it was supposed to copy.
4. **Generalization: 6/15 → 11/15 → 14/15 → 15/15.** Task-level tools (`open_page(app, page)`, `record_facts(labels)`, `fill_form({label: fact})`), a manifest of pages and procedures, and general feedback rules. I tried per-scenario prompt rules once; they made things worse (1/5 on a targeted recheck) and were removed.
5. **Two reviews of the scorer** found that it audited writes only in refusal cases, judged edits by the record's original author rather than the person running the task, and ignored writes in false-completion checks. All three were fixed, and the development set was rerun under the stricter audit (15/15).
6. **A bug hunt** found 17 issues (negated numbers, pronoun bypasses, a "No" answer that looped, separate spending ledgers, restart approvals and others). All were fixed with tests.
7. **Final pass:** a sixth goal type (correction), Docker, UI fixes from a hands-on verification, a final live development pass (16/16 tasks, 11/11 controls, ₹3.19), a held-out rerun under the audited scorer (10/11, ₹1.52) and the demo recording.

## What the model spend went on

The cap was ₹50 for the whole build, including every live evaluation; it was raised to ₹60 for the final held-out rerun and the demo. Total spend was about ₹46. The local ledger reserves an estimate before each call and settles it from the gateway's reported cost.

| | Calls | Input tokens | Output tokens | Cost |
| --- | ---: | ---: | ---: | ---: |
| Gemini 2.5 Flash-Lite | 1,484 | 3.74 M | 70 k | ₹39.04 |
| Gemini 2.5 Flash (smoke tests and one comparison) | 18 | 58 k | 0.5 k | ₹2.10 |

*Figures from `data/live-eval-ledger.db` before the final development pass. That pass is reported separately in the README.*

What the numbers say:

- **Input is 98% of the tokens.** Each call re-sends the instructions, company context, goal, plan, facts, the last 12 actions and up to three page observations (about 2,500 tokens on average). Output is short tool calls. The cheapest improvements are therefore on the input side: smaller page observations, sending only what changed, and prompt caching where the gateway supports it.
- **Flash costs about 4.5× Flash-Lite per call** (₹0.117 against ₹0.026) because the gateway bills Flash's hidden thinking tokens. That is why every reported result uses Flash-Lite.
- **Typical costs:** ₹0.05–0.30 per task (3 to 8 model calls). A full development pass costs ₹3.2–3.7 for 27 scenarios. The first held-out pass cost ₹5.37 (169 tool calls), ₹3.88 of it on the two misses, where the model looped on two feedback gaps; after those were fixed, the rerun cost ₹1.52 (58 tool calls). Clear feedback to the model saves money as well as failures.
- **The tool design was also the main cost fix.** The raw-tool pass used 383 tool calls and ₹5.29 for 26 scenarios; the task-tool pass used 122 calls and ₹3.66.

### What the budget forced

- **One model.** No comparison across model families, and Flash only in smoke tests.
- **One run per result.** Each development pass, each held-out run and the correction check ran once, so the numbers have no variance estimate. The only repeats are two cheap understanding passes (47/48).
- **The held-out set was rerun under the audited scorer only at the end** (10/11, ₹1.52), after the cap was raised from ₹50 to ₹60. By then its first run's misses had already informed fixes, so the clean held-out number remains the first run's 9/11.
- **No LLM-as-judge.** Every metric is deterministic.

## With a larger API budget

Estimates use the measured rate of about ₹0.14 per scenario on Flash-Lite.

| Experiment | Why | Rough cost |
| --- | --- | ---: |
| 5 repeats of the development set per significant change | Report pass^k (all 5 succeed) and pass@k, not one sample; Flash-Lite varied between runs | ₹19 per change |
| A new held-out set, run 3 times on frozen code | A clean held-out number with a variance estimate | ₹5–16 |
| Model matrix: Flash-Lite, Flash, a Pro-class model and one model from another family, 3 repeats each | Cost against accuracy, and whether the code-side checks carry a weaker model | ₹40–150, depending on the larger models' prices |
| Held-out set grown to 50 tasks (new suppliers, document layouts, phrasings, admin flows) | 11 tasks is too small to compare versions | ₹7 per pass |
| Understanding tier, 10 repeats over 100 phrasings | How often the model asks, refuses or proceeds when it should not | ₹25 |
| Prompt-injection sweep (30 hostile page texts) | Shows that page text cannot steer a write, across many wordings | ₹5 |
| LLM-as-judge over every trace (below) | Quality signals the oracle cannot compute | ₹0.06–2 per trace |

## LLM-as-judge: how I would add it

The deterministic oracle stays the source of truth for anything with a right answer: which records changed, by whom, whether values match the source, and whether a run should be `completed`. A judge must never decide `completed` or override the oracle. It adds signals the oracle cannot compute:

| Judged dimension | Example question for the judge |
| --- | --- |
| Question quality | Was asking necessary? Does the question name the real ambiguity, and are the choices complete? |
| Summary faithfulness | Does the final sentence to the user match the read-back data and nothing more? |
| Refusal reasonableness | For `unsupported` or `blocked`, was declining right given the request and the tools? |
| Wasted work | Did the trace repeat pages, loop on an error, or take steps that did not move the goal? |
| Approval clarity | Could a manager understand what they are approving from the card alone? |

Design:

- **Rubrics with yes/no criteria**, not a 1–10 score. Each criterion is one question with a written definition and an example of each answer.
- **The judge sees evidence, not claims:** the request, a compact trace (tool, arguments, result), and the oracle's read-back of the final state. It never sees the worker's own summary as proof.
- **A different model family from the worker**, so it does not grade its own phrasing.
- **Calibrate before trusting it.** Label 40–50 traces by hand, measure agreement (Cohen's kappa per criterion), and drop or rewrite criteria below about 0.6.
- **Pairwise comparison between versions** ("is trace A or B better at…"), asked both ways round to cancel position bias.
- **Cost:** a compact trace is about 4–6k input tokens, about ₹0.06 per judgment at Flash-Lite rates. A stronger judge costs its price ratio more. Judging every trace from a 27-scenario pass with a mid-priced model stays within a few rupees.

The same model can also **generate evaluation data**: paraphrases of requests for the understanding tier, and supplier documents with new layouts. A person reviews each generated case and labels its expected outcome before it enters a set. Generated cases go into the development set; the held-out set stays written by hand.

## Other evaluations I would add

- **Variance as a first-class metric:** pass^k and pass@k per scenario over repeats.
- **Cost and latency budgets in CI:** fail a change that raises model calls or tokens per task by more than 20% on the scripted suite.
- **Trace metrics:** steps per task, repeated actions, recovery success after a fault, and how long a run waits for a person.
- **Race conditions, which are known gaps today:** cancelling exactly during a save, and a policy change racing a save. The write-ahead log and reconciliation should cover them, but no test drives those exact interleavings.
- **Longer jobs:** a batch of 20 invoices with faults scattered through it.
- **Precision of asking:** of the questions the worker asks, how many were necessary, and of the requests that needed a question, how many got one.

## With more time: product and engineering

- **Declarative app connectors.** Sign-in, allowed origins and write targets described in the manifest, so a new app needs no code (today `BrowserSession.start` and `WorkerLoop._submit` know the two apps).
- **Documents beyond labelled HTML:** OCR for PDF invoices and a vision fallback for pages without labelled fields.
- **Company memory beyond suggestions:** which document labels map to which form fields per app, and which procedures needed approvals or corrections, so repeated workflows take fewer steps.
- **More goal types as data plus probes:** payment proposals with approval, three-way matching (order, receipt, invoice).
- **Production shape:** multi-worker queue with leases, persistent console sessions, budget enforced by the provider rather than estimated locally, per-tenant audit log export, and notifications when a run needs a person.
- **One spending ledger across processes.** The Docker container keeps its own ledger in its volume, so the meter in a container does not include spend made outside it.

## What I would do differently

- **Start with task-level tools.** The raw click tools cost the first live pass (6/15, ₹5.29) and several hours. The failure was predictable: models are poor at mapping values onto unlabelled element ids.
- **Build the strict oracle before reporting any number.** Snapshot before each run, audit every write by actor, and count a completion with any unexpected write as false. Earlier results had to be relabelled once the audit tightened.
- **Run every new goal type live once, immediately.** The correction goal passed the scripted suite, because the script already knew the record id, and failed its first live run. The scripted model checks the code paths, not whether the model can find what it needs.
- **Plan the paid runs.** Reserve the final held-out run and the demo first, then spend the rest on development. The final held-out rerun only fitted after the cap was raised.
- **Fewer, clearly named reports.** `evals/` holds many intermediate `LIVE_*` reports. One report per pass with a run manifest (commit, model, scorer version) would be easier to audit.
- **Check the console with real captures early.** The evidence captures looked blank in the browser because the CSS centre-cropped sparse pages. Mock data had hidden that until a hands-on check.
