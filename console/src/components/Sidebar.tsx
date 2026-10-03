import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { Example, Principal, RunSummary } from "../api/types";
import { count, shortTime, statusMeta } from "../format";

interface ComposerProps {
  onStarted: (run: RunSummary) => void;
}

export function Composer({ onStarted }: ComposerProps) {
  const [text, setText] = useState("");
  const [examples, setExamples] = useState<Example[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.examples().then(setExamples).catch(() => setExamples([]));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) {
      setError("Describe what you want done.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun(text.trim());
      setText("");
      onStarted(run);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The run didn't start. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="sheet sheet-pad stack" onSubmit={submit} aria-labelledby="new-h">
      <h2 id="new-h" className="sheet-title">New task</h2>
      <div className="field">
        <label htmlFor="task" className="sr-only">Task</label>
        <textarea
          id="task"
          className="textarea"
          rows={4}
          maxLength={2000}
          placeholder="Say what you want done, for example: enter the latest Larkspur Supplies invoice in the register."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      {examples.length > 0 && (
        <div className="chips" aria-label="Examples">
          {examples.map((ex) => (
            <button key={ex.title} type="button" className="chip" title={ex.notes} onClick={() => setText(ex.request)}>
              {ex.title}
            </button>
          ))}
        </div>
      )}
      {error && <p className="error-text" role="alert">{error}</p>}
      <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
        {busy ? "Starting…" : "Start task"}
      </button>
    </form>
  );
}

interface RunListProps {
  user: Principal;
  runs: RunSummary[];
  currentId: string | null;
}

export function RunList({ user, runs, currentId }: RunListProps) {
  return (
    <nav className="sheet" aria-labelledby="runs-h">
      <h2 id="runs-h" className="sheet-title" style={{ padding: "14px 14px 4px" }}>
        {user.role === "admin" ? "All runs" : "Your runs"}
      </h2>
      {runs.length === 0 ? (
        <p className="empty">No runs yet. Start one above, or pick an example.</p>
      ) : (
        <ul className="run-list">
          {runs.map((r) => {
            const meta = statusMeta(r.status);
            return (
              <li key={r.run_id}>
                <a className="run-link" href={`#/runs/${r.run_id}`} aria-current={r.run_id === currentId ? "page" : undefined}>
                  <span className="run-req">{r.request}</span>
                  <span className="run-meta">
                    <span className={`pill tone-${meta.tone}`}>{meta.label}</span>
                    <span>
                      {user.role === "admin" && r.principal.user_id !== user.user_id ? `${r.principal.display_name}, ` : ""}
                      {shortTime(r.created_at)}, {count(r.steps, "step")}
                    </span>
                  </span>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
