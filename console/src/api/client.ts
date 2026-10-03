import type {
  Approval,
  Budget,
  DemoUser,
  Example,
  Principal,
  RunDetail,
  RunEvent,
  RunSummary,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type Method = "GET" | "POST" | "DELETE";

export async function parseError(res: Response): Promise<ApiError> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "error" in body) {
      const err = (body as { error: { code?: unknown; message?: unknown } }).error;
      if (typeof err?.code === "string" && typeof err?.message === "string") {
        return new ApiError(res.status, err.code, err.message);
      }
    }
  } catch {
    // fall through to the generic error below
  }
  return new ApiError(res.status, "unexpected_response", `The server answered ${res.status} without an explanation.`);
}

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach the worker. Check that the backend is running on port 8100.");
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204 || res.status === 202) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  demoUsers: () => request<DemoUser[]>("GET", "/api/demo-users"),
  signIn: (email: string, password: string) => request<Principal>("POST", "/api/session", { email, password }),
  me: () => request<Principal>("GET", "/api/me"),
  signOut: () => request<void>("DELETE", "/api/session"),
  examples: () => request<Example[]>("GET", "/api/examples"),
  runs: () => request<RunSummary[]>("GET", "/api/runs"),
  createRun: (text: string) => request<RunSummary>("POST", "/api/runs", { request: text }),
  run: (runId: string) => request<RunDetail>("GET", `/api/runs/${encodeURIComponent(runId)}`),
  events: (runId: string, after: number) =>
    request<RunEvent[]>("GET", `/api/runs/${encodeURIComponent(runId)}/events?after=${after}`),
  answer: (runId: string, text: string) =>
    request<void>("POST", `/api/runs/${encodeURIComponent(runId)}/answer`, { text }),
  decide: (runId: string, approvalId: string, decision: "approve" | "reject", note?: string) =>
    request<Approval>(
      "POST",
      `/api/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`,
      { decision, note },
    ),
  cancel: (runId: string) => request<void>("POST", `/api/runs/${encodeURIComponent(runId)}/cancel`),
  budget: () => request<Budget>("GET", "/api/budget"),
  artifactUrl: (runId: string, name: string) =>
    `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`,
};
