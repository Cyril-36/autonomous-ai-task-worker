import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { Budget, DemoUser, Principal, RunSummary } from "./api/types";
import { RunView } from "./components/RunView";
import { TopBar } from "./components/Shell";
import { SignIn } from "./components/SignIn";
import { Composer, RunList } from "./components/Sidebar";
import { useRun } from "./state/useRun";

function routeRunId(): string | null {
  const m = /^#\/runs\/([\w-]+)/.exec(window.location.hash);
  return m ? m[1] : null;
}

function useHashRoute(): string | null {
  const [runId, setRunId] = useState(routeRunId);
  useEffect(() => {
    const onHash = () => setRunId(routeRunId());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return runId;
}

export default function App() {
  const [user, setUser] = useState<Principal | null>(null);
  const [checked, setChecked] = useState(false);
  const [scope, setScope] = useState("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const runId = useHashRoute();
  const run = useRun(user ? runId : null);

  const describe = useCallback((u: Principal, demo: DemoUser[]) => {
    const d = demo.find((x) => x.email === u.email);
    setScope(u.role === "admin" ? "Admin, all suppliers" : `Operator, ${d?.assigned_suppliers.join(", ") ?? "assigned suppliers"}`);
  }, []);

  useEffect(() => {
    Promise.all([api.me(), api.demoUsers().catch(() => [] as DemoUser[])])
      .then(([u, demo]) => {
        setUser(u);
        describe(u, demo);
      })
      .catch(() => {
        // 401 means "not signed in": the sign-in screen handles it
      })
      .finally(() => setChecked(true));
  }, [describe]);

  const loadRuns = useCallback(() => {
    api.runs().then(setRuns).catch(() => undefined);
    api.budget().then(setBudget).catch(() => undefined);
  }, []);

  // Refresh the list on sign-in, on navigation and whenever the open run changes status.
  useEffect(() => {
    if (user) loadRuns();
  }, [user, runId, run.view?.status, loadRuns]);

  // Keep the list's statuses honest while any listed run is still moving.
  useEffect(() => {
    if (!user) return;
    const active = runs.some((r) => !["completed", "partial", "blocked", "failed", "unsupported"].includes(r.status));
    if (!active) return;
    const t = setInterval(loadRuns, 4000);
    return () => clearInterval(t);
  }, [user, runs, loadRuns]);

  if (!checked) return null;
  if (!user) {
    return (
      <SignIn
        onSignedIn={(u, demo) => {
          setUser(u);
          describe(u, demo);
          window.location.hash = "#/";
        }}
      />
    );
  }

  async function signOut() {
    await api.signOut().catch(() => undefined);
    setUser(null);
    setRuns([]);
    window.location.hash = "#/";
  }

  return (
    <>
      <TopBar user={user} scope={scope} budget={run.budget ?? budget} onSignOut={signOut} />
      <div className="layout">
        <aside className="col-left">
          <Composer
            onStarted={(r) => {
              setRuns((list) => [r, ...list]);
              window.location.hash = `#/runs/${r.run_id}`;
            }}
          />
          <RunList user={user} runs={runs} currentId={runId} />
        </aside>
        {runId ? (
          <RunView run={run} />
        ) : (
          <section className="col-main">
            <div className="sheet sheet-pad stack">
              <h1 className="run-title">Give the worker a task</h1>
              <p className="muted" style={{ maxWidth: "60ch" }}>
                Describe the outcome you want. It reads what it needs from the supplier portal, makes changes in the register as you,
                pauses when policy needs your approval, and shows the checks it passed when it's done.
              </p>
            </div>
          </section>
        )}
      </div>
    </>
  );
}
