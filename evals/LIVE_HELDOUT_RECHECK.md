# Evaluation report

Tier: live  
Model: `google/gemini-2.5-flash-lite`  
Output cap: 512 tokens; tool choice: required; temperature: provider default  
Prompt SHA-256: `2ba2835ebe53aa592e0f40863cf26dc09a97cf21e4b37cff4cbf11369719fc3f`  
Reference date: 2026-10-03; seed: 7

| Metric | Result |
| --- | ---: |
| Task success | 2/2 |
| Control pass | 0/0 |
| Field correctness | 1/1 |
| False completions | 0/2 |
| Unauthorized writes | 0/2 |
| Duplicate records | 0/2 |
| Task success, heldout | 2/2 |
| Tool calls | 20/2 runs |
| Latency | 23.82 s/2 runs |
| Settled cost | ₹0.647946/2 scenarios |

## Scenarios

| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| h_batch_other_supplier | heldout | completed | completed | yes |  | True | 12 | ₹0.444 |
| h_contact_update | heldout | completed | completed | yes |  | None | 8 | ₹0.204 |
