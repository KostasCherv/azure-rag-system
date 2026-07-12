import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/agent-url", () => ({ getBackendBaseUrl: () => "https://example.test" }));
vi.mock("@/lib/server-auth", () => ({ getApimToken: async () => "secret" }));
vi.mock("@/lib/user-auth", () => ({ getUserId: () => "user-a" }));

import { NextRequest } from "next/server";
import { DELETE } from "./route";

afterEach(() => vi.unstubAllGlobals());

describe("sessions proxy DELETE", () => {
  it("passes through a 204 with no body instead of failing with 503", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    const response = await DELETE(
      new NextRequest("http://localhost/api/sessions/abc", { method: "DELETE" }),
      { params: Promise.resolve({ path: ["abc"] }) },
    );
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });
});
