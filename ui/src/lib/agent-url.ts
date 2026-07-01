const DEFAULT_AGENT_URL = "http://127.0.0.1:8000/agui";

export function getAgentUrl(): string {
  const value = (process.env.AGENT_URL || DEFAULT_AGENT_URL).replace(/\/+$/, "");
  const url = new URL(value);

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("AGENT_URL must use http or https");
  }

  return url.toString().replace(/\/$/, "");
}
