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
});
