import { getApimToken } from "@/lib/server-auth";
import { getBackendBaseUrl } from "@/lib/agent-url";

type Dependencies = {
  getToken: () => Promise<string | null>;
  getBaseUrl: () => string;
  fetcher: typeof fetch;
};

type RouteContext = {
  params: Promise<{ name: string }>;
};

function authHeaders(token: string | null): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function createDocumentsDeleteHandler(deps: Dependencies) {
  return async (_request: Request, context: RouteContext) => {
    try {
      const { name } = await context.params;
      const token = await deps.getToken();
      const response = await deps.fetcher(
        `${deps.getBaseUrl()}/corpus/documents/${encodeURIComponent(name)}`,
        {
          method: "DELETE",
          headers: authHeaders(token),
        },
      );
      const body = await response.text();
      return new Response(body, { status: response.status, headers: { "Content-Type": "application/json" } });
    } catch {
      return Response.json({ error: "failed to delete document" }, { status: 503 });
    }
  };
}

export const DELETE = createDocumentsDeleteHandler({
  getToken: getApimToken,
  getBaseUrl: getBackendBaseUrl,
  fetcher: fetch,
});
