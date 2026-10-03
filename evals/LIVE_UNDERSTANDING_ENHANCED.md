# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 22/24 |
| Control pass | 0/0 |
| Field correctness | 0/0 |
| False completions | 0/24 |
| Unauthorized writes | 0/24 |
| Duplicate records | 0/24 |
| Task success, understanding | 22/24 |
| Tool calls | 30/24 runs |
| Latency | 44.10 s/24 runs |
| Settled cost | ₹0.436600/24 scenarios |


Misses by cause: misunderstood 2

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| u_latest_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_latest_paraphrase | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_latest_passive | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_number_polite | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_number_books | understanding | committed | committed | yes |  | None | 1 | ₹0.014 |
| u_number_dash | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_number_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.023 |
| u_check_missing | understanding | committed | committed | yes |  | None | 1 | ₹0.023 |
| u_check_duplicate | understanding | committed | committed | yes |  | None | 1 | ₹0.014 |
| u_batch_cap_words | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_batch_catch_up | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_contact_remittance | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_contact_directory | understanding | committed | unsupported | no | outcome unsupported | None | 1 | ₹0.012 |
| u_export_iso | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_export_words | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_export_dayfirst | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_ambiguous_plain | understanding | question | question | yes |  | None | 1 | ₹0.012 |
| u_ambiguous_casual | understanding | question | question | yes |  | None | 1 | ₹0.012 |
| u_unknown_supplier | understanding | question | question | yes |  | None | 2 | ₹0.033 |
| u_unsupported_pay | understanding | unsupported | unsupported | yes |  | None | 3 | ₹0.047 |
| u_unsupported_email | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.036 |
| u_unsupported_delete | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.012 |
| u_unsupported_policy | understanding | unsupported | unsupported | yes |  | None | 3 | ₹0.040 |
| u_unsupported_refund | understanding | unsupported | committed | no | outcome committed | None | 1 | ₹0.012 |

## Failed run diagnostics

### u_contact_directory

- status running: Signing in to sandbox apps.
- status unsupported: The user wants to update supplier contact details, but the available tools lack the functionality to directly update supplier information. The `commit_goal` function does not support the 'update_supplier_contact' goal type.
- unsupported {"reason": "The user wants to update supplier contact details, but the available tools lack the functionality to directly update supplier information. The `commit_goal` function does not support the ' -> The user wants to update supplier contact details, but the available tools lack the functionality to directly update supplier information. The `commit_goal` function does not support the 'update_supplier_contact' goal type.

### u_unsupported_refund

- status running: Signing in to sandbox apps.
- contract committed:
- commit_goal {"contract": {"goal_type": "register_invoice", "max_count": 1, "requested_action": "Issue a refund to Kestrova Components for their last invoice.", "selector": "latest", "supplier": "Kestrova Componen -> Goal locked. Sources: KC-703 (kc-703).

