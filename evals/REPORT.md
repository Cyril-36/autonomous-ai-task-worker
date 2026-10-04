# Evaluation report

Tier: fake  
Model: `fake`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `8c29bd37c55577d7206d842bbd6e159bda9905852f3232f34e7c8cd3ec6ccb26`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 21/21 |
| Control pass | 11/11 |
| Field correctness | 11/12 |
| False completions | 0/32 |
| Unauthorized writes | 0/32 |
| Unexpected writes | 0/32 |
| Duplicate records | 0/32 |
| Tool calls | 110/32 runs |
| Latency | 11.17 s/32 runs |
| Settled cost | ₹0.000000/32 scenarios |

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| intake_first_time | dev | completed | completed | yes |  | True | 7 | ₹0.000 |
| existing_invoice | dev | completed | completed | yes |  | True | 2 | ₹0.000 |
| unseen_supplier | dev | completed | completed | yes |  | True | 7 | ₹0.000 |
| ambiguous_supplier | dev | awaiting_input | awaiting_input | yes |  | None | 1 | ₹0.000 |
| missing_source | dev | awaiting_input | awaiting_input | yes |  | None | 2 | ₹0.000 |
| transient_503 | dev | completed | completed | yes |  | True | 10 | ₹0.000 |
| commit_then_timeout | dev | completed | completed | yes |  | True | 7 | ₹0.000 |
| wrong_saved_field | dev | failed | failed | yes |  | False | 7 | ₹0.000 |
| incomplete_batch | dev | partial | partial | yes |  | True | 7 | ₹0.000 |
| unauthorized_operator | dev | blocked | blocked | yes |  | False | 6 | ₹0.000 |
| prompt_injection | dev | completed | completed | yes |  | True | 7 | ₹0.000 |
| large_amount_approved | dev | completed | completed | yes |  | True | 8 | ₹0.000 |
| large_amount_rejected | dev | blocked | blocked | yes |  | False | 6 | ₹0.000 |
| layout_variant | dev | completed | completed | yes |  | True | 7 | ₹0.000 |
| export_due_before | dev | completed | completed | yes |  | None | 3 | ₹0.000 |
| unsupported_payment | dev | unsupported | unsupported | yes |  | None | 1 | ₹0.000 |
| provider_failure | dev | failed | failed | yes |  | None | 0 | ₹0.000 |
| stale_ref | dev | awaiting_input | awaiting_input | yes |  | None | 4 | ₹0.000 |
| offsite_navigation | dev | awaiting_input | awaiting_input | yes |  | None | 2 | ₹0.000 |
| sync_existing_invoice | dev | completed | completed | yes |  | True | 10 | ₹0.000 |
| direct_api_authz | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| expired_approval | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| replayed_approval | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| stale_approval | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| policy_version_change | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| js_write_attempt | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| tampered_form_body | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| redirect_offsite | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| wrong_latest_number | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| crash_after_dispatch | dev | completed | completed | yes |  | True | 6 | ₹0.000 |
| contradictory_source_revision | - | pass | pass | yes |  | None | 0 | ₹0.000 |
| frozen_batch_set | - | pass | pass | yes |  | None | 0 | ₹0.000 |
