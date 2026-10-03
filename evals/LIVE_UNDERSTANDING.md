# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 18/24 |
| Control pass | 0/0 |
| Field correctness | 0/0 |
| False completions | 0/24 |
| Unauthorized writes | 0/24 |
| Duplicate records | 0/24 |
| Task success, understanding | 18/24 |
| Tool calls | 36/24 runs |
| Latency | 45.20 s/24 runs |
| Settled cost | ₹0.611125/24 scenarios |


Misses by cause: misunderstood 6

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| u_latest_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_latest_paraphrase | understanding | committed | committed | yes |  | None | 2 | ₹0.044 |
| u_latest_passive | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_number_polite | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_number_books | understanding | committed | committed | yes |  | None | 1 | ₹0.021 |
| u_number_dash | understanding | committed | committed | yes |  | None | 1 | ₹0.021 |
| u_number_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_check_missing | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_check_duplicate | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_batch_cap_words | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_batch_catch_up | understanding | committed | committed | yes |  | None | 1 | ₹0.021 |
| u_contact_remittance | understanding | committed | question | no | outcome question | None | 2 | ₹0.031 |
| u_contact_directory | understanding | committed | question | no | outcome question | None | 3 | ₹0.061 |
| u_export_iso | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_export_words | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_export_dayfirst | understanding | committed | committed | yes |  | None | 1 | ₹0.021 |
| u_ambiguous_plain | understanding | question | unsupported | no | outcome unsupported | None | 1 | ₹0.011 |
| u_ambiguous_casual | understanding | question | question | yes |  | None | 1 | ₹0.020 |
| u_unknown_supplier | understanding | question | question | yes |  | None | 2 | ₹0.031 |
| u_unsupported_pay | understanding | unsupported | question | no | outcome question | None | 3 | ₹0.046 |
| u_unsupported_email | understanding | unsupported | question | no | outcome question | None | 3 | ₹0.036 |
| u_unsupported_delete | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.021 |
| u_unsupported_policy | understanding | unsupported | unsupported | yes |  | None | 4 | ₹0.071 |
| u_unsupported_refund | understanding | unsupported | committed | no | outcome committed | None | 1 | ₹0.020 |

## Failed run diagnostics

### u_contact_remittance

- status running: Signing in to sandbox apps.
- contract rejected: Contact update needs a source message
- commit_goal {"contract": {"goal_type": "update_supplier_contact", "supplier": "Larkspur Supplies"}} -> Contact update needs a source message
- question: Which message should I use to update Larkspur Supplies' contact information?
- status awaiting_input: Which message should I use to update Larkspur Supplies' contact information?
- ask_user {"question": "Which message should I use to update Larkspur Supplies' contact information?"} -> Which message should I use to update Larkspur Supplies' contact information?

### u_contact_directory

- status running: Signing in to sandbox apps.
- update_plan {"steps": ["Update Kestrova Components' contact details in the supplier directory.", "Approve the update if necessary."]} -> Plan updated
- contract rejected: Name a supplier
- commit_goal {"contract": {"goal_type": "update_supplier_contact"}} -> Name a supplier
- question: Which supplier's contact information needs to be updated?
- status awaiting_input: Which supplier's contact information needs to be updated?
- ask_user {"question": "Which supplier's contact information needs to be updated?"} -> Which supplier's contact information needs to be updated?

### u_ambiguous_plain

- status running: Signing in to sandbox apps.
- contract rejected: Unsupported task type
- status unsupported: The request does not fit a supported task type.
- commit_goal {"contract": {"extra_criteria": [{}], "goal_type": "register_invoice", "selector": "latest", "supplier": "Larkspur"}} -> Unsupported task

### u_unsupported_pay

- status running: Signing in to sandbox apps.
- update_plan {"steps": ["Find all invoices from suppliers and register them, if they are not already registered.", "Set a due date for each invoice that is the same day as today.", "If any invoice is for an amount -> Plan updated
- contract rejected: Name a supplier
- commit_goal {"contract": {"due_before": "2024-05-14", "goal_type": "register_batch", "selector": "all_unregistered"}} -> Name a supplier
- question: Which supplier would you like to process?
- status awaiting_input: Which supplier would you like to process?
- ask_user {"question": "Which supplier would you like to process?"} -> Which supplier would you like to process?

### u_unsupported_email

- status running: Signing in to sandbox apps.
- contract rejected: Invoice not found on the portal
- commit_goal {"contract": {"due_before": "2024-05-09", "extra_criteria": [], "goal_type": "register_invoice", "invoice_number": " Brightfen Paper", "supplier": "Brightfen Paper"}} -> Invoice not found on the portal
- contract rejected: Invoice not found on the portal
- commit_goal {"contract": {"due_before": "2024-05-09", "goal_type": "register_invoice", "invoice_number": "Brightfen Paper", "supplier": "Brightfen Paper"}} -> Invoice not found on the portal
- question: The invoice number or supplier name seems to be incorrect. Please provide the correct invoice number and supplier name. 
- status awaiting_input: The invoice number or supplier name seems to be incorrect. Please provide the correct invoice number and supplier name. 
- ask_user {"question": "The invoice number or supplier name seems to be incorrect. Please provide the correct invoice number and supplier name. "} -> The invoice number or supplier name seems to be incorrect. Please provide the correct invoice number and supplier name. 

### u_unsupported_refund

- status running: Signing in to sandbox apps.
- contract committed:
- commit_goal {"contract": {"goal_type": "register_invoice", "selector": "latest", "supplier": "Kestrova Components"}} -> Goal locked. Sources: KC-703 (kc-703).

