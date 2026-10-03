# Provider smoke test

Run on 2026-10-03 with the locally configured key; no key or response text was
saved. The documented `https://api.aicredits.in/v1` endpoint worked. The request
used `google/gemini-2.5-flash`; the gateway echoed `gemini-2.5-flash`. Both
requests returned a structured `get_time` tool call.

| Request | Prompt tokens | Completion tokens | Total tokens | Gateway cost |
| --- | ---: | ---: | ---: | ---: |
| Default | 32 | 10 | 89 | ₹0.017414 |
| `reasoning_effort=low` | 32 | 10 | 92 | ₹0.018273 |

The parameter was accepted but did not reduce visible completion tokens or
reported cost in this small trial, so the runtime will omit it. Total gateway
cost for this smoke was about ₹0.035687. The catalogue-rate estimate based on
the returned prompt/completion token fields was ₹0.003501 per request, much lower
than the gateway's reported charge. The difference is consistent with billed
thinking tokens excluded from `completion_tokens`; it is not a verified breakdown.
The ledger should settle from the gateway's reported INR cost when available,
and treat reservations as estimated local limits. The smoke did not test a
tool-result follow-up round trip or a full worker run.

The same T1 smoke was repeated with `google/gemini-2.5-flash-lite` before any
full live run. Both requests returned the `get_time` tool call. The default and
`reasoning_effort=low` calls each reported 32 prompt tokens, 10 completion
tokens, 42 total tokens, and ₹0.000824332 gateway cost. The catalogue-rate
estimate from the visible token fields was ₹0.00072864 per call. This tiny
sample supports Flash Lite as the budget-conscious eval setting; it does not
establish the cost of a complete agent run.

References: [AICredits API reference](https://aicredits.in/docs/api-reference),
[pricing and thinking-token billing](https://aicredits.in/docs/pricing).
