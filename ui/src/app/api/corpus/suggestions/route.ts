import { getBackendBaseUrl } from "@/lib/agent-url";
import { getApimToken } from "@/lib/server-auth";
import { getUserId } from "@/lib/user-auth";

type Dependencies = {
  getToken: () => Promise<string | null>;
  getBaseUrl: () => string;
  getUserId: (headers: Headers) => string | null;
  fetcher: typeof fetch;
};

function authHeaders(token: string | null, userId: string): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-RAG-User-ID": userId,
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function createSuggestionsGetHandler(deps: Dependencies) {
  return async (request: Request) => {
    const userId = deps.getUserId(request.headers);
    if (!userId) return new Response("Unauthorized", { status: 401 });

    try {
      const token = await deps.getToken();
      const response = await deps.fetcher(`${deps.getBaseUrl()}/corpus/suggestions`, {
        headers: authHeaders(token, userId),
        cache: "no-store",
      });
      if ([204, 205, 304].includes(response.status)) {
        return new Response(null, { status: response.status });
      }
      if (!response.ok) {
        return Response.json({ error: "failed to load suggestions" }, { status: response.status });
      }

      return new Response(await response.text(), {
        status: response.status,
        headers: { "Content-Type": "application/json" },
      });
    } catch {
      return Response.json({ error: "failed to load suggestions" }, { status: 503 });
    }
  };
}

export const GET = createSuggestionsGetHandler({
  getToken: getApimToken,
  getBaseUrl: getBackendBaseUrl,
  getUserId,
  fetcher: fetch,
});
