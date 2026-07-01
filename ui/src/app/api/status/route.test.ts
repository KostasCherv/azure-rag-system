import { describe, expect, it, vi } from "vitest";
import { createStatusHandler } from "./route";

describe("status route", () => {
  it("forwards only bearer authorization and Accept", async () => {
    const fetcher = vi.fn(async (_url, init) => { expect(init?.headers).toEqual({ Authorization: "Bearer secret", Accept: "application/json" }); return new Response(JSON.stringify({ status: "ready", search: { status: "available", indexer: { status: "success", ended_at: "2026-01-01T00:00:00Z" } }, openai: { status: "available" } }), { status: 200 }); });
    const response = await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://example.test/ready" })();
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "ready" });
  });
  it("normalizes backend, malformed, and network failures", async () => {
    for (const fetcher of [vi.fn(async () => new Response("bad", { status: 503 })), vi.fn(async () => new Response("{}")), vi.fn(async () => { throw new Error("secret detail"); })]) {
      const response = await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://example.test/ready" })();
      expect(response.status).toBe(503);
      expect(await response.json()).toEqual({ status: "unavailable", indexer: null });
    }
  });
});
