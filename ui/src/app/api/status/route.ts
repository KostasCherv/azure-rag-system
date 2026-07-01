import { getReadyUrl } from "@/lib/agent-url";
import { normalizeReadiness, unavailable } from "@/lib/readiness";
import { getApimToken } from "@/lib/server-auth";

type Dependencies = { getToken: () => Promise<string>; getUrl: () => string; fetcher: typeof fetch };

export function requestTimeout(milliseconds: number): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), milliseconds);
  return { signal: controller.signal, cancel: () => clearTimeout(timer) };
}

export function createStatusHandler(deps: Dependencies) {
  return async () => {
    try {
      const token = await deps.getToken();
      const timeout = requestTimeout(6000);
      try {
        const response = await deps.fetcher(deps.getUrl(), { headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, signal: timeout.signal, cache: "no-store" });
        if (!response.ok) return Response.json(unavailable(), { status: 503 });
        const normalized = normalizeReadiness(await response.json());
        return Response.json(normalized, { status: normalized.status === "unavailable" ? 503 : 200 });
      } finally {
        timeout.cancel();
      }
    } catch {
      return Response.json(unavailable(), { status: 503 });
    }
  };
}

export const GET = createStatusHandler({ getToken: getApimToken, getUrl: getReadyUrl, fetcher: fetch });
