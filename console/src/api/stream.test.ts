import { describe, expect, it } from "vitest";
import { ApiError, parseError } from "./client";
import { SeqGate } from "./stream";

describe("SeqGate", () => {
  it("passes new events once and drops replays", () => {
    const gate = new SeqGate(2);
    expect(gate.accept({ seq: 1 })).toBe(false);
    expect(gate.accept({ seq: 2 })).toBe(false);
    expect(gate.accept({ seq: 3 })).toBe(true);
    expect(gate.accept({ seq: 3 })).toBe(false);
    expect(gate.lastSeq).toBe(3);
  });
});

describe("parseError", () => {
  it("maps the contract error body", async () => {
    const res = new Response(JSON.stringify({ error: { code: "forbidden", message: "Not your run." } }), { status: 403 });
    const err = await parseError(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe("forbidden");
    expect(err.message).toBe("Not your run.");
  });

  it("explains a body that isn't the contract shape", async () => {
    const err = await parseError(new Response("oops", { status: 500 }));
    expect(err.code).toBe("unexpected_response");
    expect(err.message).toContain("500");
  });
});
