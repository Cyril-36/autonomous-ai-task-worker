// Mirrors worker/contracts.py and docs/INTERFACES.md §1. Money and decimals are strings.

export type Role = "admin" | "operator";

export interface Principal {
  user_id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface DemoUser {
  email: string;
  display_name: string;
  role: Role;
  assigned_suppliers: string[];
  password_hint: string;
}

export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_input"
  | "awaiting_approval"
  | "completed"
  | "partial"
  | "blocked"
  | "failed"
  | "unsupported"
  | "interrupted";

export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "partial",
  "blocked",
  "failed",
  "unsupported",
]);

export type Phase = "setup" | "discover" | "execute" | "verify" | "done";
export const PHASES: Phase[] = ["setup", "discover", "execute", "verify", "done"];

export interface RunSummary {
  run_id: string;
  request: string;
  principal: Principal;
  status: RunStatus;
  phase: Phase;
  created_at: string;
  updated_at: string;
  steps: number;
  cost_inr: string;
  model: string;
}

export type FactType = "amount" | "date" | "text";

export interface Fact {
  key: string;
  value: string;
  normalized: string;
  type: FactType;
  observation_id: string;
  url: string;
  doc_id: string | null;
  revision: string | null;
  field_locator: string;
}

export interface PlanStep {
  text: string;
  status: "todo" | "doing" | "done" | "blocked";
}

export type GoalType =
  | "register_invoice"
  | "check_or_register_invoice"
  | "register_batch"
  | "update_supplier_contact"
  | "export_invoices";

export interface SourceRef {
  app: "portal";
  kind: "invoice" | "message";
  doc_id: string;
  revision: string;
  supplier_id: string;
  key: string;
}

export interface Obligation {
  obligation_id: string;
  kind: string;
  description: string;
  params: Record<string, unknown>;
}

export interface FieldMapping {
  target_field: string;
  source_label: string;
  type: FactType;
}

export interface RequestConstraints {
  supplier_text: string | null;
  selector: string | null;
  invoice_numbers: string[];
  dates: string[];
  cap: number | null;
}

export interface GoalContract {
  contract_id: string;
  run_id: string;
  goal_type: GoalType;
  constraints: RequestConstraints;
  supplier_id: string | null;
  supplier_name: string | null;
  sources: SourceRef[];
  batch_remaining: SourceRef[];
  filter: Record<string, string> | null;
  field_map: FieldMapping[];
  obligations: Obligation[];
  locked_at: string;
  revision: number;
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "used" | "expired" | "invalidated";

export interface ValueChange {
  field: string;
  old: string | null;
  new: string;
}

export interface Approval {
  approval_id: string;
  run_id: string;
  intent_hash: string;
  reason: string;
  changes: ValueChange[];
  target_label: string;
  target_version: number | null;
  policy_version: number;
  expires_at: string;
  status: ApprovalStatus;
  decided_by: string | null;
  decided_at: string | null;
}

export type PendingState = "dispatching" | "committed" | "rejected" | "voided" | "conflict";

export interface PendingMutation {
  mutation_id: string;
  run_id: string;
  form_token: string | null;
  target_key: Record<string, string>;
  before_values: Record<string, string> | null;
  before_version: number | null;
  intended_values: Record<string, string>;
  state: PendingState;
  reason: string | null;
  retries: number;
}

export interface CheckResult {
  obligation_id: string;
  description: string;
  passed: boolean;
  expected: string | null;
  actual: string | null;
  detail: string | null;
}

export interface EvidenceItem {
  label: string;
  value: string;
  url: string | null;
  screenshot_path: string | null;
}

export interface VerificationResult {
  run_id: string;
  contract_id: string;
  passed: boolean;
  checks: CheckResult[];
  status: RunStatus;
  summary: string;
  evidence: EvidenceItem[];
  remaining: string[];
}

export interface Budget {
  run_spent_inr?: string;
  run_limit_inr?: string;
  global_spent_inr: string;
  global_reserved_inr: string;
  global_limit_inr: string;
  estimated: true;
}

/** candidates: the choices code found; suggested: this user's earlier choice (memory). */
export interface Question {
  question_id: string;
  text: string;
  candidates?: string[];
  suggested?: string;
}

export interface RunDetail {
  summary: RunSummary;
  contract: GoalContract | null;
  plan: { steps: PlanStep[]; revision: number };
  facts: Fact[];
  approvals: Approval[];
  question: Question | null;
  verification: VerificationResult | null;
  pending: PendingMutation[];
  budget: Budget;
  last_seq: number;
}

export interface Example {
  title: string;
  request: string;
  notes: string;
}

export type GateCode =
  | "allowed"
  | "needs_approval"
  | "phase_discover"
  | "no_contract"
  | "origin_blocked"
  | "path_blocked"
  | "provenance_failed"
  | "field_mismatch"
  | "source_mismatch"
  | "pending_unresolved"
  | "approval_invalid"
  | "filename_invalid"
  | "query_mismatch"
  | "not_a_mutation";

export interface StepData {
  step: number;
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  summary: string;
  url?: string;
  observation_id?: string;
  screenshot?: string;
  error_code?: string;
  duration_ms: number;
  skipped?: boolean;
}

export interface GateData {
  step: number;
  allowed: boolean;
  code: GateCode;
  reason: string;
  mutation?: { action_url: string; fields: Record<string, string>; target_label?: string };
}

export interface CostData {
  run_spent_inr: string;
  run_limit_inr: string;
  global_spent_inr: string;
  global_limit_inr: string;
  prompt_tokens: number;
  completion_tokens: number;
  model: string;
}

interface EventBase<T extends string, D> {
  run_id: string;
  seq: number;
  ts: string;
  type: T;
  data: D;
}

export type RunEvent =
  | EventBase<"run_status", { status: RunStatus; reason?: string }>
  | EventBase<"phase", { phase: Phase }>
  | EventBase<"plan", { steps: PlanStep[]; revision: number; reason?: string }>
  | EventBase<"step", StepData>
  | EventBase<"fact", Fact & { step: number }>
  | EventBase<"contract", { action: "committed" | "revised" | "rejected"; reason?: string; contract?: GoalContract }>
  | EventBase<"gate", GateData>
  | EventBase<"approval", Approval>
  | EventBase<"question", Question>
  | EventBase<"answer", { question_id: string; text: string; by: string }>
  | EventBase<"pending", PendingMutation>
  | EventBase<"verification", VerificationResult>
  | EventBase<"cost", CostData>
  | EventBase<"error", { code: string; message: string; retryable: boolean }>;

export type RunEventType = RunEvent["type"];
