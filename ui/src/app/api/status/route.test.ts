import { describe, expect, it, vi } from "vitest";
import { createStatusHandler } from "./route";
import { getReadyUrl } from "@/lib/agent-url";

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
  it("uses the selected URL and supplies a signal that times out around six seconds", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const fetcher = vi.fn(async (url, init) => { expect(url).toBe("https://override.test/ready"); signal = init?.signal ?? undefined; return new Response(JSON.stringify({ status: "ready", search: { indexer: { status: "success" } } })); });
    await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://override.test/ready" })();
    expect(signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(6_100);
    expect(signal?.aborted).toBe(true);
    vi.useRealTimers();
  });
  it.each([
    [undefined, "https://example.test/base/agui", "https://example.test/base/ready"],
    ["https://override.test/custom-ready", "https://example.test/base/agui", "https://override.test/custom-ready"],
  ])("calls the derived or overridden readiness URL", async (readyUrl, agentUrl, expected) => {
    process.env.AGENT_URL = agentUrl;
    if (readyUrl) process.env.READY_URL = readyUrl; else delete process.env.READY_URL;
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ status: "ready", search: { indexer: { status: "success" } } })));
    await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: getReadyUrl })();
    expect(fetcher.mock.calls[0][0]).toBe(expected);
    delete process.env.AGENT_URL;
    delete process.env.READY_URL;
  });
});
