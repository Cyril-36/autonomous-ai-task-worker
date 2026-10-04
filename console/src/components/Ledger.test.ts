import { describe, expect, it } from "vitest";
import type { TimelineItem } from "../state/runReducer";
import { visibleItems } from "./Ledger";

const at = "2026-10-04T04:00:00Z";

describe("timeline rows", () => {
  it("shows a refused goal that became a question only as the question", () => {
    const items = [
      { type: "contract", run_id: "r", seq: 1, ts: at, data: { action: "rejected", reason: "The request does not clearly ask to register the invoice" } },
      { type: "question", run_id: "r", seq: 2, ts: at, data: { text: "The request does not clearly ask to register the invoice. Should I register the invoice?" } },
    ] as TimelineItem[];
    expect(visibleItems(items).map((item) => item.type)).toEqual(["question"]);
  });

  it("keeps a refused goal that the model has to fix itself", () => {
    const items = [
      { type: "contract", run_id: "r", seq: 1, ts: at, data: { action: "rejected", reason: "Source LS-9 is not in the portal" } },
    ] as TimelineItem[];
    expect(visibleItems(items)).toHaveLength(1);
  });
});
