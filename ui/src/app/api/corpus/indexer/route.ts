import { getApimToken } from "@/lib/server-auth";
import { getBackendBaseUrl } from "@/lib/agent-url";

type Dependencies = {
  getToken: () => Promise<string | null>;
  getBaseUrl: () => string;
  fetcher: typeof fetch;
};

function authHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function createIndexerGetHandler(deps: Dependencies) {
  return async () => {
    try {
      const token = await deps.getToken();
      const response = await deps.fetcher(`${deps.getBaseUrl()}/corpus/indexer`, {
        headers: authHeaders(token),
        cache: "no-store",
      });
      const body = await response.text();
      return new Response(body, { status: response.status, headers: { "Content-Type": "application/json" } });
    } catch {
      return Response.json({ error: "failed to read indexer status" }, { status: 503 });
    }
  };
}

export function createIndexerPostHandler(deps: Dependencies) {
  return async () => {
    try {
      const token = await deps.getToken();
      const headers = authHeaders(token);
      const response = await deps.fetcher(`${deps.getBaseUrl()}/corpus/indexer/run`, {
        method: "POST",
        headers,
      });
      const body = await response.text();
      return new Response(body, { status: response.status, headers: { "Content-Type": "application/json" } });
    } catch {
      return Response.json({ error: "failed to start indexer" }, { status: 503 });
    }
  };
}

export const GET = createIndexerGetHandler({ getToken: getApimToken, getBaseUrl: getBackendBaseUrl, fetcher: fetch });
export const POST = createIndexerPostHandler({ getToken: getApimToken, getBaseUrl: getBackendBaseUrl, fetcher: fetch });
