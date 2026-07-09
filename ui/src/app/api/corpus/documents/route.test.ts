import { describe, expect, it, vi } from "vitest";
import { createDocumentsGetHandler, createDocumentsPostHandler } from "./route";

describe("corpus documents route", () => {
  it("proxies GET with bearer token", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/documents");
      expect(init?.headers).toEqual({ Authorization: "Bearer secret", Accept: "application/json" });
      return new Response(JSON.stringify([{ name: "sample.pdf" }]), { status: 200 });
    });
    const response = await createDocumentsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher,
    })();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual([{ name: "sample.pdf" }]);
  });

  it("proxies POST multipart with bearer token", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/documents");
      expect(init?.method).toBe("POST");
      expect(init?.headers).toEqual({ Authorization: "Bearer secret" });
      expect(init?.body).toBeInstanceOf(FormData);
      return new Response(JSON.stringify({ name: "sample.pdf" }), { status: 200 });
    });
    const form = new FormData();
    form.append("file", new File(["pdf"], "sample.pdf", { type: "application/pdf" }));
    const response = await createDocumentsPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher,
    })(new Request("http://localhost/api/corpus/documents", { method: "POST", body: form }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ name: "sample.pdf" });
  });

  it("returns 400 when file is missing", async () => {
    const response = await createDocumentsPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher: vi.fn(),
    })(new Request("http://localhost/api/corpus/documents", { method: "POST", body: new FormData() }));
    expect(response.status).toBe(400);
  });

  it("returns 503 on network failure", async () => {
    const response = await createDocumentsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      fetcher: vi.fn(async () => { throw new Error("network"); }),
    })();
    expect(response.status).toBe(503);
  });
});
