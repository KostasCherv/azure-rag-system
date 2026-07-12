import { describe, expect, it, vi } from "vitest";
import { createSuggestionsGetHandler } from "./route";

describe("corpus suggestions route", () => {
  it.each([
    ["secret", {
      Accept: "application/json",
      Authorization: "Bearer secret",
      "X-RAG-User-ID": "user-a",
    }],
    [null, {
      Accept: "application/json",
      "X-RAG-User-ID": "user-a",
    }],
  ])("proxies GET with optional bearer token and trusted user id", async (token, expectedHeaders) => {
    const suggestions = ["How do I deploy?", "What is indexed?"];
    const fetcher = vi.fn(async (url, init) => {
      expect(url).toBe("https://example.test/corpus/suggestions");
      expect(init).toEqual({
        headers: expectedHeaders,
        cache: "no-store",
      });
      return new Response(JSON.stringify(suggestions), { status: 200 });
    });
    const getUserId = vi.fn(() => "user-a");
    const request = new Request("http://localhost/api/corpus/suggestions?user_id=attacker");

    const response = await createSuggestionsGetHandler({
      getToken: async () => token,
      getBaseUrl: () => "https://example.test",
      getUserId,
      fetcher,
    })(request);

    expect(getUserId).toHaveBeenCalledWith(request.headers);
    expect(fetcher).toHaveBeenCalledOnce();
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("application/json");
    expect(await response.json()).toEqual(suggestions);
  });

  it("returns 401 without user identity and does not fetch", async () => {
    const fetcher = vi.fn();
    const response = await createSuggestionsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => null,
      fetcher,
    })(new Request("http://localhost/api/corpus/suggestions?user_id=attacker"));

    expect(response.status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("preserves an upstream error status without exposing its body", async () => {
    const response = await createSuggestionsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => "user-a",
      fetcher: vi.fn(async () => new Response("database password: sensitive", { status: 503 })),
    })(new Request("http://localhost/api/corpus/suggestions"));

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "failed to load suggestions" });
  });

  it.each([204, 304])("preserves bodyless upstream status %i with an empty body", async (status) => {
    const response = await createSuggestionsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => "user-a",
      fetcher: vi.fn(async () => new Response(null, { status })),
    })(new Request("http://localhost/api/corpus/suggestions"));

    expect(response.status).toBe(status);
    expect(await response.text()).toBe("");
  });

  it("returns a generic 503 on network failure", async () => {
    const response = await createSuggestionsGetHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => "user-a",
      fetcher: vi.fn(async () => {
        throw new Error("network details");
      }),
    })(new Request("http://localhost/api/corpus/suggestions"));

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "failed to load suggestions" });
  });
});
