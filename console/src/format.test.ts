import { describe, expect, it } from "vitest";
import { describeUrl, formatInr, statusMeta } from "./format";

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
    expect(statusMeta("completed").label).toBe("Done and verified");
    expect(statusMeta("partial").tone).toBe("wait");
  });
});
