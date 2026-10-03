# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 3/3 |
| Control pass | 0/0 |
| Field correctness | 1/2 |
| False completions | 0/3 |
| Unauthorized writes | 0/3 |
| Duplicate records | 0/3 |
| Tool calls | 50/3 runs |
| Latency | 61.07 s/3 runs |
| Settled cost | ₹1.822627/3 scenarios |

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| wrong_saved_field | dev | failed | failed | yes |  | False | 39 | ₹1.516 |
| large_amount_approved | dev | completed | completed | yes |  | True | 8 | ₹0.250 |
| export_due_before | dev | completed | completed | yes |  | None | 3 | ₹0.057 |

## Script-only scenarios excluded from live tier

`missing_source`, `provider_failure`, `stale_ref`, `offsite_navigation`, `crash_after_dispatch`

