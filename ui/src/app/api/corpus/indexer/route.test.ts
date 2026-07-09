import { describe, expect, it, vi } from "vitest";
import { createIndexerGetHandler, createIndexerPostHandler } from "./route";

describe("corpus indexer route", () => {
  it("proxies GET status with bearer token", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/indexer");
      expect(init?.headers).toEqual({ Authorization: "Bearer secret", Accept: "application/json" });
      return new Response(JSON.stringify({ status: "success" }), { status: 200 });
    });
    const response = await createIndexerGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher,
    })();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "success" });
  });

  it("proxies POST run with bearer token", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/indexer/run");
      expect(init?.method).toBe("POST");
      expect(init?.headers).toEqual({ Authorization: "Bearer secret", Accept: "application/json" });
      return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
    });
    const response = await createIndexerPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher,
    })();
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ status: "accepted" });
  });

  it("returns 503 on network failure", async () => {
    const response = await createIndexerPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher: vi.fn(async () => { throw new Error("network"); }),
    })();
    expect(response.status).toBe(503);
  });
});
