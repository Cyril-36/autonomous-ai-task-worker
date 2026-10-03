# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 1/1 |
| Control pass | 0/0 |
| Field correctness | 1/1 |
| False completions | 0/1 |
| Unauthorized writes | 0/1 |
| Duplicate records | 0/1 |
| Tool calls | 11/1 runs |
| Latency | 14.16 s/1 runs |
| Settled cost | ₹0.382056/1 scenarios |

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| transient_503 | dev | completed | completed | yes |  | True | 11 | ₹0.382 |

## Script-only scenarios excluded from live tier

`missing_source`, `provider_failure`, `stale_ref`, `offsite_navigation`, `crash_after_dispatch`

