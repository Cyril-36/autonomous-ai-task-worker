import { useState } from "react";
import { api } from "../api/client";
import { PHASES, type Phase } from "../api/types";
import { count, formatInr, readableReason, shortTime, statusMeta } from "../format";
import { isTerminal, type RunState } from "../state/useRun";
import { Evidence } from "./Evidence";
import { evidenceCaptures } from "./evidenceCaptures";
import { Ledger } from "./Ledger";
import { ApprovalCard, QuestionCard } from "./NeedsYou";
import { FactsPanel, GoalPanel, PlanPanel } from "./Panels";
import { WhyPanel } from "./WhyPanel";

const PHASE_LABEL: Record<Phase, string> = {
  setup: "Sign in",
  discover: "Read only",
  execute: "Make changes",
  verify: "Verify",
  done: "Done",
};

function Phases({ phase, visited }: { phase: Phase; visited: Phase[] }) {
  const at = PHASES.indexOf(phase);
  return (
    <ol className="phases" aria-label="Progress">
      {PHASES.map((p, i) => {
        const now = i === at && p !== "done";
        const done = !now && visited.includes(p) && (i < at || p === "done");
        const skipped = i < at && !visited.includes(p);
        return (
          <li key={p} className={done ? "done" : now ? "now" : skipped ? "skipped" : ""} aria-current={now ? "step" : undefined}>
            <span className="bar" />
            {PHASE_LABEL[p]}
            {skipped && <span className="sr-only"> (skipped)</span>}
            {skipped && <span className="skip-note" aria-hidden="true">skipped</span>}
          </li>
        );
      })}
    </ol>
  );
}

const REASON_TEXT: Record<string, string> = {
  cancelled_by_user: "You stopped this run. Anything confirmed before that is listed below; nothing else was saved.",
};

interface RunViewProps {
  run: RunState;
}

export function RunView({ run }: RunViewProps) {
  const [shot, setShot] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  const { view, error, connected } = run;

  if (error) {
    return (
      <section className="sheet sheet-pad stack">
        <h2 className="sheet-title">This run can't be shown</h2>
        <p className="error-text">{error.message}</p>
        <div className="actions">
          <button className="btn" type="button" onClick={run.refresh}>Try again</button>
        </div>
      </section>
    );
  }
  if (!view) return <section className="sheet sheet-pad muted">Loading the run…</section>;

  const verified = view.verification?.passed === true;
  const meta = statusMeta(view.status, view.status === "completed" ? verified : undefined);
  const terminal = isTerminal(view);
  const unverified = view.status === "completed" && !verified;
  const shownInEvidence = view.status === "completed" && verified;
  // The open card below carries the full question or approval text; the banner only points to it.
  const reason = shownInEvidence
    ? null
    : view.question
    ? "It needs your answer below to continue."
    : view.openApproval
    ? "Nothing is saved until you approve the change below."
    : unverified
    ? "The worker reported this run as completed, but no passing verification result arrived, so it is not shown as done."
    : view.statusReason
      ? (REASON_TEXT[view.statusReason] ?? readableReason(view.statusReason))
      : null;
  const working = !terminal && view.status === "running";
  const spent = view.cost?.run_spent_inr ?? view.summary.cost_inr;
  const limit = view.cost?.run_limit_inr ?? run.budget?.run_limit_inr ?? "4.00";

  async function stop() {
    if (!confirmStop) {
      setConfirmStop(true);
      return;
    }
    setConfirmStop(false);
    await api.cancel(view!.summary.run_id).catch(() => undefined);
  }

  return (
    <>
      <div className="col-main">
        <section className="sheet run-head" aria-labelledby="run-title">
          <div className="run-head-top">
            <div className="stack" style={{ gap: 6, flex: "1 1 360px", minWidth: 0 }}>
              <span className="run-byline">
                Started {shortTime(view.summary.created_at)} by {view.summary.principal.display_name}, acting with their permissions
              </span>
              <h1 id="run-title" className="run-title">{view.summary.request}</h1>
            </div>
            <div className="run-stats">
              <span className={`pill tone-${meta.tone}`} role="status">{meta.label}</span>
              <span>
                {count(view.stepCount, "step")}, about {formatInr(spent)} of {formatInr(limit)}
              </span>
              {!connected && !terminal && <span className="conn">Reconnecting to live updates…</span>}
            </div>
          </div>
          {reason && <p className={`reason tone-${meta.tone}`}>{reason}</p>}
          <Phases phase={view.phase} visited={view.visitedPhases} />
          {!terminal && (
            <div className="actions">
              <button type="button" className="btn btn-quiet" onClick={stop} style={confirmStop ? { color: "var(--stop-ink)" } : undefined}>
                {confirmStop ? "Confirm: stop this run" : "Stop run"}
              </button>
              {confirmStop && (
                <button type="button" className="btn btn-quiet" onClick={() => setConfirmStop(false)}>Keep going</button>
              )}
            </div>
          )}
        </section>

        {view.openApproval && <ApprovalCard runId={view.summary.run_id} approval={view.openApproval} />}
        {view.question && <QuestionCard runId={view.summary.run_id} question={view.question} />}
        {view.verification && terminal && <Evidence result={view.verification} status={view.status}
          captures={evidenceCaptures(view.summary.run_id, view.contract, view.timeline,
                                     view.verification.passed && view.status === "completed")} />}

        <Ledger runId={view.summary.run_id} items={view.timeline} fresh={run.freshSeqs} working={working} onOpenShot={setShot} />
      </div>

      <div className="col-right">
        <WhyPanel contract={view.contract} timeline={view.timeline}
          verification={view.verification} status={view.status} reason={view.statusReason} />
        <GoalPanel contract={view.contract} verification={terminal ? view.verification : null} />
        <PlanPanel steps={view.plan.steps} revision={view.plan.revision} />
        <FactsPanel facts={view.facts} order={view.factOrder} />
      </div>

      {shot && (
        <dialog open className="sheet" style={{ position: "fixed", inset: 24, margin: "auto", maxWidth: 1100, padding: 12, zIndex: 10 }} aria-label="Screenshot">
          <div className="actions" style={{ justifyContent: "flex-end", marginBottom: 8 }}>
            <button type="button" className="btn" onClick={() => setShot(null)} autoFocus>Close</button>
          </div>
          <img src={shot} alt="Screenshot of the page at this step" style={{ width: "100%", borderRadius: 6 }} />
        </dialog>
      )}
    </>
  );
}
