# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 24/24 |
| Control pass | 0/0 |
| Field correctness | 0/0 |
| False completions | 0/24 |
| Unauthorized writes | 0/24 |
| Unexpected writes | 0/24 |
| Duplicate records | 0/24 |
| Task success, understanding | 24/24 |
| Tool calls | 34/24 runs |
| Latency | 47.78 s/24 runs |
| Settled cost | ₹0.574950/24 scenarios |

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| u_latest_plain | understanding | committed | committed | yes |  | None | 2 | ₹0.041 |
| u_latest_paraphrase | understanding | committed | committed | yes |  | None | 2 | ₹0.056 |
| u_latest_passive | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_number_polite | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_number_books | understanding | committed | committed | yes |  | None | 2 | ₹0.041 |
| u_number_dash | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_number_plain | understanding | committed | committed | yes |  | None | 1 | ₹0.023 |
| u_check_missing | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_check_duplicate | understanding | question | question | yes |  | None | 1 | ₹0.023 |
| u_batch_cap_words | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_batch_catch_up | understanding | committed | committed | yes |  | None | 1 | ₹0.022 |
| u_contact_remittance | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_contact_directory | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_export_iso | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_export_words | understanding | committed | committed | yes |  | None | 1 | ₹0.012 |
| u_export_dayfirst | understanding | committed | committed | yes |  | None | 1 | ₹0.013 |
| u_ambiguous_plain | understanding | question | question | yes |  | None | 1 | ₹0.012 |
| u_ambiguous_casual | understanding | question | question | yes |  | None | 1 | ₹0.021 |
| u_unknown_supplier | understanding | question | question | yes |  | None | 4 | ₹0.054 |
| u_unsupported_pay | understanding | unsupported | unsupported | yes |  | None | 3 | ₹0.046 |
| u_unsupported_email | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.012 |
| u_unsupported_delete | understanding | unsupported | unsupported | yes |  | None | 1 | ₹0.012 |
| u_unsupported_policy | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.026 |
| u_unsupported_refund | understanding | unsupported | unsupported | yes |  | None | 2 | ₹0.025 |
