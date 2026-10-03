import { describe, expect, it } from "vitest";
import { count, describeUrl, fieldName, fieldValue, formatInr, readableReason, sentence, statusMeta } from "./format";

describe("formatInr", () => {
  it.each([
    ["118400.00", "₹1,18,400.00"],
    ["48250", "₹48,250.00"],
    ["999.5", "₹999.50"],
    ["12345678.90", "₹1,23,45,678.90"],
  ])("%s -> %s", (input, out) => expect(formatInr(input)).toBe(out));

  it("leaves non-numbers alone", () => expect(formatInr("n/a")).toBe("n/a"));
});

describe("describeUrl", () => {
  it("names the sandbox apps", () => {
    expect(describeUrl("http://127.0.0.1:8102/invoices/new")).toEqual({ app: "Register", path: "/invoices/new" });
  });
});

describe("statusMeta", () => {
  it("never calls a run done unless it was verified", () => {
    expect(statusMeta("completed").label).toBe("Completed");
    expect(statusMeta("partial").tone).toBe("wait");
  });

  it("flags a completed run that has no passing verification", () => {
    expect(statusMeta("completed", false)).toEqual({ label: "Completed, not verified", tone: "stop" });
    expect(statusMeta("completed", true).label).toBe("Done and verified");
  });
});

describe("readableReason", () => {
  it("turns codes into words and leaves sentences alone", () => {
    expect(readableReason("replay_demo_only")).toBe("Replay demo only.");
    expect(readableReason("Nothing was saved.")).toBe("Nothing was saved.");
  });
});

describe("field display", () => {
  it("names fields and formats money", () => {
    expect(fieldName("supplier_id")).toBe("Supplier");
    expect(fieldName("source_doc_id")).toBe("Source document");
    expect(fieldName("due_date")).toBe("Due date");
    expect(fieldValue("amount", "125000.00")).toBe("₹1,25,000.00");
    expect(fieldValue("invoice_number", "BF-2292")).toBe("BF-2292");
    expect(sentence("Needs approval")).toBe("Needs approval.");
  });
});

describe("count", () => {
  it("pluralizes", () => {
    expect(count(1, "step")).toBe("1 step");
    expect(count(12, "step")).toBe("12 steps");
  });
});
