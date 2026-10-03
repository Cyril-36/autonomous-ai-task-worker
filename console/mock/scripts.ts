// Scripted runs for the dev mock. Shapes follow docs/INTERFACES.md §1.
// Each script is a list of beats; a beat is an event payload, or a pause that
// waits for the user's approval decision or answer.

type Data = Record<string, unknown>;
export type Beat =
  | { type: string; data: Data }
  | { pause: "approval"; approvalId: string; onApprove: Beat[]; onReject: Beat[] }
  | { pause: "answer"; questionId: string; then: (answer: string) => Beat[] };

const P = "http://127.0.0.1:8101";
const R = "http://127.0.0.1:8102";
let stepNo = 0;

function step(tool: string, summary: string, extra: Data = {}): Beat {
  stepNo += 1;
  return {
    type: "step",
    data: { step: stepNo, tool, args: {}, ok: true, summary, duration_ms: 300 + ((stepNo * 137) % 700), ...extra },
  };
}

function fact(key: string, label: string, value: string, normalized: string, type: string, doc: string, s: number): Beat {
  return {
    type: "fact",
    data: {
      key, value, normalized, type, observation_id: `obs_${String(s).padStart(4, "0")}`,
      url: `${P}/invoices/${doc}`, doc_id: doc, revision: "3", field_locator: label, step: s,
    },
  };
}

const plan = (steps: string[], doing: number, revision = 1, reason?: string): Beat => ({
  type: "plan",
  data: {
    steps: steps.map((text, i) => ({ text, status: i < doing ? "done" : i === doing ? "doing" : "todo" })),
    revision,
    ...(reason ? { reason } : {}),
  },
});

const status = (s: string, reason?: string): Beat => ({ type: "run_status", data: { status: s, ...(reason ? { reason } : {}) } });
const phase = (p: string): Beat => ({ type: "phase", data: { phase: p } });

function contract(runId: string, opts: { supplier: string; supplierId: string; doc: string; key: string; obligations: string[]; goal?: string }): Beat {
  return {
    type: "contract",
    data: {
      action: "committed",
      contract: {
        contract_id: `c_${runId}`,
        run_id: runId,
        goal_type: opts.goal ?? "register_invoice",
        constraints: { supplier_text: opts.supplier, selector: "latest", invoice_numbers: [], dates: [], cap: null },
        supplier_id: opts.supplierId,
        supplier_name: opts.supplier,
        sources: opts.doc ? [{ app: "portal", kind: "invoice", doc_id: opts.doc, revision: "3", supplier_id: opts.supplierId, key: opts.key }] : [],
        batch_remaining: [],
        filter: null,
        field_map: [
          { target_field: "amount", source_label: "Amount", type: "amount" },
          { target_field: "due_date", source_label: "Due date", type: "date" },
          { target_field: "currency", source_label: "Currency", type: "text" },
        ],
        obligations: opts.obligations.map((d, i) => ({ obligation_id: `o${i + 1}`, kind: "record_fields", description: d, params: {} })),
        locked_at: "2026-10-03T14:02:00Z",
        revision: 1,
      },
    },
  };
}

function cost(spent: number, tokens: number): Beat {
  return {
    type: "cost",
    data: {
      run_spent_inr: spent.toFixed(2), run_limit_inr: "4.00", global_spent_inr: (4.28 + spent).toFixed(2),
      global_limit_inr: "30.00", prompt_tokens: tokens, completion_tokens: Math.round(tokens / 30), model: "google/gemini-2.5-flash-lite",
    },
  };
}

const INTAKE_PLAN = [
  "Find Larkspur Supplies' latest invoice on the portal",
  "Record its amount, currency and due date",
  "Commit the goal so the source is frozen",
  "Enter the invoice in the register",
  "Check the saved record matches the invoice",
];

const INTAKE_OBLIGATIONS = [
  "Supplier resolves to exactly one supplier",
  "Source is that supplier's latest portal invoice",
  "Exactly one register row for Larkspur Supplies, LS-1042",
  "Saved amount and currency equal the source",
  "Saved due date equals the source",
];

function verification(runId: string, passed: boolean, checks: [string, string, string][], summary: string, extra: Data = {}): Beat {
  return {
    type: "verification",
    data: {
      run_id: runId, contract_id: `c_${runId}`, passed, status: passed ? "completed" : "partial", summary,
      checks: checks.map(([description, expected, actual], i) => ({
        obligation_id: `o${i + 1}`, description, passed: true, expected, actual, detail: null,
      })),
      evidence: [
        { label: "Saved record", value: "INV-0217", url: `${R}/invoices/217`, screenshot_path: null },
        { label: "Source invoice", value: "LS-1042, revision 3", url: `${P}/invoices/doc_ls1042`, screenshot_path: null },
      ],
      remaining: [],
      ...extra,
    },
  };
}

function intakeDiscovery(): Beat[] {
  return [
    step("browser_navigate", "Opened the portal invoice list", { url: `${P}/invoices` }),
    cost(0.06, 4100),
    step("browser_click", "Filtered by supplier Larkspur Supplies: 4 invoices", { url: `${P}/invoices?supplier=larkspur-supplies` }),
    step("browser_click", "Opened LS-1042, issued 28 Sep 2026, the most recent", { url: `${P}/invoices/doc_ls1042`, screenshot: "step-04.png" }),
  ];
}

function intakeFacts(amount: string, normalized: string): Beat[] {
  const s = stepNo;
  return [
    fact("invoice_number", "Invoice number", "LS-1042", "LS-1042", "text", "doc_ls1042", s),
    fact("amount", "Amount", amount, normalized, "amount", "doc_ls1042", s),
    fact("due_date", "Due date", "20 Oct 2026", "2026-10-20", "date", "doc_ls1042", s),
    fact("currency", "Currency", "INR", "INR", "text", "doc_ls1042", s),
    step("record_fact", "Recorded 4 facts from the invoice page"),
    plan(INTAKE_PLAN, 2),
    cost(0.21, 6900),
  ];
}

function intakeEntry(runId: string, normalized: string): Beat[] {
  return [
    contract(runId, { supplier: "Larkspur Supplies", supplierId: "larkspur-supplies", doc: "doc_ls1042", key: "LS-1042", obligations: INTAKE_OBLIGATIONS }),
    phase("execute"),
    plan(INTAKE_PLAN, 3),
    step("browser_navigate", "Opened New invoice in the register", { url: `${R}/invoices/new` }),
    step("browser_select", "Supplier set to Larkspur Supplies"),
    step("browser_fill", "Invoice number set to LS-1042 from the invoice"),
    step("browser_fill", `Amount set to ${normalized} from the invoice`),
    step("browser_fill", "Due date set to 2026-10-20 from the invoice"),
    cost(0.38, 8200),
  ];
}

function intakeFinish(runId: string, amountShown: string, normalized: string, recovered: boolean): Beat[] {
  const pending = {
    mutation_id: "mut_44e1", run_id: runId, form_token: "•••",
    target_key: { supplier: "larkspur-supplies", invoice_number: "LS-1042" },
    before_values: null, before_version: null, intended_values: { amount: normalized, due_date: "2026-10-20", currency: "INR" },
    reason: null, retries: 0,
  };
  const save: Beat[] = recovered
    ? [
        { ...step("browser_click", "Clicked Save: no response within 8 seconds", { url: `${R}/invoices/new`, error_code: "timeout" }), },
        { type: "pending", data: { ...pending, state: "dispatching", reason: "The save request got no answer. Further saves for LS-1042 are on hold until this is settled." } },
        { type: "pending", data: { ...pending, state: "committed", reason: "The register confirms the save went through as INV-0217. It was not saved a second time." } },
      ]
    : [
        step("browser_click", "Clicked Save", { url: `${R}/invoices/217`, screenshot: "step-11.png" }),
        { type: "pending", data: { ...pending, state: "committed", reason: "Saved as INV-0217." } },
      ];
  if (recovered) {
    const failed = save[0] as { type: string; data: Data };
    failed.data.ok = false;
  }
  return [
    ...save,
    plan(INTAKE_PLAN, 4),
    phase("verify"),
    step("finish", "Proposed that the task is complete"),
    verification(
      runId,
      true,
      [
        ["Supplier resolves to exactly one supplier", "Larkspur Supplies", "Larkspur Supplies"],
        ["Source is the latest portal invoice", "issued 28 Sep 2026", "LS-1042, 28 Sep 2026"],
        ["Exactly one register row", "1", "1 (INV-0217)"],
        ["Saved amount and currency equal the source", `${normalized} INR`, `${normalized} INR`],
        ["Saved due date equals the source", "2026-10-20", "2026-10-20"],
      ],
      `Invoice LS-1042 from Larkspur Supplies is saved as INV-0217: ${amountShown}, due 20 Oct 2026.${recovered ? " The first save timed out; the register confirmed it had gone through, so it was not saved twice." : ""}`,
    ),
    plan(INTAKE_PLAN, 5),
    cost(0.52, 10400),
    phase("done"),
    status("completed"),
  ];
}

export function buildScript(runId: string, request: string, user: { email: string; display_name: string }): Beat[] {
  stepNo = 0;
  const text = request.toLowerCase();
  const opening: Beat[] = [
    status("running"),
    phase("setup"),
    step("setup", `Signed in to the supplier portal and the register as ${user.display_name}`),
    phase("discover"),
  ];

  if (user.email.startsWith("meera")) {
    return [
      ...opening,
      plan(INTAKE_PLAN, 0),
      ...intakeDiscovery(),
      ...intakeFacts("₹48,250.00", "48250.00"),
      contract(runId, { supplier: "Larkspur Supplies", supplierId: "larkspur-supplies", doc: "doc_ls1042", key: "LS-1042", obligations: INTAKE_OBLIGATIONS }),
      phase("execute"),
      step("browser_navigate", "Opened New invoice in the register", { url: `${R}/invoices/new` }),
      step("browser_select", "Supplier set to Larkspur Supplies"),
      step("browser_click", "Clicked Save: the register refused", { url: `${R}/invoices/new` }),
      { type: "pending", data: { mutation_id: "mut_9a01", run_id: runId, form_token: "•••", target_key: { supplier: "larkspur-supplies", invoice_number: "LS-1042" }, before_values: null, before_version: null, intended_values: {}, state: "rejected", reason: "Register answered 403: Meera Pillai is not assigned to Larkspur Supplies.", retries: 0 } },
      phase("done"),
      status("blocked", "The register only lets Meera Pillai change Kestrova Components. Nothing was saved. Ask an admin to assign Larkspur Supplies, or have Ravi Menon run this task."),
    ];
  }

  if (text.includes("export")) {
    return [
      ...opening,
      plan(["Open the register's invoice list", "Commit the goal with the due-date filter", "Write the export file", "Check the file matches the register"], 0),
      step("browser_navigate", "Opened the register invoice list", { url: `${R}/invoices` }),
      { type: "contract", data: { action: "committed", contract: { ...((contract(runId, { supplier: "", supplierId: "", doc: "", key: "", obligations: ["Export file exists under exports/", "Rows equal the register's invoices due before 31 Oct 2026, none missing, none extra"], goal: "export_invoices" }) as unknown as { data: { contract: Data } }).data.contract), supplier_id: null, supplier_name: null, filter: { due_before: "2026-10-31" } } } },
      phase("execute"),
      step("files_write", "Wrote exports/due-before-2026-10-31.csv with 6 rows from the register"),
      phase("verify"),
      step("finish", "Proposed that the task is complete"),
      { ...verification(runId, true, [["Export file exists", "exports/due-before-2026-10-31.csv", "present"], ["Rows match the register", "6 rows", "6 rows, none missing, none extra"]], "Exported 6 invoices due before 31 Oct 2026 to exports/due-before-2026-10-31.csv."), },
      cost(0.19, 5200),
      phase("done"),
      status("completed"),
    ];
  }

  if (/larkspur\.?$/.test(text.trim()) || text.includes("from larkspur.")) {
    return [
      ...opening,
      step("browser_navigate", "Opened the portal invoice list", { url: `${P}/invoices` }),
      step("browser_click", "Searched suppliers for Larkspur: 2 matches", { url: `${P}/invoices?q=larkspur` }),
      { type: "contract", data: { action: "rejected", reason: "Two suppliers match \"Larkspur\": Larkspur Supplies and Larkspur Logistics. The goal can't be committed until one is chosen." } },
      { type: "question", data: { question_id: "q1", text: "Supplier name is ambiguous. Which one did you mean: Larkspur Supplies or Larkspur Logistics?", candidates: ["Larkspur Supplies", "Larkspur Logistics"] } },
      status("awaiting_input"),
      {
        pause: "answer",
        questionId: "q1",
        then: () => [
          status("running"),
          plan(INTAKE_PLAN, 0, 2, "Supplier confirmed by the user"),
          step("browser_click", "Filtered by supplier Larkspur Supplies: 4 invoices", { url: `${P}/invoices?supplier=larkspur-supplies` }),
          step("browser_click", "Opened LS-1042, issued 28 Sep 2026, the most recent", { url: `${P}/invoices/doc_ls1042` }),
          ...intakeFacts("₹48,250.00", "48250.00"),
          ...intakeEntry(runId, "48250.00"),
          ...intakeFinish(runId, "₹48,250.00", "48250.00", false),
        ],
      },
    ];
  }

  const approval = {
    approval_id: "apr_19c2", run_id: runId, intent_hash: "sha256:7c1e…", reason: "Policy v1: invoices of ₹1,00,000 or more need approval before saving.",
    changes: [
      { field: "Supplier", old: null, new: "Larkspur Supplies" },
      { field: "Invoice number", old: null, new: "LS-1042" },
      { field: "Amount", old: null, new: "₹1,18,400.00 INR" },
      { field: "Due date", old: null, new: "20 Oct 2026" },
    ],
    target_label: "New invoice LS-1042 for Larkspur Supplies", target_version: null, policy_version: 1,
    expires_at: new Date(Date.now() + 15 * 60_000).toISOString(), decided_by: null, decided_at: null,
  };
  return [
    ...opening,
    plan(INTAKE_PLAN, 0),
    ...intakeDiscovery(),
    ...intakeFacts("₹1,18,400.00", "118400.00"),
    ...intakeEntry(runId, "118400.00"),
    { type: "gate", data: { step: stepNo + 1, allowed: false, code: "needs_approval", reason: "Saving is paused: the amount is ₹1,00,000 or more, so policy v1 needs your approval. All 4 values trace to invoice LS-1042, revision 3.", mutation: { action_url: `${R}/invoices`, fields: { supplier_id: "larkspur-supplies", invoice_number: "LS-1042", amount: "118400.00", due_date: "2026-10-20", form_token: "•••" }, target_label: approval.target_label } } },
    { type: "approval", data: { ...approval, status: "pending" } },
    status("awaiting_approval"),
    {
      pause: "approval",
      approvalId: "apr_19c2",
      onApprove: [
        { type: "approval", data: { ...approval, status: "approved", decided_by: user.display_name, decided_at: new Date().toISOString() } },
        status("running"),
        ...intakeFinish(runId, "₹1,18,400.00", "118400.00", true),
      ],
      onReject: [
        { type: "approval", data: { ...approval, status: "rejected", decided_by: user.display_name, decided_at: new Date().toISOString() } },
        phase("done"),
        status("blocked", "You rejected the save, so nothing was written to the register. The invoice values found are kept below if you want to start again."),
      ],
    },
  ];
}
