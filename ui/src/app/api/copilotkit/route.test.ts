import { describe, expect, it, vi } from "vitest";
import { createPostHandler } from "./route";

describe("copilot route", () => {
  it("constructs the per-request agent with a bearer header", async () => {
    const makeAgent = vi.fn(() => ({} as never));
    const handle = vi.fn(async () => new Response("ok"));
    const post = createPostHandler({ getToken: async () => "secret", makeAgent, makeEndpoint: vi.fn(() => ({ handleRequest: handle })) as never, getUrl: () => "https://example.test/agui" });
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(makeAgent).toHaveBeenCalledWith("https://example.test/agui", { Authorization: "Bearer secret" });
    expect(handle).toHaveBeenCalledOnce();
  });

  it("requests and applies a fresh token on every POST", async () => {
    const getToken = vi.fn().mockResolvedValueOnce("first").mockResolvedValueOnce("second");
    const makeAgent = vi.fn(() => ({} as never));
    const post = createPostHandler({ getToken, makeAgent, makeEndpoint: vi.fn(() => ({ handleRequest: async () => new Response("ok") })) as never, getUrl: () => "https://example.test/agui" });
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(getToken).toHaveBeenCalledTimes(2);
    expect(makeAgent).toHaveBeenNthCalledWith(1, "https://example.test/agui", { Authorization: "Bearer first" });
    expect(makeAgent).toHaveBeenNthCalledWith(2, "https://example.test/agui", { Authorization: "Bearer second" });
  });

  it("omits Authorization header when APIM token is unavailable", async () => {
    const makeAgent = vi.fn(() => ({} as never));
    const post = createPostHandler({ getToken: async () => null, makeAgent, makeEndpoint: vi.fn(() => ({ handleRequest: async () => new Response("ok") })) as never, getUrl: () => "https://example.test/agui" });
    await post(new Request("http://localhost/api/copilotkit", { method: "POST" }) as never);
    expect(makeAgent).toHaveBeenCalledWith("https://example.test/agui", {});
  });
});
