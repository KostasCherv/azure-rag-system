import { describe, expect, it, vi } from "vitest";
import { createDocumentsGetHandler, createDocumentsPostHandler } from "./route";

const getUserId = () => "user-a";

describe("corpus documents route", () => {
  it("proxies GET with bearer token and user id", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/documents");
      expect(init?.headers).toEqual({
        Authorization: "Bearer secret",
        Accept: "application/json",
        "X-RAG-User-ID": "user-a",
      });
      return new Response(JSON.stringify([{ name: "sample.pdf" }]), { status: 200 });
    });
    const response = await createDocumentsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId,
      fetcher,
    })(new Request("http://localhost/api/corpus/documents"));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual([{ name: "sample.pdf" }]);
  });

  it("proxies POST multipart with bearer token and user id", async () => {
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/documents");
      expect(init?.method).toBe("POST");
      expect(init?.headers).toEqual({ Authorization: "Bearer secret", "X-RAG-User-ID": "user-a" });
      expect(init?.body).toBeInstanceOf(FormData);
      return new Response(JSON.stringify({ name: "sample.pdf" }), { status: 200 });
    });
    const form = new FormData();
    form.append("file", new File(["pdf"], "sample.pdf", { type: "application/pdf" }));
    const response = await createDocumentsPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId,
      fetcher,
    })(new Request("http://localhost/api/corpus/documents", { method: "POST", body: form }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ name: "sample.pdf" });
  });

  it("returns 401 when no user identity is available", async () => {
    const fetcher = vi.fn();
    const deps = {
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => null,
      fetcher,
    };
    const get = await createDocumentsGetHandler(deps)(new Request("http://localhost/api/corpus/documents"));
    const post = await createDocumentsPostHandler(deps)(
      new Request("http://localhost/api/corpus/documents", { method: "POST", body: new FormData() }),
    );
    expect(get.status).toBe(401);
    expect(post.status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("returns 400 when file is missing", async () => {
    const response = await createDocumentsPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId,
      fetcher: vi.fn(),
    })(new Request("http://localhost/api/corpus/documents", { method: "POST", body: new FormData() }));
    expect(response.status).toBe(400);
  });

  it("returns 503 on network failure", async () => {
    const response = await createDocumentsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId,
      fetcher: vi.fn(async () => { throw new Error("network"); }),
    })(new Request("http://localhost/api/corpus/documents"));
    expect(response.status).toBe(503);
  });
});
