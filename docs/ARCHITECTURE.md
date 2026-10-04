# Architecture

Diagrams of the system as built. [DESIGN.md](DESIGN.md) explains the reasoning behind each part, and [INTERFACES.md](INTERFACES.md) fixes the console API.

The core idea: **the model picks the next action; code decides what is allowed, where each value came from, and whether the work is done.**

## 1. Components

```mermaid
flowchart LR
  subgraph Browser["Operator's browser"]
    UI["Console<br/>React 19 + Vite<br/>:8100"]
  end

  subgraph Worker["Worker process (Python, FastAPI)"]
    API["Console API<br/>sessions, runs, approvals,<br/>server-sent events"]
    Q["Run queue<br/>one run at a time"]
    LOOP["Worker loop<br/>runtime/loop.py"]
    PROMPT["Prompt builder<br/>goal, plan, facts,<br/>last actions, pages"]
    GOALS["Goal check<br/>verify/goals.py<br/>sources, field map, checks"]
    TOOLS["Task tools<br/>open_page, record_facts,<br/>fill_form, submit_form, …"]
    GATE["Write gate<br/>policy/gate.py<br/>provenance, permissions,<br/>approvals"]
    PEND["Pending writes<br/>write-ahead log,<br/>reconciliation"]
    VERIFY["Verifier<br/>read-back probes"]
    LEDGER["Spending ledger<br/>reserve, then settle"]
    MEM["Per-user memory<br/>suggests, never applies"]
    DB[("SQLite<br/>runs, events,<br/>approvals, ledger")]
  end

  subgraph Chromium["Chromium (Playwright)"]
    GUARD["Network guard<br/>allowlist, exact POST bodies"]
  end

  subgraph Sandbox["Sandbox company apps"]
    PORTAL["Supplier portal<br/>:8101"]
    REG["Invoice register<br/>:8102<br/>enforces permissions"]
  end

  LLM["LLM gateway<br/>AICredits, Gemini 2.5 Flash-Lite"]
  MANIFEST[("config/apps.yaml<br/>pages and procedures")]

  UI <-->|HTTP + SSE| API
  API --> Q --> LOOP
  LOOP --> PROMPT --> LLM
  LLM -->|tool call| LOOP
  MANIFEST --> PROMPT
  MANIFEST --> TOOLS
  LOOP --> GOALS
  LOOP --> TOOLS
  TOOLS --> GATE --> PEND
  TOOLS --> GUARD
  GUARD --> PORTAL
  GUARD --> REG
  LOOP --> VERIFY
  VERIFY -->|read-only probes| PORTAL
  VERIFY -->|read-only probes| REG
  LOOP --> LEDGER
  LOOP --> MEM
  LOOP --> DB
  API --> DB
```

| Part | Responsibility | Code |
| --- | --- | --- |
| Console | Start tasks, answer questions, approve exact values, read evidence | `console/src` |
| Console API | Sign-in, runs, approvals, answers, live event stream | `worker/console` |
| Worker loop | One model call per step, dispatch of task tools, phase changes | `worker/runtime/loop.py` |
| Manifest | What each app's pages are and which pages each goal reads and writes | `config/apps.yaml`, `worker/runtime/apps.py` |
| Goal check | Turns a proposed goal into a locked contract with frozen sources and checks | `worker/verify/goals.py` |
| Write gate | Refuses any write without provenance, permission or a valid approval | `worker/policy` |
| Network guard | Blocks other origins, probe APIs and any POST that is not the approved body | `worker/tools/network_guard.py` |
| Verifier | Reads the systems back and decides `completed` | `worker/verify/verifier.py` |
| Spending ledger | Reserves an estimate before each call; settles from the gateway's cost | `worker/llm/ledger.py` |

## 2. A run's phases

```mermaid
stateDiagram-v2
  [*] --> setup
  setup --> discover: signed in as the requesting user
  discover --> discover: open pages, record facts (read-only)
  discover --> question: goal unclear or ambiguous
  question --> discover: user answers
  question --> blocked: user says no
  discover --> unsupported: not a goal this worker does
  discover --> execute: goal locked by code
  execute --> approval: policy needs a person
  approval --> execute: approved (exact values)
  approval --> blocked: rejected or expired
  execute --> verify: model calls finish
  verify --> completed: every check passed on read-back
  verify --> partial: some checks passed
  verify --> failed: checks failed
  execute --> failed: step or spending limit
  completed --> [*]
  partial --> [*]
  blocked --> [*]
  failed --> [*]
  unsupported --> [*]
```

Run statuses are `queued`, `running`, `awaiting_input`, `awaiting_approval`, `completed`, `partial`, `blocked`, `failed`, `unsupported` and `interrupted`. Only the verifier can produce `completed`.

## 3. One write, end to end

```mermaid
sequenceDiagram
  autonumber
  participant M as Model
  participant L as Worker loop
  participant G as Write gate
  participant P as Pending log
  participant B as Chromium + guard
  participant R as Register
  participant V as Verifier
  participant U as Operator

  M->>L: fill_form([{label, fact}])
  L->>L: find each field by label, copy the fact's value
  M->>L: submit_form()
  L->>G: intent (fields, provenance, target, form token)
  G-->>L: needs approval: it changes an existing record
  L->>U: approval card with before and after values
  U->>L: approve (bound to values, version, policy, 15 min)
  M->>L: submit_form()
  L->>G: same intent
  G-->>L: allowed
  L->>P: record "dispatching" before sending
  L->>B: arm the exact POST body, click save
  B->>R: POST /invoices/1
  alt response lost or timed out
    L->>R: did this form token commit?
    R-->>L: yes, or no (then void it and allow a retry)
  end
  R-->>L: saved, version 2
  L->>P: mark "committed"
  M->>L: finish()
  L->>V: verify the locked goal
  V->>R: read the record back
  V-->>L: 5 of 5 checks passed
  L->>U: Done and verified, with evidence
```

## 4. What the model sees each turn

```mermaid
flowchart TB
  SYS["Fixed instructions<br/>same for every goal type"] --> MSG
  APPS["Company context<br/>pages and procedures from the manifest"] --> MSG
  REQ["The user's request<br/>and answers"] --> MSG
  GOAL["Locked goal, or none yet"] --> MSG
  PLAN["Plan and progress<br/>built by code from evidence"] --> MSG
  FACTS["Facts recorded so far<br/>copied from pages by code"] --> MSG
  ACTS["Last 12 actions and results"] --> MSG
  PAGES["Last 3 page observations<br/>wrapped as untrusted page text"] --> MSG
  MSG["Messages"] --> LLM["Model"]
  TOOLSET["Tools for this phase<br/>no write tools before the goal is locked"] --> LLM
  LLM --> CALL["One tool call per change of page"]
```

## 5. Evaluation tiers

```mermaid
flowchart LR
  subgraph Free["Free, every commit (CI)"]
    UNIT["pytest + Vitest<br/>281 + 35 tests"]
    FAKE["Scripted fake model<br/>21 tasks + 11 controls"]
  end
  subgraph Live["Live model, paid"]
    DEV["Development set<br/>16 tasks + 11 controls"]
    HELD["Held-out set<br/>11 tasks, never tuned on"]
    UND["Understanding set<br/>24 requests, stops at the goal"]
  end
  ORACLE["Oracle<br/>snapshot before each run,<br/>audit every write by actor"]
  FAKE --> ORACLE
  DEV --> ORACLE
  HELD --> ORACLE
  UND --> ORACLE
  ORACLE --> REPORT["Reports in evals/<br/>README tables generated"]
```

## 6. Deployment

```mermaid
flowchart LR
  subgraph Image["Docker image task-worker"]
    direction TB
    NODE["build stage: node 22<br/>npm ci, vite build"] -.->|console/dist| PY
    PY["python 3.12 + uv<br/>Chromium with system deps"]
    DEVPY["scripts/dev.py starts<br/>portal :8101, register :8102,<br/>worker + console :8100"]
    PY --> DEVPY
  end
  ENV[".env<br/>AICREDITS_API_KEY"] --> Image
  VOL[("volume worker-data<br/>/app/data")] --- Image
  HOST["Host 127.0.0.1:8100-8102"] --- Image
```
