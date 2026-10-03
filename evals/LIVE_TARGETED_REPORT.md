# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `b14c6e075aa402ed2d09415513e0b39b8d35278f53837f045bbb8b34ab610bb8`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 1/1 |
| Control pass | 0/0 |
| Field correctness | 1/1 |
| False completions | 0/1 |
| Unauthorized writes | 0/1 |
| Duplicate records | 0/1 |
| Tool calls | 12/1 runs |
| Latency | 14.52 s/1 runs |
| Settled cost | ₹0.460352/1 scenarios |

## Scenarios

| ID | Expected | Actual | Success | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | ---: | ---: |
| intake_first_time | completed | completed | yes | True | 12 | ₹0.460351843075887916 |

## Script-only scenarios excluded from live tier

`missing_source`, `provider_failure`, `stale_ref`, `offsite_navigation`, `crash_after_dispatch`

