import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { GoalContract, VerificationResult } from "../api/types";
import type { TimelineItem } from "../state/runReducer";
import { WhyPanel } from "./WhyPanel";

describe("decision explanation", () => {
  it("uses the recorded action, checks and gate reason", () => {
    const contract = {
      goal_type: "register_invoice",
      obligations: [{ obligation_id: "source_match", kind: "source_match",
        description: "Saved fields match the source", params: {} }],
    } as GoalContract;
    const verification = { checks: [{ obligation_id: "source_match",
      description: "Saved fields match the source", passed: false,
      expected: "source", actual: "different", detail: null }],
    } as VerificationResult;
    const timeline = [
      { type: "step", run_id: "r1", seq: 1, ts: "2026-10-04T04:00:00Z",
        data: { tool: "commit_goal", step: 1, args: { contract: {
          requested_action: "Register the newest invoice", goal_type: "register_invoice" } },
          ok: true, summary: "Goal locked", duration_ms: 1 } },
      { type: "gate", run_id: "r1", seq: 2, ts: "2026-10-04T04:01:00Z",
        data: { step: 2, allowed: false, code: "needs_approval",
          reason: "Amount exceeds the current approval threshold" } },
    ] as TimelineItem[];
    const html = renderToStaticMarkup(<WhyPanel contract={contract} timeline={timeline}
      verification={verification} status="awaiting_approval"
      reason="Waiting for approval" />);
    expect(html).toContain("Why it did that");
    expect(html).toContain("Register the newest invoice");
    expect(html).toContain("Saved fields match the source");
    expect(html).toContain("Amount exceeds the current approval threshold");
    expect(html).toContain("Waiting for approval");
  });

  it("lists a repeated reason once and does not repeat it as the outcome", () => {
    const gate = (seq: number) => ({ type: "gate", run_id: "r1", seq, ts: "2026-10-04T04:01:00Z",
      data: { step: seq, allowed: false, code: "needs_approval", reason: "Approval needed because it changes an existing record" } });
    const html = renderToStaticMarkup(<WhyPanel contract={null} timeline={[gate(1), gate(2)] as TimelineItem[]}
      verification={null} status="awaiting_approval" reason="Approval needed because it changes an existing record" />);
    expect(html.split("it changes an existing record").length - 1).toBe(1);
  });
});
