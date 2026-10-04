import { api } from "../api/client";
import type { PendingState } from "../api/types";
import { GOAL_LABEL, clock, describeUrl, seconds, toolLabel } from "../format";
import type { TimelineItem } from "../state/runReducer";


type Kind = "" | "k-ok" | "k-stop" | "k-wait" | "k-run";

interface Row {
  n: string;
  kind: string;
  tone: Kind;
  text: string;
  sub?: React.ReactNode;
  screenshot?: string;
}

const PENDING: Record<PendingState, { kind: string; tone: Kind }> = {
  dispatching: { kind: "Saving", tone: "k-run" },
  committed: { kind: "Confirmed", tone: "k-ok" },
  rejected: { kind: "Refused", tone: "k-stop" },
  voided: { kind: "Not saved", tone: "k-run" },
  conflict: { kind: "Conflict", tone: "k-stop" },
};

function UrlNote({ url, extra }: { url?: string; extra?: string }) {
  if (!url && !extra) return null;
  const u = url ? describeUrl(url) : null;
  return (
    <span className="row-sub">
      {u && (
        <>
          {u.app} <span className="mono">{u.path}</span>
        </>
      )}
      {u && extra ? ", " : null}
      {extra}
    </span>
  );
}

function toRow(item: TimelineItem): Row {
  switch (item.type) {
    case "step": {
      const d = item.data;
      if (d.paused) {
        // The approval or question row next to it carries the reason; this row only marks the wait.
        return {
          n: String(d.step),
          kind: toolLabel(d.tool),
          tone: "k-wait",
          text: d.tool === "submit_form" ? "Waiting for your approval before saving." : "Waiting for your answer.",
          screenshot: d.screenshot,
        };
      }
      const failed = !d.ok;
      return {
        n: String(d.step),
        kind: d.skipped ? "Skipped" : toolLabel(d.tool),
        tone: failed ? "k-stop" : "",
        text: d.summary,
        sub: <UrlNote url={d.url} extra={[failed && d.error_code ? `error: ${d.error_code}` : "", d.duration_ms > 0 ? seconds(d.duration_ms) : ""].filter(Boolean).join(", ")} />,
        screenshot: d.screenshot,
      };
    }
    case "gate": {
      const d = item.data;
      const kind = d.allowed ? "Allowed" : d.code === "needs_approval" ? "Paused" : "Refused";
      return {
        n: "",
        kind,
        tone: d.allowed ? "k-ok" : d.code === "needs_approval" ? "k-wait" : "k-stop",
        text: d.reason,
        sub: d.mutation?.target_label ? <span className="row-sub">{d.mutation.target_label}</span> : undefined,
      };
    }
    case "contract": {
      const d = item.data;
      if (d.action === "rejected" || !d.contract) {
        return { n: "", kind: "Goal refused", tone: "k-stop", text: d.reason ?? "The proposed goal was not accepted." };
      }
      const c = d.contract;
      const sources = c.sources.map((s) => s.key).join(", ");
      return {
        n: "",
        kind: d.action === "revised" ? "Goal revised" : "Goal locked",
        tone: "k-run",
        text: `${GOAL_LABEL[c.goal_type]}${c.supplier_name ? ` for ${c.supplier_name}` : ""}${sources ? `, source ${sources}` : ""}. Changes are allowed from here on.`,
        sub: <span className="row-sub">{c.obligations.length} checks to pass before it counts as done</span>,
      };
    }
    case "plan": {
      const d = item.data;
      return {
        n: "",
        kind: "Plan",
        tone: "",
        text: d.revision <= 1 ? `Wrote a ${d.steps.length}-step plan` : `Revised the plan${d.reason ? `: ${d.reason}` : ""}`,
        sub: <span className="row-sub">version {d.revision}</span>,
      };
    }
    case "approval": {
      const d = item.data;
      if (d.status === "pending") return { n: "", kind: "Approval", tone: "k-wait", text: `Asked you to approve: ${d.target_label}` };
      const by = d.decided_by ? ` by ${d.decided_by}` : "";
      const map = {
        approved: ["Approved", "k-ok", `Approved${by}`],
        rejected: ["Rejected", "k-stop", `Rejected${by}. Nothing was saved.`],
        used: ["Approval used", "k-ok", "The approval was used for exactly the approved values."],
        expired: ["Expired", "k-stop", "The approval expired before it was used."],
        invalidated: ["Invalidated", "k-stop", "The approval no longer applies because the record or policy changed."],
      } as const;
      const [kind, tone, text] = map[d.status];
      return { n: "", kind, tone, text };
    }
    case "question":
      return { n: "", kind: "Question", tone: "k-wait", text: item.data.text };
    case "answer":
      return { n: "", kind: "Answer", tone: "", text: `${item.data.by}: “${item.data.text}”` };
    case "pending": {
      const d = item.data;
      const meta = PENDING[d.state];
      const fallback = {
        dispatching: "Recorded the save before sending it, so its outcome can always be checked. Other changes to this record wait until it is settled.",
        committed: "The register confirms the save went through.",
        rejected: "The register refused the change.",
        voided: "Confirmed the save never happened, so it is safe to try again.",
        conflict: "The record now holds different values than intended.",
      } as const;
      return {
        n: "",
        kind: meta.kind,
        tone: meta.tone,
        text: d.reason ?? fallback[d.state],
        sub: <span className="row-sub mono">{Object.values(d.target_key).join(" / ")}</span>,
      };
    }
    case "verification": {
      const d = item.data;
      const passed = d.checks.filter((c) => c.passed).length;
      return {
        n: "",
        kind: d.passed ? "Verified" : "Check failed",
        tone: d.passed ? "k-ok" : "k-stop",
        text: d.passed
          ? `${passed} of ${d.checks.length} checks passed by reading the result back`
          : `${d.checks.length - passed} of ${d.checks.length} checks failed: ${d.checks.filter((c) => !c.passed).map((c) => c.description).join("; ")}`,
      };
    }
    case "error":
      return { n: "", kind: "Error", tone: "k-stop", text: item.data.message, sub: <span className="row-sub">{item.data.retryable ? "will retry" : "not retried"}</span> };
  }
}

/** A refused goal that turned into a question is shown once, as the question. */
export function visibleItems(items: TimelineItem[]): TimelineItem[] {
  return items.filter((item, index) => {
    if (item.type !== "contract" || item.data.action !== "rejected" || !item.data.reason) return true;
    const reason = item.data.reason;
    return !items.slice(index + 1, index + 3).some((next) => next.type === "question" && next.data.text.startsWith(reason));
  });
}

interface LedgerProps {
  runId: string;
  items: TimelineItem[];
  fresh: ReadonlySet<number>;
  working: boolean;
  onOpenShot: (src: string) => void;
}

export function Ledger({ runId, items: all, fresh, working, onOpenShot }: LedgerProps) {
  const items = visibleItems(all);
  return (
    <section className="sheet ledger" aria-labelledby="ledger-h">
      <div className="ledger-head">
        <h2 id="ledger-h" className="sheet-title">What it did</h2>
        <span className="sheet-note">{items.length} entries</span>
      </div>
      {items.length === 0 ? (
        <p className="ledger-foot">Waiting for the first step.</p>
      ) : (
        <ol className="ledger-rows">
          {items.map((item) => {
            const row = toRow(item);
            return (
              <li key={item.seq} className={`row${fresh.has(item.seq) ? " row-new" : ""}`}>
                <span className="row-n">{row.n}</span>
                <span className={`row-kind ${row.tone}`}>{row.kind}</span>
                <span className="row-body">
                  <span className="row-text">{row.text}</span>
                  {row.sub}
                  {row.screenshot && (
                    <button
                      type="button"
                      className="thumb"
                      onClick={() => onOpenShot(api.artifactUrl(runId, row.screenshot!))}
                      aria-label={`Open screenshot for step ${row.n}`}
                    >
                      <img src={api.artifactUrl(runId, row.screenshot)} alt="" loading="lazy" onError={(e) => (e.currentTarget.parentElement!.hidden = true)} />
                    </button>
                  )}
                </span>
                <span className="row-time">{clock(item.ts)}</span>
              </li>
            );
          })}
        </ol>
      )}
      {working && <p className="ledger-foot">Choosing the next action…</p>}
    </section>
  );
}
