import { describe, expect, it, vi } from "vitest";
import { createPostHandler } from "./route";

const principalHeader = Buffer.from(
  JSON.stringify({
    auth_typ: "aad",
    claims: [
      { typ: "name", val: "Ada Lovelace" },
      {
        typ: "http://schemas.microsoft.com/identity/claims/objectidentifier",
        val: "11111111-1111-1111-1111-111111111111",
      },
    ],
  }),
  "utf8",
).toString("base64");

describe("copilot route", () => {
  it("constructs the per-request agent with a bearer header", async () => {
    const makeAgent = vi.fn(() => ({} as never));
    const handle = vi.fn(async () => new Response("ok"));
    const post = createPostHandler({ getToken: async () => "secret", makeAgent, makeEndpoint: vi.fn(() => ({ handleRequest: handle })) as never, getUrl: () => "https://example.test/agui" });
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(makeAgent).toHaveBeenCalledWith("https://example.test/agui", { Authorization: "Bearer secret", "X-RAG-User-ID": "local-development-user" });
    expect(handle).toHaveBeenCalledOnce();
  });

  it("requests and applies a fresh token on every POST", async () => {
    const getToken = vi.fn().mockResolvedValueOnce("first").mockResolvedValueOnce("second");
    const makeAgent = vi.fn(() => ({} as never));
    const post = createPostHandler({ getToken, makeAgent, makeEndpoint: vi.fn(() => ({ handleRequest: async () => new Response("ok") })) as never, getUrl: () => "https://example.test/agui" });
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(getToken).toHaveBeenCalledTimes(2);
    expect(makeAgent).toHaveBeenNthCalledWith(1, "https://example.test/agui", { Authorization: "Bearer first", "X-RAG-User-ID": "local-development-user" });
    expect(makeAgent).toHaveBeenNthCalledWith(2, "https://example.test/agui", { Authorization: "Bearer second", "X-RAG-User-ID": "local-development-user" });
  });

  it("omits Authorization header when APIM token is unavailable", async () => {
    const makeAgent = vi.fn(() => ({} as never));
    const post = createPostHandler({ getToken: async () => null, makeAgent, makeEndpoint: vi.fn(() => ({ handleRequest: async () => new Response("ok") })) as never, getUrl: () => "https://example.test/agui" });
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(makeAgent).toHaveBeenCalledWith("https://example.test/agui", { "X-RAG-User-ID": "local-development-user" });
  });

  it("returns 401 when user auth is required and principal is missing", async () => {
    process.env.REQUIRE_USER_AUTH = "true";
    const post = createPostHandler({
      getToken: async () => "secret",
      makeAgent: vi.fn(() => ({} as never)),
      makeEndpoint: vi.fn(() => ({ handleRequest: async () => new Response("ok") })) as never,
      getUrl: () => "https://example.test/agui",
    });
    const response = await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(response.status).toBe(401);
    delete process.env.REQUIRE_USER_AUTH;
  });

  it("forwards the principal oid as the user id when user auth is required", async () => {
    process.env.REQUIRE_USER_AUTH = "true";
    const handle = vi.fn(async () => new Response("ok"));
    const makeAgent = vi.fn(() => ({} as never));
    const post = createPostHandler({
      getToken: async () => "secret",
      makeAgent,
      makeEndpoint: vi.fn(() => ({ handleRequest: handle })) as never,
      getUrl: () => "https://example.test/agui",
    });
    const response = await post(
      new Request("http://localhost/api/copilotkit", {
        method: "POST",
        headers: { "x-ms-client-principal": principalHeader },
      }) as never,
    );
    expect(response.status).toBe(200);
    expect(handle).toHaveBeenCalledOnce();
    expect(makeAgent).toHaveBeenCalledWith("https://example.test/agui", {
      Authorization: "Bearer secret",
      "X-RAG-User-ID": "11111111-1111-1111-1111-111111111111",
    });
    delete process.env.REQUIRE_USER_AUTH;
  });
});
