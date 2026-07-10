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
    for (const fetcher of [vi.fn(async () => new Response("{}")), vi.fn(async () => { throw new Error("secret detail"); })]) {
      const response = await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://example.test/ready" })();
      expect(response.status).toBe(503);
      expect(await response.json()).toEqual({
        status: "unavailable", search: null, openai: null, documentCount: null, lastSuccess: null, indexer: null,
      });
    }
  });
  it("parses readiness detail from a non-OK backend body", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      status: "unavailable",
      search: { status: "unavailable", document_count: 0, indexer: { status: "failed", last_success_ended_at: "2026-01-01T00:30:00Z" } },
      openai: { status: "available" },
    }), { status: 503 }));
    const response = await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://example.test/ready" })();
    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({
      status: "unavailable",
      search: "unavailable",
      openai: "available",
      documentCount: 0,
      lastSuccess: "2026-01-01T00:30:00Z",
    });
  });
  it("uses the selected URL and aborts a hanging request around six seconds", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    const fetcher = vi.fn((url, init) => new Promise<Response>((_resolve, reject) => { expect(url).toBe("https://override.test/ready"); signal = init?.signal ?? undefined; signal?.addEventListener("abort", () => reject(new Error("aborted"))); }));
    const result = createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://override.test/ready" })();
    await Promise.resolve();
    expect(signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(6_100);
    expect(signal?.aborted).toBe(true);
    expect((await result).status).toBe(503);
    vi.useRealTimers();
  });
  it("clears the timeout after a fast response", async () => {
    const clear = vi.spyOn(globalThis, "clearTimeout");
    await createStatusHandler({ getToken: async () => "secret", fetcher: async () => new Response("bad", { status: 503 }), getUrl: () => "https://example.test/ready" })();
    expect(clear).toHaveBeenCalledOnce();
  });
  it.each([
    [undefined, "https://example.test/base/agui", "https://example.test/base/ready"],
    ["https://override.test/custom-ready", "https://example.test/base/agui", "https://override.test/custom-ready"],
  ])("calls the derived or overridden readiness URL", async (readyUrl, agentUrl, expected) => {
    process.env.AGENT_URL = agentUrl;
    if (readyUrl) process.env.READY_URL = readyUrl; else delete process.env.READY_URL;
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => new Response(JSON.stringify({ status: "ready", search: { indexer: { status: "success" } } })));
    await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: getReadyUrl })();
    expect(fetcher.mock.calls[0][0]).toBe(expected);
    delete process.env.AGENT_URL;
    delete process.env.READY_URL;
  });

  it("rejects unauthenticated requests before touching the token or backend when user auth is required", async () => {
    process.env.REQUIRE_USER_AUTH = "true";
    const getToken = vi.fn(async () => "secret");
    const fetcher = vi.fn(async () => new Response("{}"));
    const response = await createStatusHandler({ getToken, fetcher, getUrl: () => "https://example.test/ready" })(
      new Request("https://ui.test/api/status"),
    );
    expect(response.status).toBe(401);
    expect(getToken).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
    delete process.env.REQUIRE_USER_AUTH;
  });

  it("serves authenticated requests when user auth is required", async () => {
    process.env.REQUIRE_USER_AUTH = "true";
    const principal = Buffer.from(JSON.stringify({
      claims: [
        { typ: "name", val: "Ada Lovelace" },
        { typ: "http://schemas.microsoft.com/identity/claims/objectidentifier", val: "oid-123" },
      ],
    })).toString("base64");
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ status: "ready", search: { status: "available", indexer: { status: "success", ended_at: "2026-01-01T00:00:00Z" } }, openai: { status: "available" } }), { status: 200 }));
    const response = await createStatusHandler({ getToken: async () => "secret", fetcher, getUrl: () => "https://example.test/ready" })(
      new Request("https://ui.test/api/status", { headers: { "x-ms-client-principal": principal } }),
    );
    expect(response.status).toBe(200);
    delete process.env.REQUIRE_USER_AUTH;
  });

  it("calls readiness without Authorization when APIM token is unavailable", async () => {
    const fetcher = vi.fn(async (_url, init) => {
      expect(init?.headers).toEqual({ Accept: "application/json" });
      return new Response(JSON.stringify({ status: "ready", search: { status: "available", indexer: { status: "success", ended_at: "2026-01-01T00:00:00Z" } }, openai: { status: "available" } }), { status: 200 });
    });
    const response = await createStatusHandler({ getToken: async () => null, fetcher, getUrl: () => "http://127.0.0.1:8000/ready" })();
    expect(response.status).toBe(200);
  });
});
