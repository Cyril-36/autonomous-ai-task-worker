# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `8c29bd37c55577d7206d842bbd6e159bda9905852f3232f34e7c8cd3ec6ccb26`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 1/1 |
| Control pass | 0/0 |
| Field correctness | 1/1 |
| False completions | 0/1 |
| Unauthorized writes | 0/1 |
| Unexpected writes | 0/1 |
| Duplicate records | 0/1 |
| Tool calls | 8/1 runs |
| Latency | 10.87 s/1 runs |
| Settled cost | ₹0.297501/1 scenarios |

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| sync_existing_invoice | dev | completed | completed | yes |  | True | 8 | ₹0.298 |

## Script-only scenarios excluded from live tier

`missing_source`, `provider_failure`, `stale_ref`, `offsite_navigation`, `crash_after_dispatch`

