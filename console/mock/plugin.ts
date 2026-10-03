// Dev-only mock of docs/INTERFACES.md §1. Enabled with VITE_MOCK=1 (`npm run dev:mock`).
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";
import { buildScript, type Beat } from "./scripts.ts";

interface User { user_id: string; email: string; display_name: string; role: "admin" | "operator"; suppliers: string[] }
interface Run {
  summary: Record<string, unknown> & { run_id: string; status: string; phase: string; steps: number; cost_inr: string };
  owner: string;
  events: Record<string, unknown>[];
  queue: Beat[];
  waiting: Extract<Beat, { pause: string }> | null;
  listeners: Set<ServerResponse>;
  timer: ReturnType<typeof setInterval> | null;
}

const PASSWORD = "sandbox-demo";
const USERS: User[] = [
  { user_id: "u_ravi", email: "ravi@example.com", display_name: "Ravi Menon", role: "operator", suppliers: ["Larkspur Supplies", "Brightfen Paper"] },
  { user_id: "u_meera", email: "meera@example.com", display_name: "Meera Pillai", role: "operator", suppliers: ["Kestrova Components"] },
  { user_id: "u_asha", email: "asha@example.com", display_name: "Asha Rao", role: "admin", suppliers: [] },
];
const TERMINAL = new Set(["completed", "partial", "blocked", "failed", "unsupported"]);
const runs = new Map<string, Run>();
let globalSpent = 4.28;
let counter = 0;

const principal = (u: User) => ({ user_id: u.user_id, email: u.email, display_name: u.display_name, role: u.role });

function send(res: ServerResponse, status: number, body?: unknown) {
  res.statusCode = status;
  if (body === undefined) return res.end();
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}
const fail = (res: ServerResponse, status: number, code: string, message: string) => send(res, status, { error: { code, message } });

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  try {
    return JSON.parse(Buffer.concat(chunks).toString() || "{}");
  } catch {
    return {};
  }
}

function currentUser(req: IncomingMessage): User | undefined {
  const m = /console_session=([^;]+)/.exec(req.headers.cookie ?? "");
  return m ? USERS.find((u) => u.email === decodeURIComponent(m[1])) : undefined;
}

function emit(run: Run, type: string, data: Record<string, unknown>) {
  const event = { run_id: run.summary.run_id, seq: run.events.length + 1, ts: new Date().toISOString(), type, data };
  run.events.push(event);
  if (type === "run_status") run.summary.status = data.status as string;
  if (type === "phase") run.summary.phase = data.phase as string;
  if (type === "step") run.summary.steps = data.step as number;
  if (type === "cost") {
    run.summary.cost_inr = data.run_spent_inr as string;
    globalSpent = Number(data.global_spent_inr);
  }
  run.summary.updated_at = event.ts;
  for (const res of run.listeners) writeEvent(res, event);
  if (type === "run_status" && TERMINAL.has(data.status as string)) {
    for (const res of run.listeners) {
      res.write("event: end\ndata: {}\n\n");
      res.end();
    }
    run.listeners.clear();
  }
}

function writeEvent(res: ServerResponse, event: Record<string, unknown>) {
  res.write(`id: ${event.seq}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
}

function pump(run: Run) {
  if (run.timer) return;
  run.timer = setInterval(() => {
    if (run.waiting) return;
    const beat = run.queue.shift();
    if (!beat) {
      clearInterval(run.timer!);
      run.timer = null;
      return;
    }
    if ("pause" in beat) {
      run.waiting = beat;
      return;
    }
    emit(run, beat.type, beat.data);
    // register a pause as soon as the event announcing it is out, so answers can't race it
    const next = run.queue[0];
    if (next && "pause" in next) run.waiting = run.queue.shift() as Extract<Beat, { pause: string }>;
  }, 650);
}

function detail(run: Run) {
  const latest = <T,>(type: string) => [...run.events].reverse().find((e) => e.type === type)?.data as T | undefined;
  const approvals = new Map<string, Record<string, unknown>>();
  const facts = new Map<string, Record<string, unknown>>();
  const pending = new Map<string, Record<string, unknown>>();
  let question: Record<string, unknown> | null = null;
  let contract: unknown = null;
  for (const e of run.events) {
    const d = e.data as Record<string, unknown>;
    if (e.type === "approval") approvals.set(d.approval_id as string, d);
    if (e.type === "fact") facts.set(d.key as string, d);
    if (e.type === "pending") pending.set(d.mutation_id as string, d);
    if (e.type === "question") question = d;
    if (e.type === "answer") question = null;
    if (e.type === "contract" && d.contract) contract = d.contract;
  }
  return {
    summary: run.summary,
    contract,
    plan: latest<Record<string, unknown>>("plan") ?? { steps: [], revision: 0 },
    facts: [...facts.values()],
    approvals: [...approvals.values()],
    question,
    verification: latest("verification") ?? null,
    pending: [...pending.values()],
    budget: budget(run),
    last_seq: run.events.length,
  };
}

function budget(run?: Run) {
  return {
    ...(run ? { run_spent_inr: run.summary.cost_inr, run_limit_inr: "4.00" } : {}),
    global_spent_inr: globalSpent.toFixed(2),
    global_reserved_inr: "0.00",
    global_limit_inr: "30.00",
    estimated: true,
  };
}

const EXAMPLES = [
  { title: "Enter the latest invoice", request: "Find the latest invoice from Larkspur Supplies, enter its amount and due date in our register, and show me the saved record.", notes: "Over ₹1,00,000, so it asks for approval." },
  { title: "Ambiguous supplier", request: "Enter the latest invoice from Larkspur.", notes: "Two suppliers match; it asks which one." },
  { title: "Check before registering", request: "Has Brightfen's invoice BF-2291 been registered? If not, register it.", notes: "Already registered; nothing is written." },
  { title: "Export due invoices", request: "Export a CSV of registered invoices due before 31 Oct 2026.", notes: "Writes a file under exports/." },
];

export function mockApi(): Plugin {
  return {
    name: "task-worker-mock-api",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://localhost");
        const path = url.pathname;
        if (!path.startsWith("/api/")) return next();
        const method = req.method ?? "GET";

        if (path === "/api/demo-users" && method === "GET") {
          return send(res, 200, USERS.map((u) => ({ email: u.email, display_name: u.display_name, role: u.role, assigned_suppliers: u.suppliers, password_hint: `Sandbox password: ${PASSWORD}` })));
        }
        if (path === "/api/session" && method === "POST") {
          const body = await readJson(req);
          const user = USERS.find((u) => u.email === body.email);
          if (!user || body.password !== PASSWORD) return fail(res, 401, "bad_credentials", "That email and password don't match a sandbox account.");
          res.setHeader("Set-Cookie", `console_session=${encodeURIComponent(user.email)}; Path=/; HttpOnly; SameSite=Lax`);
          return send(res, 200, principal(user));
        }
        if (path === "/api/session" && method === "DELETE") {
          res.setHeader("Set-Cookie", "console_session=; Path=/; Max-Age=0");
          return send(res, 204);
        }

        const user = currentUser(req);
        if (!user) return fail(res, 401, "not_signed_in", "Sign in to continue.");
        if (path === "/api/me") return send(res, 200, principal(user));
        if (path === "/api/examples") return send(res, 200, EXAMPLES);
        if (path === "/api/budget") return send(res, 200, budget());

        if (path === "/api/runs" && method === "GET") {
          const visible = [...runs.values()].filter((r) => user.role === "admin" || r.owner === user.email);
          return send(res, 200, visible.map((r) => r.summary).reverse());
        }
        if (path === "/api/runs" && method === "POST") {
          const body = await readJson(req);
          const text = typeof body.request === "string" ? body.request.trim() : "";
          if (text.length < 1 || text.length > 2000) return fail(res, 422, "invalid_request", "Describe the task in 1 to 2,000 characters.");
          if (globalSpent >= 30) return fail(res, 402, "budget_exhausted", "The estimated spending limit of ₹30 has been reached. No new runs can start.");
          counter += 1;
          const runId = `run_${(0x7f3a + counter).toString(16)}`;
          const now = new Date().toISOString();
          const run: Run = {
            summary: { run_id: runId, request: text, principal: principal(user), status: "queued", phase: "setup", created_at: now, updated_at: now, steps: 0, cost_inr: "0.00", model: "google/gemini-2.5-flash-lite" },
            owner: user.email, events: [], queue: buildScript(runId, text, user), waiting: null, listeners: new Set(), timer: null,
          };
          runs.set(runId, run);
          pump(run);
          return send(res, 201, run.summary);
        }

        const m = /^\/api\/runs\/([^/]+)(\/.*)?$/.exec(path);
        if (!m) return fail(res, 404, "not_found", "No such endpoint.");
        const run = runs.get(m[1]);
        if (!run) return fail(res, 404, "not_found", "That run doesn't exist.");
        if (user.role !== "admin" && run.owner !== user.email) return fail(res, 403, "forbidden", "This run belongs to another user.");
        const sub = m[2] ?? "";

        if (sub === "" && method === "GET") return send(res, 200, detail(run));
        if (sub === "/events") {
          const after = Number(url.searchParams.get("after") ?? 0);
          return send(res, 200, run.events.filter((e) => (e.seq as number) > after));
        }
        if (sub === "/stream") {
          res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
          const after = Number(req.headers["last-event-id"] ?? 0);
          for (const e of run.events) if ((e.seq as number) > after) writeEvent(res, e);
          if (TERMINAL.has(run.summary.status)) {
            res.write("event: end\ndata: {}\n\n");
            return res.end();
          }
          run.listeners.add(res);
          const keepalive = setInterval(() => res.write(": keepalive\n\n"), 15000);
          req.on("close", () => {
            clearInterval(keepalive);
            run.listeners.delete(res);
          });
          return;
        }
        if (sub === "/answer" && method === "POST") {
          if (run.summary.status !== "awaiting_input" || run.waiting?.pause !== "answer") return fail(res, 409, "conflict", "This run isn't waiting for an answer.");
          const body = await readJson(req);
          const text = String(body.text ?? "").trim();
          if (!text) return fail(res, 422, "invalid_request", "Type an answer first.");
          const waiting = run.waiting;
          run.waiting = null;
          emit(run, "answer", { question_id: waiting.questionId, text, by: user.display_name });
          run.queue.unshift(...waiting.then(text));
          pump(run);
          return send(res, 202);
        }
        const am = /^\/approvals\/([^/]+)$/.exec(sub);
        if (am && method === "POST") {
          if (run.waiting?.pause !== "approval" || run.waiting.approvalId !== am[1]) return fail(res, 409, "conflict", "This approval is no longer pending.");
          const body = await readJson(req);
          if (body.decision !== "approve" && body.decision !== "reject") return fail(res, 422, "invalid_request", "Decision must be approve or reject.");
          const waiting = run.waiting;
          run.waiting = null;
          run.queue.unshift(...(body.decision === "approve" ? waiting.onApprove : waiting.onReject));
          pump(run);
          const approval = [...run.events].reverse().find((e) => e.type === "approval")?.data as Record<string, unknown>;
          return send(res, 200, { ...approval, status: body.decision === "approve" ? "approved" : "rejected", decided_by: user.display_name });
        }
        if (sub === "/cancel" && method === "POST") {
          run.queue = [];
          run.waiting = null;
          emit(run, "phase", { phase: "done" });
          emit(run, "run_status", { status: "failed", reason: "cancelled_by_user" });
          return send(res, 202);
        }
        if (sub.startsWith("/artifacts/")) return fail(res, 404, "not_found", "The mock has no screenshots.");
        return fail(res, 404, "not_found", "No such endpoint.");
      });
    },
  };
}
