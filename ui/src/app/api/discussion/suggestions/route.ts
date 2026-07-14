import { getBackendBaseUrl } from "@/lib/agent-url";
import { getApimToken } from "@/lib/server-auth";
import { getUserId } from "@/lib/user-auth";

const MAX_BODY_BYTES = 64 * 1024;

type Dependencies = {
  getToken: () => Promise<string | null>;
  getBaseUrl: () => string;
  getUserId: (headers: Headers) => string | null;
  fetcher: typeof fetch;
};

export function createDiscussionSuggestionsPostHandler(deps: Dependencies) {
  return async (request: Request) => {
    const userId = deps.getUserId(request.headers);
    if (!userId) return new Response("Unauthorized", { status: 401 });

    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
      return Response.json({ error: "request too large" }, { status: 413 });
    }

    try {
      const token = await deps.getToken();
      const headers: Record<string, string> = {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-RAG-User-ID": userId,
      };
      if (token) headers.Authorization = `Bearer ${token}`;

      const response = await deps.fetcher(`${deps.getBaseUrl()}/discussion/suggestions`, {
        method: "POST",
        headers,
        body,
        cache: "no-store",
      });
      if (!response.ok) return Response.json([], { status: 200 });

      return new Response(await response.text(), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    } catch {
      return Response.json([], { status: 200 });
    }
  };
}

export const POST = createDiscussionSuggestionsPostHandler({
  getToken: getApimToken,
  getBaseUrl: getBackendBaseUrl,
  getUserId,
  fetcher: fetch,
});
