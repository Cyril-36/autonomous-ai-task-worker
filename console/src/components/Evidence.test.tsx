import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Evidence } from "./Evidence";
import type { VerificationResult } from "../api/types";

describe("verified export evidence", () => {
  it("shows an authenticated CSV download link", () => {
    const result: VerificationResult = {
      run_id: "run-1",
      contract_id: "contract-1",
      passed: true,
      status: "completed",
      summary: "Exact CSV verified",
      checks: [],
      remaining: [],
      evidence: [{
        label: "Export",
        value: "exports/run-1/abc123-due.csv",
        url: null,
        screenshot_path: null,
        download_url: "/api/runs/run-1/exports/abc123-due.csv",
      }],
    };
    const html = renderToStaticMarkup(<Evidence result={result} status="completed" />);
    expect(html).toContain('href="/api/runs/run-1/exports/abc123-due.csv"');
    expect(html).toContain("Download CSV");
  });

  it("labels source and saved captures without replacing read-back checks", () => {
    const result: VerificationResult = {
      run_id: "run-1", contract_id: "c1", passed: true, status: "completed",
      summary: "Verified by read-back", checks: [{
        obligation_id: "saved", description: "Saved record matches source", passed: true,
        expected: "source values", actual: "saved values", detail: null,
      }], remaining: [], evidence: [],
    };
    const html = renderToStaticMarkup(<Evidence result={result} status="completed" captures={{
      source: { src: "/api/runs/run-1/artifacts/step-3.png", label: "Source invoice",
                revision: "2", capturedAt: "09:41" },
      saved: { src: "/api/runs/run-1/artifacts/step-8.png", label: "Saved record",
               capturedAt: "09:43" },
    }} />);
    expect(html).toContain("Source invoice");
    expect(html).toContain("revision 2");
    expect(html).toContain("09:41");
    expect(html).toContain("Saved record");
    expect(html).toContain("09:43");
    expect(html).toContain("Saved record matches source");
  });
});
