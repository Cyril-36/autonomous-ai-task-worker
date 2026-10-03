# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 47/48 |
| Control pass | 0/0 |
| Field correctness | 0/0 |
| False completions | 0/48 |
| Unauthorized writes | 0/48 |
| Duplicate records | 0/48 |
| Task success, understanding | 47/48 |
| Tool calls | 62/48 runs |
| Latency | 82.20 s/48 runs |
| Settled cost | ₹0.918329/48 scenarios |


Misses by cause: misunderstood 1

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| u_latest_plain#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_latest_paraphrase#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_latest_passive#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_number_polite#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_number_books#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_number_dash#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_number_plain#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.014 |
| u_check_missing#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_check_duplicate#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_batch_cap_words#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_batch_catch_up#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_contact_remittance#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.021 |
| u_contact_directory#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.021 |
| u_export_iso#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_export_words#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_export_dayfirst#1 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_ambiguous_plain#1 | understanding | question | question | yes |  | None | 1 | ₹0.013 |
| u_ambiguous_casual#1 | understanding | question | question | yes |  | None | 1 | ₹0.012 |
| u_unknown_supplier#1 | understanding | question | question | yes |  | None | 3 | ₹0.048 |
| u_unsupported_pay#1 | understanding | unsupported | unsupported | yes |  | None | 4 | ₹0.061 |
| u_unsupported_email#1 | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.011 |
| u_unsupported_delete#1 | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.012 |
| u_unsupported_policy#1 | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.026 |
| u_unsupported_refund#1 | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.012 |
| u_latest_plain#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_latest_paraphrase#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_latest_passive#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_number_polite#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_number_books#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_number_dash#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_number_plain#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_check_missing#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_check_duplicate#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_batch_cap_words#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_batch_catch_up#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_contact_remittance#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_contact_directory#2 | understanding | committed | unsupported | no | outcome unsupported | None | 1 | ₹0.012 |
| u_export_iso#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_export_words#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_export_dayfirst#2 | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_ambiguous_plain#2 | understanding | question | question | yes |  | None | 1 | ₹0.012 |
| u_ambiguous_casual#2 | understanding | question | question | yes |  | None | 1 | ₹0.012 |
| u_unknown_supplier#2 | understanding | question | question | yes |  | None | 2 | ₹0.024 |
| u_unsupported_pay#2 | understanding | unsupported | unsupported | yes |  | None | 3 | ₹0.046 |
| u_unsupported_email#2 | understanding | unsupported | unsupported | yes |  | None | 4 | ₹0.060 |
| u_unsupported_delete#2 | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.012 |
| u_unsupported_policy#2 | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.029 |
| u_unsupported_refund#2 | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.035 |

## Failed run diagnostics

### u_contact_directory#2

- status running: Signing in to sandbox apps.
- status unsupported: The user wants to update supplier contact details. This is not a supported goal type. Supported goal types are: register_invoice, check_or_register_invoice, register_batch, export_invoices.
- unsupported {"reason": "The user wants to update supplier contact details. This is not a supported goal type. Supported goal types are: register_invoice, check_or_register_invoice, register_batch, export_invoices -> The user wants to update supplier contact details. This is not a supported goal type. Supported goal types are: register_invoice, check_or_register_invoice, register_batch, export_invoices.

