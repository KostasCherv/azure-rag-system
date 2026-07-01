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
});
