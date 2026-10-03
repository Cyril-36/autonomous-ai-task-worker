import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { Approval } from "../api/types";

function useCountdown(iso: string): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, new Date(iso).getTime() - now);
  if (left === 0) return "expired";
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  return `expires in ${m}:${String(s).padStart(2, "0")}`;
}

interface ApprovalCardProps {
  runId: string;
  approval: Approval;
}

export function ApprovalCard({ runId, approval }: ApprovalCardProps) {
  const countdown = useCountdown(approval.expires_at);
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const expired = countdown === "expired";

  async function decide(decision: "approve" | "reject") {
    if (decision === "reject" && !confirmReject) {
      setConfirmReject(true);
      return;
    }
    setBusy(decision);
    setError(null);
    try {
      await api.decide(runId, approval.approval_id, decision);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The decision wasn't recorded. Try again.");
      setBusy(null);
    }
  }

  return (
    <section className="card-wait" aria-labelledby="approval-h">
      <div className="sheet-head">
        <h2 id="approval-h">Approve before it saves</h2>
        <span className="mono" style={{ color: "var(--wait-ink)", fontSize: 12 }}>
          {countdown}
        </span>
      </div>
      <p>
        {approval.reason} You are approving exactly these values for <strong>{approval.target_label}</strong>. If any of
        them, the record or the policy change, this approval stops applying and it asks again.
      </p>
      <div className="table-box">
        <table className="diff">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Now</th>
              <th scope="col">After saving</th>
            </tr>
          </thead>
          <tbody>
            {approval.changes.map((c) => (
              <tr key={c.field}>
                <td>{c.field}</td>
                <td className="old">{c.old ?? "empty"}</td>
                <td className="new">{c.new}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="actions">
        <button type="button" className="btn btn-primary btn-lg" disabled={busy !== null || expired} onClick={() => decide("approve")}>
          {busy === "approve" ? "Approving…" : "Approve and save"}
        </button>
        <button
          type="button"
          className="btn btn-lg"
          disabled={busy !== null || expired}
          onClick={() => decide("reject")}
          style={confirmReject ? { borderColor: "var(--stop-ink)", color: "var(--stop-ink)" } : undefined}
        >
          {busy === "reject" ? "Rejecting…" : confirmReject ? "Confirm: reject and save nothing" : "Reject"}
        </button>
        {confirmReject && busy === null && (
          <button type="button" className="btn btn-quiet" onClick={() => setConfirmReject(false)}>
            Keep it pending
          </button>
        )}
      </div>
    </section>
  );
}

interface QuestionCardProps {
  runId: string;
  question: { question_id: string; text: string };
}

export function QuestionCard({ runId, question }: QuestionCardProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) {
      setError("Type an answer first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.answer(runId, text.trim());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The answer wasn't sent. Try again.");
      setBusy(false);
    }
  }

  return (
    <form className="card-wait" aria-labelledby="question-h" onSubmit={submit}>
      <h2 id="question-h">It needs an answer to continue</h2>
      <p style={{ fontSize: 14, color: "var(--ink)" }}>{question.text}</p>
      <div className="field">
        <label htmlFor="answer">Your answer</label>
        <input id="answer" className="input" value={text} onChange={(e) => setText(e.target.value)} disabled={busy} autoFocus />
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="actions">
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
          {busy ? "Sending…" : "Send answer"}
        </button>
      </div>
    </form>
  );
}
