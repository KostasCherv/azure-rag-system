import "server-only";
import { DefaultAzureCredential } from "@azure/identity";

type Credential = { getToken(scope: string): Promise<{ token: string } | null> };

export function getApimScope(): string | null {
  if (shouldBypassApimAuthForLocalAgent()) return null;
  const scope = process.env.APIM_SCOPE?.trim();
  if (!scope) return null;
  if (!scope.endsWith("/.default")) throw new Error("APIM_SCOPE must end with /.default");
  return scope;
}

export function createTokenProvider(credential: Credential = new DefaultAzureCredential()) {
  return async (): Promise<string | null> => {
    const scope = getApimScope();
    if (!scope) return null;
    const result = await credential.getToken(scope);
    if (!result?.token) throw new Error("APIM access token unavailable");
    return result.token;
  };
}

export const getApimToken = createTokenProvider();

function shouldBypassApimAuthForLocalAgent(): boolean {
  if (process.env.FORCE_APIM_AUTH === "true") return false;
  const rawAgentUrl = process.env.AGENT_URL || "http://127.0.0.1:8000/agui";
  try {
    const url = new URL(rawAgentUrl);
    return ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
  } catch {
    return false;
  }
}
