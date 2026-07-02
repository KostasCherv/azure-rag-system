import { afterEach, describe, expect, it, vi } from "vitest";
import { createTokenProvider, getApimScope } from "./server-auth";

describe("server auth", () => {
  afterEach(() => {
    delete process.env.APIM_SCOPE;
    delete process.env.AGENT_URL;
    delete process.env.FORCE_APIM_AUTH;
  });
  it("requires a /.default APIM scope", () => {
    process.env.AGENT_URL = "https://example.test/agui";
    process.env.APIM_SCOPE = "api://apim";
    expect(() => getApimScope()).toThrow("/.default");
  });
  it("allows APIM scope to be unset in local direct mode", () => {
    delete process.env.APIM_SCOPE;
    expect(getApimScope()).toBeNull();
  });
  it("requests the configured scope and returns only the token", async () => {
    process.env.AGENT_URL = "https://example.test/agui";
    process.env.APIM_SCOPE = "api://apim/.default";
    const getToken = vi.fn(async () => ({ token: "secret" }));
    expect(await createTokenProvider({ getToken })()).toBe("secret");
    expect(getToken).toHaveBeenCalledWith("api://apim/.default");
  });
  it("does not request a credential token when APIM scope is unset", async () => {
    delete process.env.APIM_SCOPE;
    const getToken = vi.fn(async () => ({ token: "secret" }));
    expect(await createTokenProvider({ getToken })()).toBeNull();
    expect(getToken).not.toHaveBeenCalled();
  });
  it("bypasses APIM auth for localhost agent URLs", async () => {
    process.env.APIM_SCOPE = "api://apim/.default";
    process.env.AGENT_URL = "http://127.0.0.1:8000/agui";
    const getToken = vi.fn(async () => ({ token: "secret" }));
    expect(await createTokenProvider({ getToken })()).toBeNull();
    expect(getToken).not.toHaveBeenCalled();
  });
  it("allows forcing APIM auth for localhost agent URLs", async () => {
    process.env.APIM_SCOPE = "api://apim/.default";
    process.env.AGENT_URL = "http://127.0.0.1:8000/agui";
    process.env.FORCE_APIM_AUTH = "true";
    const getToken = vi.fn(async () => ({ token: "secret" }));
    expect(await createTokenProvider({ getToken })()).toBe("secret");
    expect(getToken).toHaveBeenCalledWith("api://apim/.default");
  });
});
