import type { Fact, GoalContract, PlanStep, VerificationResult } from "../api/types";
import { GOAL_LABEL, describeUrl, formatInr } from "../format";

interface GoalPanelProps {
  contract: GoalContract | null;
  verification: VerificationResult | null;
}

export function GoalPanel({ contract, verification }: GoalPanelProps) {
  const results = new Map(verification?.checks.map((c) => [c.obligation_id, c]) ?? []);
  return (
    <section className="sheet sheet-pad stack" aria-labelledby="goal-h">
      <div className="sheet-head">
        <h2 id="goal-h" className="sheet-title">Goal</h2>
        <span className="sheet-note">{contract ? "locked" : "not committed yet"}</span>
      </div>
      {!contract ? (
        <p className="muted" style={{ fontSize: 13 }}>
          It reads first. Once it knows enough, it commits a goal, and the code works out the checks the result must pass. Nothing can be
          changed before that.
        </p>
      ) : (
        <>
          <dl className="kv">
            <dt>Task</dt>
            <dd>{GOAL_LABEL[contract.goal_type]}</dd>
            {contract.supplier_name && (
              <>
                <dt>Supplier</dt>
                <dd>{contract.supplier_name}</dd>
              </>
            )}
            {contract.sources.length > 0 && (
              <>
                <dt>Source</dt>
                <dd>
                  {contract.sources.map((s) => (
                    <div key={s.doc_id}>
                      <span className="mono">{s.key}</span> <span className="muted">revision {s.revision}</span>
                    </div>
                  ))}
                </dd>
              </>
            )}
            {contract.filter && (
              <>
                <dt>Filter</dt>
                <dd className="mono">
                  {Object.entries(contract.filter)
                    .map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`)
                    .join(", ")}
                </dd>
              </>
            )}
            {contract.batch_remaining.length > 0 && (
              <>
                <dt>Left over</dt>
                <dd>{contract.batch_remaining.length} beyond the cap</dd>
              </>
            )}
          </dl>
          <ul className="oblist" aria-label="Checks the result must pass">
            {contract.obligations.map((o) => {
              const r = results.get(o.obligation_id);
              const cls = r ? (r.passed ? "pass" : "fail") : "";
              return (
                <li key={o.obligation_id} className="ob">
                  <span className={`box ${cls}`} aria-hidden="true" />
                  <span>
                    {o.description}
                    <div className={`ob-state ${cls}`}>{r ? (r.passed ? "Passed on read-back" : "Failed on read-back") : "Checked after the work"}</div>
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

export function PlanPanel({ steps, revision }: { steps: PlanStep[]; revision: number }) {
  return (
    <section className="sheet sheet-pad stack" aria-labelledby="plan-h">
      <div className="sheet-head">
        <h2 id="plan-h" className="sheet-title">Its plan</h2>
        {revision > 1 && <span className="sheet-note">revised {revision - 1}×</span>}
      </div>
      {steps.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>No plan yet.</p>
      ) : (
        <ol className="planlist">
          {steps.map((s, i) => (
            <li key={`${i}-${s.text}`} className={`plan-item ${s.status}`}>
              <span className="plan-mark">{s.status === "done" ? "✓" : s.status === "blocked" ? "×" : `${i + 1}.`}</span>
              <span>
                {s.text}
                {s.status === "doing" && <span className="sr-only"> (in progress)</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function shown(f: Fact): string {
  return f.type === "amount" ? formatInr(f.normalized) : f.normalized;
}

export function FactsPanel({ facts, order }: { facts: Record<string, Fact>; order: string[] }) {
  return (
    <section className="sheet sheet-pad stack" aria-labelledby="facts-h">
      <div className="sheet-head">
        <h2 id="facts-h" className="sheet-title">What it found</h2>
        <span className="sheet-note">copied from the page by code</span>
      </div>
      {order.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>Nothing recorded yet.</p>
      ) : (
        <dl className="facts">
          {order.map((key) => {
            const f = facts[key];
            const where = describeUrl(f.url);
            return (
              <div key={key} className="fact">
                <dt>{f.field_locator}</dt>
                <dd className="fact-val">{shown(f)}</dd>
                <dd className="fact-from">
                  {f.value !== shown(f) && <>shown as “{f.value}”, </>}
                  {f.url.startsWith("goal:") ? (
                    "fixed by the locked goal"
                  ) : f.url.startsWith("memory:") ? (
                    "remembered for next time"
                  ) : (
                    <>
                      <a href={f.url} target="_blank" rel="noreferrer">
                        {where.app}
                        {f.doc_id ? ` ${f.doc_id}` : ""}
                      </a>
                      {f.revision && <> revision {f.revision}</>}
                    </>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}
