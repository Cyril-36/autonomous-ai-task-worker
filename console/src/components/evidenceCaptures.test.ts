import { describe, expect, it } from "vitest";
import type { GoalContract } from "../api/types";
import type { TimelineItem } from "../state/runReducer";
import { evidenceCaptures } from "./evidenceCaptures";

const contract = {
  sources: [{ app: "portal", kind: "invoice", doc_id: "ls-1042", revision: "2",
              supplier_id: "larkspur-supplies", key: "LS-1042" }],
} as GoalContract;

function step(seq: number, tool: string, screenshot: string, url?: string): TimelineItem {
  return { seq, ts: `2026-10-04T04:0${seq}:00Z`, type: "step", run_id: "r1",
    data: { step: seq, tool, screenshot, url, args: {}, ok: true, summary: "ok",
            duration_ms: 2 } };
}

describe("evidence captures", () => {
  it("pairs the matching source document with the later saved record", () => {
    const timeline = [
      step(1, "record_facts", "step-1.png", "http://portal/invoices/other"),
      step(2, "record_facts", "step-2.png", "http://portal/invoices/ls-1042"),
      step(3, "submit_form", "step-3.png", "http://register/invoices"),
    ];
    const pair = evidenceCaptures("r1", contract, timeline, true);
    expect(pair?.source.src).toContain("step-2.png");
    expect(pair?.source.revision).toBe("2");
    expect(pair?.saved.src).toContain("step-3.png");
    expect(evidenceCaptures("r1", contract, timeline, false)).toBeUndefined();
  });
});
