# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `b14c6e075aa402ed2d09415513e0b39b8d35278f53837f045bbb8b34ab610bb8`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 16/24 |
| Control pass | 0/0 |
| Field correctness | 0/0 |
| False completions | 0/24 |
| Unauthorized writes | 0/24 |
| Duplicate records | 0/24 |
| Task success, understanding | 16/24 |
| Tool calls | 51/24 runs |
| Latency | 64.77 s/24 runs |
| Settled cost | ₹1.143418/24 scenarios |


Misses by cause: misunderstood 8

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| u_latest_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_latest_paraphrase | understanding | committed | committed | no | selector: expected latest, got invoice_number | None | 4 | ₹0.129 |
| u_latest_passive | understanding | committed | committed | yes |  | None | 1 | ₹0.010 |
| u_number_polite | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_number_books | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_number_dash | understanding | committed | committed | yes |  | None | 1 | ₹0.010 |
| u_number_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_check_missing | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_check_duplicate | understanding | committed | committed | yes |  | None | 1 | ₹0.020 |
| u_batch_cap_words | understanding | committed | committed | yes |  | None | 1 | ₹0.011 |
| u_batch_catch_up | understanding | committed | none (blocked) | no | outcome none (blocked) | None | 10 | ₹0.409 |
| u_contact_remittance | understanding | committed | committed | yes |  | None | 8 | ₹0.187 |
| u_contact_directory | understanding | committed | question | no | outcome question | None | 1 | ₹0.009 |
| u_export_iso | understanding | committed | committed | yes |  | None | 1 | ₹0.010 |
| u_export_words | understanding | committed | question | no | outcome question | None | 2 | ₹0.031 |
| u_export_dayfirst | understanding | committed | question | no | outcome question | None | 2 | ₹0.031 |
| u_ambiguous_plain | understanding | question | question | yes |  | None | 1 | ₹0.010 |
| u_ambiguous_casual | understanding | question | question | yes |  | None | 1 | ₹0.010 |
| u_unknown_supplier | understanding | question | question | yes |  | None | 1 | ₹0.019 |
| u_unsupported_pay | understanding | unsupported | question | no | outcome question | None | 2 | ₹0.021 |
| u_unsupported_email | understanding | unsupported | committed | no | outcome committed | None | 2 | ₹0.020 |
| u_unsupported_delete | understanding | unsupported | question | no | outcome question | None | 1 | ₹0.020 |
| u_unsupported_policy | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.024 |
| u_unsupported_refund | understanding | unsupported | unsupported | yes |  | None | 4 | ₹0.073 |
