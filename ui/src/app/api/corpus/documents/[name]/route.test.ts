import { describe, expect, it, vi } from "vitest";
import { createDocumentsDeleteHandler } from "./route";

describe("corpus documents delete route", () => {
  it("proxies DELETE with encoded filename and bearer token", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/documents/guide%20.md");
      expect(init?.method).toBe("DELETE");
      expect(init?.headers).toEqual({ Authorization: "Bearer secret", Accept: "application/json" });
      return new Response(JSON.stringify({ name: "guide .md", deleted_chunks: 2 }), { status: 200 });
    });
    const response = await createDocumentsDeleteHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher,
    })(new Request("http://localhost/api/corpus/documents/guide%20.md", { method: "DELETE" }), {
      params: Promise.resolve({ name: "guide .md" }),
    });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ name: "guide .md", deleted_chunks: 2 });
  });

  it("returns 503 on network failure", async () => {
    const response = await createDocumentsDeleteHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher: vi.fn(async () => {
        throw new Error("network");
      }),
    })(new Request("http://localhost/api/corpus/documents/guide.md", { method: "DELETE" }), {
      params: Promise.resolve({ name: "guide.md" }),
    });
    expect(response.status).toBe(503);
  });
});
