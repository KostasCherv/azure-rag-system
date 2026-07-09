const DEFAULT_AGENT_URL = "http://127.0.0.1:8000/agui";

export function getAgentUrl(): string {
  const value = (process.env.AGENT_URL || DEFAULT_AGENT_URL).replace(/\/+$/, "");
  const url = new URL(value);

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("AGENT_URL must use http or https");
  }

  return url.toString().replace(/\/$/, "");
}

export function getBackendBaseUrl(): string {
  const agent = new URL(getAgentUrl());
  if (!agent.pathname.endsWith("/agui")) {
    throw new Error("AGENT_URL must have terminal /agui to derive backend base URL");
  }
  agent.pathname = agent.pathname.slice(0, -5) || "/";
  return agent.toString().replace(/\/$/, "");
}

export function getReadyUrl(): string {
  const override = process.env.READY_URL;
  if (override) return validateHttpUrl(override, "READY_URL");
  const agent = new URL(getAgentUrl());
  if (!agent.pathname.endsWith("/agui")) throw new Error("AGENT_URL must have terminal /agui to derive readiness URL");
  agent.pathname = agent.pathname.slice(0, -5) + "/ready";
  return agent.toString().replace(/\/$/, "");
}

function validateHttpUrl(value: string, name: string): string {
  const url = new URL(value.replace(/\/+$/, ""));
  if (!(["http:", "https:"] as string[]).includes(url.protocol)) throw new Error(`${name} must use http or https`);
  return url.toString().replace(/\/$/, "");
}
