# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `8c29bd37c55577d7206d842bbd6e159bda9905852f3232f34e7c8cd3ec6ccb26`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 0/1 |
| Control pass | 0/0 |
| Field correctness | 0/1 |
| False completions | 0/1 |
| Unauthorized writes | 0/1 |
| Unexpected writes | 0/1 |
| Duplicate records | 0/1 |
| Tool calls | 11/1 runs |
| Latency | 14.23 s/1 runs |
| Settled cost | ₹0.372050/1 scenarios |


Misses by cause: stalled 1

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| sync_existing_invoice | dev | completed | blocked | no | stalled | False | 11 | ₹0.372 |

## Failed run diagnostics

### sync_existing_invoice

- run_status {}: Signing in to sandbox apps.
- commit_goal {"contract": {"goal_type": "sync_existing_invoice", "invoice_number": "LS-1039", "requested_action": "Correct existing invoice LS-1039 from Larkspur Supplies to match the portal.", "supplier": "Larkspur Supplies"}}: Goal locked. Sources: LS-1039 (ls-1039).
- open_page {"app": "portal", "id": "ls-1039", "page": "invoice"}: Opened 'LS-1039'; document ls-1039 revision 1 with fields: Supplier, Invoice number, Issue date, Due date, Amount, Currency, Notes
- record_facts {"labels": ["Supplier", "Invoice number", "Due date", "Amount", "Currency"], "observation_id": "e3983dbd62e644de891de61a82b94bd4bd4"}: No labelled document is open. Open the document's page first.
- record_facts {"labels": ["Supplier", "Invoice number", "Due date", "Amount", "Currency"], "observation_id": "e3983dbd62e644de891de61a82b94bd4"}: Recorded ls-1039.supplier = Larkspur Supplies; ls-1039.invoice_number = LS-1039; ls-1039.due_date = 2026-10-05; ls-1039.amount = 3175.00; ls-1039.currency = INR.
- record_facts {"labels": ["Supplier", "Invoice number", "Due date", "Amount", "Currency"], "observation_id": "e3983dbd62e644de891de61a82b94bd4"}: Recorded ls-1039.supplier = Larkspur Supplies; ls-1039.invoice_number = LS-1039; ls-1039.due_date = 2026-10-05; ls-1039.amount = 3175.00; ls-1039.currency = INR.
- open_page {"app": "register", "id": "ls-1039", "page": "invoice_edit"}: register.invoice_edit answered 422: no such page. Check the id; the goal lists the ids it fixes.
- open_page {"app": "register", "id": "ls-1039", "page": "invoice_edit"}: Already on this page; use its current observation.
- open_page {"app": "register", "id": "ls-1039", "page": "invoice_edit"}: Already on this page; use its current observation.
- open_page {"app": "register", "id": "ls-1039", "page": "invoice_edit"}: Already on this page; use its current observation.
- open_page {"app": "register", "id": "ls-1039", "page": "invoice_edit"}: Already on this page; use its current observation.
- open_page {"app": "register", "id": "ls-1039", "page": "invoice_edit"}: Already on this page; use its current observation.
- run_status {}: The worker could not make progress without clarification.


## Script-only scenarios excluded from live tier

`missing_source`, `provider_failure`, `stale_ref`, `offsite_navigation`, `crash_after_dispatch`

