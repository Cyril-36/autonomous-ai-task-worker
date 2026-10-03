import type { GoalType, RunStatus } from "./api/types";

export type Tone = "run" | "wait" | "ok" | "stop" | "idle";

const STATUS: Record<RunStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "idle" },
  running: { label: "Working", tone: "run" },
  awaiting_input: { label: "Needs your answer", tone: "wait" },
  awaiting_approval: { label: "Needs your approval", tone: "wait" },
  completed: { label: "Done and verified", tone: "ok" },
  partial: { label: "Partly done", tone: "wait" },
  blocked: { label: "Blocked", tone: "stop" },
  failed: { label: "Failed", tone: "stop" },
  unsupported: { label: "Not something it can do", tone: "stop" },
  interrupted: { label: "Interrupted, resuming", tone: "wait" },
};

export function statusMeta(status: RunStatus): { label: string; tone: Tone } {
  return STATUS[status] ?? { label: status, tone: "idle" };
}

/** "118400.00" -> "₹1,18,400.00" with Indian digit grouping, without float arithmetic. */
export function formatInr(amount: string): string {
  const m = /^(-?)(\d+)(?:\.(\d+))?$/.exec(amount.trim());
  if (!m) return amount;
  const [, sign, whole, frac = ""] = m;
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3);
  const grouped = rest ? `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${last3}` : last3;
  return `${sign}₹${grouped}.${(frac + "00").slice(0, 2)}`;
}

const TOOLS: Record<string, string> = {
  setup: "Sign in",
  browser_navigate: "Open page",
  browser_click: "Click",
  browser_fill: "Type",
  browser_select: "Choose",
  browser_snapshot: "Look",
  reauthenticate: "Sign in again",
  files_list: "List files",
  files_read: "Read file",
  files_write: "Write file",
  update_plan: "Plan",
  record_fact: "Note facts",
  commit_goal: "Commit goal",
  revise_goal: "Revise goal",
  ask_user: "Ask you",
  finish: "Finish",
};

export function toolLabel(tool: string): string {
  return TOOLS[tool] ?? tool.replace(/_/g, " ");
}

const APPS: Record<string, string> = { "8101": "Portal", "8102": "Register" };

/** "http://127.0.0.1:8101/invoices/doc_1" -> { app: "Portal", path: "/invoices/doc_1" } */
export function describeUrl(url: string): { app: string; path: string } {
  try {
    const u = new URL(url);
    return { app: APPS[u.port] ?? u.host, path: `${u.pathname}${u.search}` };
  } catch {
    return { app: "", path: url };
  }
}

export function clock(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function shortTime(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function initials(name: string): string {
  return name.split(/\s+/).map((p) => p[0] ?? "").join("").slice(0, 2).toUpperCase();
}

export function seconds(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

export const GOAL_LABEL: Record<GoalType, string> = {
  register_invoice: "Register an invoice",
  check_or_register_invoice: "Check, then register if missing",
  register_batch: "Register a batch of invoices",
  update_supplier_contact: "Update a supplier contact",
  export_invoices: "Export invoices",
};

