import { describe, expect, it, vi } from "vitest";
import { createDiscussionSuggestionsPostHandler } from "./route";

function request(body = '{"messages":[{"role":"user","content":"Question"}]}') {
  return new Request("http://localhost/api/discussion/suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

describe("discussion suggestions route", () => {
  it("proxies one POST with trusted identity and no retry", async () => {
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify([{ title: "Next", message: "What next?" }]), { status: 200 }),
    );
    const handler = createDiscussionSuggestionsPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => "user-a",
      fetcher,
    });
    const incoming = request();

    const response = await handler(incoming);

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith("https://example.test/discussion/suggestions", {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: "Bearer secret",
        "Content-Type": "application/json",
        "X-RAG-User-ID": "user-a",
      },
      body: '{"messages":[{"role":"user","content":"Question"}]}',
      cache: "no-store",
    });
    expect(await response.json()).toEqual([{ title: "Next", message: "What next?" }]);
  });

  it("returns an empty list after one failed upstream attempt", async () => {
    const fetcher = vi.fn(async () => new Response("failure", { status: 503 }));
    const response = await createDiscussionSuggestionsPostHandler({
      getToken: async () => null,
      getBaseUrl: () => "https://example.test",
      getUserId: () => "user-a",
      fetcher,
    })(request());

    expect(fetcher).toHaveBeenCalledOnce();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual([]);
  });

  it("does not call upstream without an identity", async () => {
    const fetcher = vi.fn();
    const response = await createDiscussionSuggestionsPostHandler({
      getToken: async () => "secret",
      getBaseUrl: () => "https://example.test",
      getUserId: () => null,
      fetcher,
    })(request());

    expect(response.status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
