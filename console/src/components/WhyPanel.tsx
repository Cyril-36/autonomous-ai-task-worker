import type { GoalContract, RunStatus, VerificationResult } from "../api/types";
import { GOAL_LABEL, readableReason, statusMeta } from "../format";
import type { TimelineItem } from "../state/runReducer";

interface WhyPanelProps {
  contract: GoalContract | null;
  timeline: TimelineItem[];
  verification: VerificationResult | null;
  status: RunStatus;
  reason: string | null;
}

function restatedAction(timeline: TimelineItem[]): string | null {
  const committed = [...timeline].reverse().find((item) =>
    item.type === "step" && item.data.tool === "commit_goal" && item.data.ok);
  if (!committed || committed.type !== "step") return null;
  const proposal = committed.data.args.contract;
  if (!proposal || typeof proposal !== "object") return null;
  const action = (proposal as Record<string, unknown>).requested_action;
  return typeof action === "string" && action.trim() ? action : null;
}

function decisionText(item: TimelineItem): string | null {
  if (item.type === "gate" && !item.data.allowed) return item.data.reason;
  if (item.type === "question") return item.data.text;
  if (item.type === "approval" && item.data.status === "pending") return item.data.reason;
  if (item.type === "approval" && item.data.status === "rejected") return "Approval was rejected.";
  if (item.type === "approval" && item.data.status === "invalidated") return "Approval was invalidated after the record or policy changed.";
  if (item.type === "pending" && item.data.state === "conflict") return item.data.reason ?? "The saved record conflicted with the intended values.";
  return null;
}

export function WhyPanel({ contract, timeline, verification, status, reason }: WhyPanelProps) {
  const action = restatedAction(timeline);
  const results = new Map(verification?.checks.map((check) => [check.obligation_id, check]) ?? []);
  const decisions = [...new Set(timeline.map(decisionText).filter((value): value is string => !!value))].slice(-4);
  const statusLabel = statusMeta(status, status === "completed" ? verification?.passed === true : undefined).label;
  // A reason already listed above is not repeated as the outcome; the status says where things stand.
  const outcome = reason && !decisions.includes(reason) ? readableReason(reason) : statusLabel;
  return (
    <section className="sheet sheet-pad stack" aria-labelledby="why-h">
      <div className="sheet-head"><h2 id="why-h" className="sheet-title">Why it did that</h2></div>
      <div className="why-part">
        <h3>Interpreted action</h3>
        <p>{action ?? (contract ? GOAL_LABEL[contract.goal_type] : "No action has been locked yet.")}</p>
      </div>
      {contract && (
        <div className="why-part">
          <h3>Checks required</h3>
          <ul>{contract.obligations.map((obligation) => {
            const check = results.get(obligation.obligation_id);
            return <li key={obligation.obligation_id}>{obligation.description}{check ? ` — ${check.passed ? "passed" : "failed"} on read-back` : " — pending"}</li>;
          })}</ul>
        </div>
      )}
      {decisions.length > 0 && (
        <div className="why-part">
          <h3>Pause or refusal reasons</h3>
          <ul>{decisions.map((decision, index) => <li key={`${index}-${decision}`}>{decision}</li>)}</ul>
        </div>
      )}
      <div className="why-part">
        <h3>Current outcome</h3>
        <p>{outcome}</p>
      </div>
    </section>
  );
}
