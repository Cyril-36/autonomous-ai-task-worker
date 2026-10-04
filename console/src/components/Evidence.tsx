import type { RunStatus, VerificationResult } from "../api/types";
import { describeUrl } from "../format";

interface EvidenceProps {
  result: VerificationResult;
  status: RunStatus;
}

/** Rendered only from the verifier's result; nothing here comes from model text. */
export function Evidence({ result, status }: EvidenceProps) {
  const passed = result.checks.filter((c) => c.passed).length;
  const ok = result.passed && status === "completed";
  const heading = ok
    ? `Verified: ${passed} of ${result.checks.length} checks passed`
    : status === "partial"
      ? `Partly done: ${passed} of ${result.checks.length} checks passed`
      : `Not verified: ${result.checks.length - passed} of ${result.checks.length} checks failed`;

  return (
    <section className={`evidence${ok ? "" : " failed"}`} aria-labelledby="evidence-h">
      <div className="sheet-head">
        <h2 id="evidence-h">{heading}</h2>
        <span className="sheet-note">read back from the systems, not taken from the worker</span>
      </div>
      <p className="evidence-summary">{result.summary}</p>
      <div style={{ overflowX: "auto", border: "1px solid var(--rule-soft)", borderRadius: 8 }}>
        <table className="checks">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Expected</th>
              <th scope="col">Found</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {result.checks.map((c) => (
              <tr key={c.obligation_id}>
                <td>
                  {c.description}
                  {c.detail && <div className="muted" style={{ fontSize: 12 }}>{c.detail}</div>}
                </td>
                <td className="mono">{c.expected ?? ""}</td>
                <td className="mono">{c.actual ?? ""}</td>
                <td>
                  <span className={`pill ${c.passed ? "tone-ok" : "tone-stop"}`}>{c.passed ? "Passed" : "Failed"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.remaining.length > 0 && (
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Not done yet ({result.remaining.length})</h3>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {result.remaining.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {result.evidence.length > 0 && (
        <div className="links">
          {result.evidence.map((e) => {
            const where = e.url ? describeUrl(e.url).app : "";
            return (
              <span key={e.label}>
                <span className="muted">{e.label}: </span>
                {e.download_url ? (
                  <a href={e.download_url} download>Download CSV</a>
                ) : e.url ? (
                  <a href={e.url} target="_blank" rel="noreferrer">
                    {e.value}
                    {where ? ` in ${where}` : ""}
                  </a>
                ) : (
                  e.value
                )}
              </span>
            );
          })}
        </div>
      )}
    </section>
  );
}
