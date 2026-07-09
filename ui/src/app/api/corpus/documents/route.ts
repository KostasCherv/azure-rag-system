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

export function createDocumentsGetHandler(deps: Dependencies) {
  return async () => {
    try {
      const token = await deps.getToken();
      const response = await deps.fetcher(`${deps.getBaseUrl()}/corpus/documents`, {
        headers: authHeaders(token),
        cache: "no-store",
      });
      const body = await response.text();
      return new Response(body, { status: response.status, headers: { "Content-Type": "application/json" } });
    } catch {
      return Response.json({ error: "failed to list documents" }, { status: 503 });
    }
  };
}

export function createDocumentsPostHandler(deps: Dependencies) {
  return async (request: Request) => {
    try {
      const token = await deps.getToken();
      const form = await request.formData();
      const file = form.get("file");
      if (!(file instanceof File)) {
        return Response.json({ error: "file is required" }, { status: 400 });
      }
      const outbound = new FormData();
      outbound.append("file", file, file.name);
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await deps.fetcher(`${deps.getBaseUrl()}/corpus/documents`, {
        method: "POST",
        headers,
        body: outbound,
      });
      const body = await response.text();
      return new Response(body, { status: response.status, headers: { "Content-Type": "application/json" } });
    } catch {
      return Response.json({ error: "failed to upload document" }, { status: 503 });
    }
  };
}

export const GET = createDocumentsGetHandler({ getToken: getApimToken, getBaseUrl: getBackendBaseUrl, fetcher: fetch });
export const POST = createDocumentsPostHandler({ getToken: getApimToken, getBaseUrl: getBackendBaseUrl, fetcher: fetch });
