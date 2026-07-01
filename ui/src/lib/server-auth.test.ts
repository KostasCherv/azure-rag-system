import { afterEach, describe, expect, it, vi } from "vitest";
import { createTokenProvider, getApimScope } from "./server-auth";

describe("server auth", () => {
  afterEach(() => delete process.env.APIM_SCOPE);
  it("requires a /.default APIM scope", () => {
    process.env.APIM_SCOPE = "api://apim";
    expect(() => getApimScope()).toThrow("/.default");
  });
  it("requests the configured scope and returns only the token", async () => {
    process.env.APIM_SCOPE = "api://apim/.default";
    const getToken = vi.fn(async () => ({ token: "secret" }));
    expect(await createTokenProvider({ getToken })()).toBe("secret");
    expect(getToken).toHaveBeenCalledWith("api://apim/.default");
  });
});
