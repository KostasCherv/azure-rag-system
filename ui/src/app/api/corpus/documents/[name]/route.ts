import { getApimToken } from "@/lib/server-auth";
import { getBackendBaseUrl } from "@/lib/agent-url";
import { getUserId } from "@/lib/user-auth";

type Dependencies = {
  getToken: () => Promise<string | null>;
  getBaseUrl: () => string;
  getUserId: (headers: Headers) => string | null;
  fetcher: typeof fetch;
};

type RouteContext = {
  params: Promise<{ name: string }>;
};

function authHeaders(token: string | null, userId: string): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json", "X-RAG-User-ID": userId };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function createDocumentsDeleteHandler(deps: Dependencies) {
  return async (request: Request, context: RouteContext) => {
    const userId = deps.getUserId(request.headers);
    if (!userId) return new Response("Unauthorized", { status: 401 });
    try {
      const { name } = await context.params;
      const token = await deps.getToken();
      const response = await deps.fetcher(
        `${deps.getBaseUrl()}/corpus/documents/${encodeURIComponent(name)}`,
        {
          method: "DELETE",
          headers: authHeaders(token, userId),
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
  getUserId,
  fetcher: fetch,
});
