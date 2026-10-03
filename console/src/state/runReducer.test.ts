import { describe, expect, it } from "vitest";
import type { Approval, PendingMutation, RunEvent, RunSummary, VerificationResult } from "../api/types";
import { applyEvent, emptyRunView, hydrate } from "./runReducer";

const summary: RunSummary = {
  run_id: "r1",
  request: "Enter the latest Larkspur Supplies invoice",
  principal: { user_id: "u1", email: "ravi@example.com", display_name: "Ravi Menon", role: "operator" },
  status: "queued",
  phase: "setup",
  created_at: "2026-10-03T14:00:00Z",
  updated_at: "2026-10-03T14:00:00Z",
  steps: 0,
  cost_inr: "0.00",
  model: "google/gemini-2.5-flash-lite",
};

let seq = 0;
function ev<T extends RunEvent["type"]>(type: T, data: Extract<RunEvent, { type: T }>["data"]): RunEvent {
  seq += 1;
  return { run_id: "r1", seq, ts: "2026-10-03T14:00:00Z", type, data } as RunEvent;
}

const approval: Approval = {
  approval_id: "a1",
  run_id: "r1",
  intent_hash: "h",
  reason: "Amount is ₹1,00,000 or more (policy v1)",
  changes: [{ field: "amount", old: null, new: "118400.00" }],
  target_label: "New invoice LS-1042, Larkspur Supplies",
  target_version: null,
  policy_version: 1,
  expires_at: "2026-10-03T14:15:00Z",
  status: "pending",
  decided_by: null,
  decided_at: null,
};

const pending: PendingMutation = {
  mutation_id: "m1",
  run_id: "r1",
  form_token: "•••",
  target_key: { supplier: "larkspur-supplies", invoice_number: "LS-1042" },
  before_values: null,
  before_version: null,
  intended_values: { amount: "118400.00" },
  state: "dispatching",
  reason: null,
  retries: 0,
};

const verification: VerificationResult = {
  run_id: "r1",
  contract_id: "c1",
  passed: true,
  checks: [{ obligation_id: "o1", description: "Exactly one row", passed: true, expected: "1", actual: "1", detail: null }],
  status: "completed",
  summary: "Saved as INV-0217",
  evidence: [],
  remaining: [],
};

describe("applyEvent", () => {
  it("tracks status with its reason and phase", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("run_status", { status: "blocked", reason: "Not assigned to you" }));
    v = applyEvent(v, ev("phase", { phase: "done" }));
    expect(v.status).toBe("blocked");
    expect(v.statusReason).toBe("Not assigned to you");
    expect(v.phase).toBe("done");
  });

  it("keeps plan revisions as history", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("plan", { steps: [{ text: "a", status: "todo" }], revision: 1 }));
    v = applyEvent(v, ev("plan", { steps: [{ text: "b", status: "doing" }], revision: 2, reason: "save failed" }));
    expect(v.plan.steps[0].text).toBe("b");
    expect(v.plan.revision).toBe(2);
    expect(v.timeline.filter((t) => t.type === "plan")).toHaveLength(2);
  });

  it("adds a plan row only when the revision changes", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("plan", { steps: [{ text: "a", status: "doing" }], revision: 1 }));
    v = applyEvent(v, ev("plan", { steps: [{ text: "a", status: "done" }], revision: 1 }));
    expect(v.plan.steps[0].status).toBe("done");
    expect(v.timeline.filter((t) => t.type === "plan")).toHaveLength(1);
  });

  it("counts steps and keeps them in the timeline", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("step", { step: 1, tool: "browser_navigate", args: {}, ok: true, summary: "Opened", duration_ms: 400 }));
    v = applyEvent(v, ev("step", { step: 2, tool: "browser_click", args: {}, ok: false, summary: "Timed out", duration_ms: 8000, error_code: "timeout" }));
    expect(v.stepCount).toBe(2);
    expect(v.timeline.map((t) => t.type)).toEqual(["step", "step"]);
  });

  it("keys facts and keeps first-seen order", () => {
    let v = emptyRunView(summary);
    const base = { value: "₹1,18,400.00", normalized: "118400.00", type: "amount" as const, observation_id: "o7", url: "http://127.0.0.1:8101/invoices/d1", doc_id: "d1", revision: "3", field_locator: "Amount", step: 3 };
    v = applyEvent(v, ev("fact", { key: "amount", ...base }));
    v = applyEvent(v, ev("fact", { key: "due_date", ...base, normalized: "2026-10-20", type: "date" }));
    v = applyEvent(v, ev("fact", { key: "amount", ...base, normalized: "118400.00" }));
    expect(v.factOrder).toEqual(["amount", "due_date"]);
  });

  it("records contract commit and rejection", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("contract", { action: "rejected", reason: "LS-1040 is not the latest" }));
    expect(v.contract).toBeNull();
    expect(v.timeline.at(-1)?.type).toBe("contract");
  });

  it("updates approvals by id and exposes the pending one", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("approval", approval));
    expect(v.openApproval?.approval_id).toBe("a1");
    v = applyEvent(v, ev("approval", { ...approval, status: "approved", decided_by: "Ravi Menon" }));
    expect(v.openApproval).toBeNull();
    expect(v.approvals.a1.status).toBe("approved");
  });

  it("opens and closes questions", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("question", { question_id: "q1", text: "Which Larkspur?" }));
    expect(v.question?.text).toBe("Which Larkspur?");
    v = applyEvent(v, ev("answer", { question_id: "q1", text: "Larkspur Supplies", by: "Ravi Menon" }));
    expect(v.question).toBeNull();
  });

  it("tracks pending mutation state changes", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("pending", pending));
    v = applyEvent(v, ev("pending", { ...pending, state: "committed" }));
    expect(v.pending.m1.state).toBe("committed");
    expect(v.timeline.filter((t) => t.type === "pending")).toHaveLength(2);
  });

  it("keeps the latest verification and counts rounds", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("verification", { ...verification, passed: false, status: "running" }));
    v = applyEvent(v, ev("verification", verification));
    expect(v.verification?.passed).toBe(true);
    expect(v.verificationRounds).toBe(2);
  });

  it("keeps the latest cost", () => {
    let v = emptyRunView(summary);
    v = applyEvent(v, ev("cost", { run_spent_inr: "0.40", run_limit_inr: "4.00", global_spent_inr: "5.10", global_limit_inr: "30.00", prompt_tokens: 9000, completion_tokens: 300, model: "m" }));
    expect(v.cost?.run_spent_inr).toBe("0.40");
  });

  it("ignores an event it has already applied", () => {
    let v = emptyRunView(summary);
    const step = ev("step", { step: 1, tool: "browser_navigate", args: {}, ok: true, summary: "Opened", duration_ms: 1 });
    v = applyEvent(v, step);
    const again = applyEvent(v, step);
    expect(again).toBe(v);
    expect(again.stepCount).toBe(1);
  });
});

describe("hydrate", () => {
  it("replaying history after a snapshot shows the first plan once", () => {
    const detail = {
      summary, contract: null, plan: { steps: [{ text: "a", status: "doing" as const }], revision: 1 }, facts: [], approvals: [],
      question: null, verification: null, pending: [],
      budget: { global_spent_inr: "0.00", global_reserved_inr: "0.00", global_limit_inr: "30.00", estimated: true as const }, last_seq: 2,
    };
    let v = hydrate(detail);
    v = applyEvent(v, { run_id: "r1", seq: 1, ts: "2026-10-03T14:00:00Z", type: "plan", data: { steps: [{ text: "a", status: "todo" }], revision: 1 } });
    v = applyEvent(v, { run_id: "r1", seq: 2, ts: "2026-10-03T14:00:00Z", type: "plan", data: { steps: [{ text: "a", status: "doing" }], revision: 1 } });
    expect(v.timeline.filter((t) => t.type === "plan")).toHaveLength(1);
    expect(v.plan.steps[0].status).toBe("doing");
  });
});
