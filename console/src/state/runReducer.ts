import type {
  Approval,
  CostData,
  Fact,
  GoalContract,
  PendingMutation,
  Phase,
  PlanStep,
  Question,
  RunDetail,
  RunEvent,
  RunStatus,
  RunSummary,
  VerificationResult,
} from "../api/types";

/** One row of the run timeline: the event it came from, kept whole for rendering. */
export type TimelineItem = Exclude<RunEvent, { type: "run_status" | "phase" | "cost" | "fact" }>;

export interface RunView {
  summary: RunSummary;
  lastSeq: number;
  status: RunStatus;
  statusReason: string | null;
  phase: Phase;
  /** phases the run actually entered, in order; skipped ones are absent */
  visitedPhases: Phase[];
  plan: { steps: PlanStep[]; revision: number };
  facts: Record<string, Fact & { step?: number }>;
  factOrder: string[];
  contract: GoalContract | null;
  approvals: Record<string, Approval>;
  openApproval: Approval | null;
  question: Question | null;
  pending: Record<string, PendingMutation>;
  verification: VerificationResult | null;
  verificationRounds: number;
  cost: CostData | null;
  stepCount: number;
  timeline: TimelineItem[];
}

export function emptyRunView(summary: RunSummary): RunView {
  return {
    summary,
    lastSeq: 0,
    status: summary.status,
    statusReason: null,
    phase: summary.phase,
    visitedPhases: [summary.phase],
    plan: { steps: [], revision: 0 },
    facts: {},
    factOrder: [],
    contract: null,
    approvals: {},
    openApproval: null,
    question: null,
    pending: {},
    verification: null,
    verificationRounds: 0,
    cost: null,
    stepCount: 0,
    timeline: [],
  };
}

/**
 * Panels from the server's snapshot. lastSeq stays 0 so the event history can
 * still be replayed to build the timeline; every panel update is idempotent.
 */
export function hydrate(detail: RunDetail): RunView {
  const view = emptyRunView(detail.summary);
  const approvals = Object.fromEntries(detail.approvals.map((a) => [a.approval_id, a]));
  const facts = Object.fromEntries(detail.facts.map((f) => [f.key, f]));
  return {
    ...view,
    // revision 0 so the replayed history still adds the first plan row
    plan: { steps: detail.plan.steps, revision: 0 },
    facts,
    factOrder: detail.facts.map((f) => f.key),
    contract: detail.contract,
    approvals,
    openApproval: detail.approvals.find((a) => a.status === "pending") ?? null,
    question: detail.question,
    pending: Object.fromEntries(detail.pending.map((p) => [p.mutation_id, p])),
    verification: detail.verification,
  };
}

export function applyEvent(view: RunView, event: RunEvent): RunView {
  if (event.seq <= view.lastSeq) return view;
  const next: RunView = { ...view, lastSeq: event.seq };

  switch (event.type) {
    case "run_status":
      return { ...next, status: event.data.status, statusReason: event.data.reason ?? null };
    case "phase":
      return {
        ...next,
        phase: event.data.phase,
        visitedPhases: view.visitedPhases.includes(event.data.phase) ? view.visitedPhases : [...view.visitedPhases, event.data.phase],
      };
    case "cost":
      return { ...next, cost: event.data };
    case "fact": {
      const { key } = event.data;
      return {
        ...next,
        facts: { ...view.facts, [key]: event.data },
        factOrder: view.factOrder.includes(key) ? view.factOrder : [...view.factOrder, key],
      };
    }
    case "plan":
      return {
        ...next,
        plan: { steps: event.data.steps, revision: event.data.revision },
        // progress updates reuse the revision; only a new revision is worth a ledger row
        timeline: event.data.revision === view.plan.revision ? view.timeline : [...view.timeline, event],
      };
    case "step":
      return { ...next, stepCount: Math.max(view.stepCount, event.data.step), timeline: [...view.timeline, event] };
    case "contract":
      return {
        ...next,
        contract: event.data.action === "rejected" ? view.contract : (event.data.contract ?? view.contract),
        timeline: [...view.timeline, event],
      };
    case "approval": {
      const approvals = { ...view.approvals, [event.data.approval_id]: event.data };
      const open = Object.values(approvals).find((a) => a.status === "pending") ?? null;
      return { ...next, approvals, openApproval: open, timeline: [...view.timeline, event] };
    }
    case "question":
      return { ...next, question: event.data, timeline: [...view.timeline, event] };
    case "answer":
      return {
        ...next,
        question: view.question?.question_id === event.data.question_id ? null : view.question,
        timeline: [...view.timeline, event],
      };
    case "pending":
      return {
        ...next,
        pending: { ...view.pending, [event.data.mutation_id]: event.data },
        timeline: [...view.timeline, event],
      };
    case "verification":
      return {
        ...next,
        verification: event.data,
        verificationRounds: view.verificationRounds + 1,
        timeline: [...view.timeline, event],
      };
    case "gate":
    case "error":
      return { ...next, timeline: [...view.timeline, event] };
  }
}
