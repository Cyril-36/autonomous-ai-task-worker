---
title: Task Worker
emoji: 🧾
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8100
pinned: false
short_description: AI worker that does browser tasks, then proves them
---

# Task Worker

An AI worker that takes a plain-language request, does the work in a real browser across two sandbox company apps, and reports done only when an independent read-back proves it.

Sign in with a sandbox account:

| Account | Password | May change |
| --- | --- | --- |
| `ravi@example.com` | `ravi-demo` | Larkspur Supplies, Brightfen Paper |
| `meera@example.com` | `meera-demo` | Kestrova Components |
| `asha@example.com` | `asha-demo` | Everything, including policy (admin) |

Try the example buttons: "Latest invoice", "Correct an existing invoice" (asks for approval) or "Ambiguous supplier" (asks a question).

Each task makes live model calls; this deployment stops new runs at a small spending cap. Data resets when the Space restarts. Source, design, evaluation results and the demo video: https://github.com/Cyril-36/autonomous-ai-task-worker
