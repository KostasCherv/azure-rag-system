import { getReadyUrl } from "@/lib/agent-url";
import { normalizeReadiness, unavailable } from "@/lib/readiness";
import { getApimToken } from "@/lib/server-auth";
import { getUserPrincipal, isUserAuthRequired } from "@/lib/user-auth";

type Dependencies = { getToken: () => Promise<string | null>; getUrl: () => string; fetcher: typeof fetch };

export function requestTimeout(milliseconds: number): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), milliseconds);
  return { signal: controller.signal, cancel: () => clearTimeout(timer) };
}

export function createStatusHandler(deps: Dependencies) {
  return async (request?: Request) => {
    if (isUserAuthRequired() && !getUserPrincipal(request?.headers ?? new Headers())) {
      return new Response("Unauthorized", { status: 401 });
    }
    try {
      const token = await deps.getToken();
      const headers: Record<string, string> = { Accept: "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const timeout = requestTimeout(6000);
      try {
        const url = deps.getUrl();
        const response = await deps.fetcher(url, { headers, signal: timeout.signal, cache: "no-store" });
        let normalized;
        try {
          normalized = normalizeReadiness(await response.json());
        } catch {
          normalized = unavailable();
        }
        if (!response.ok || normalized.status === "unavailable") {
          const parsed = new URL(url);
          console.warn("RAG readiness probe unhealthy", {
            target: `${parsed.origin}${parsed.pathname}`,
            httpStatus: response.status,
            status: normalized.status,
            search: normalized.search,
            openai: normalized.openai,
            documentCount: normalized.documentCount,
          });
        }
        if (!response.ok) return Response.json(normalized, { status: 503 });
        return Response.json(normalized, { status: normalized.status === "unavailable" ? 503 : 200 });
      } finally {
        timeout.cancel();
      }
    } catch (error) {
      console.warn("RAG readiness probe failed", {
        name: error instanceof Error ? error.name : "UnknownError",
        message: error instanceof Error ? error.message : "unknown error",
      });
      return Response.json(unavailable(), { status: 503 });
    }
  };
}

export const GET = createStatusHandler({ getToken: getApimToken, getUrl: getReadyUrl, fetcher: fetch });
