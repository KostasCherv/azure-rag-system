import { afterEach, describe, expect, it } from "vitest";

import { getAgentUrl, getReadyUrl } from "./agent-url";

describe("getAgentUrl", () => {
  const originalUrl = process.env.AGENT_URL;

  afterEach(() => {
    if (originalUrl === undefined) delete process.env.AGENT_URL;
    else process.env.AGENT_URL = originalUrl;
  });

  it("uses the local FastAPI AG-UI endpoint by default", () => {
    delete process.env.AGENT_URL;
    expect(getAgentUrl()).toBe("http://127.0.0.1:8000/agui");
  });

  it("removes a trailing slash from the configured endpoint", () => {
    process.env.AGENT_URL = "https://rag.example.test/agui/";
    expect(getAgentUrl()).toBe("https://rag.example.test/agui");
  });

  it("rejects non-http endpoints", () => {
    process.env.AGENT_URL = "file:///tmp/agui";
    expect(() => getAgentUrl()).toThrow("AGENT_URL must use http or https");
  });

  it("derives readiness by replacing only terminal /agui", () => {
    process.env.AGENT_URL = "https://example.test/gateway/agui";
    delete process.env.READY_URL;
    expect(getReadyUrl()).toBe("https://example.test/gateway/ready");
  });

  it("rejects deriving readiness from a non-agui path", () => {
    process.env.AGENT_URL = "https://example.test/gateway/agent";
    delete process.env.READY_URL;
    expect(() => getReadyUrl()).toThrow("terminal /agui");
  });

  it("uses an explicit readiness URL override", () => {
    process.env.READY_URL = "https://status.example.test/ready/";
    expect(getReadyUrl()).toBe("https://status.example.test/ready");
    delete process.env.READY_URL;
  });
});
