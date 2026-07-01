import { getReadyUrl } from "@/lib/agent-url";
import { normalizeReadiness, unavailable } from "@/lib/readiness";
import { getApimToken } from "@/lib/server-auth";

type Dependencies = { getToken: () => Promise<string>; getUrl: () => string; fetcher: typeof fetch };

export function timeoutSignal(milliseconds: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), milliseconds);
  return controller.signal;
}

export function createStatusHandler(deps: Dependencies) {
  return async () => {
    try {
      const token = await deps.getToken();
      const response = await deps.fetcher(deps.getUrl(), { headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, signal: timeoutSignal(6000), cache: "no-store" });
      if (!response.ok) return Response.json(unavailable(), { status: 503 });
      const normalized = normalizeReadiness(await response.json());
      return Response.json(normalized, { status: normalized.status === "unavailable" ? 503 : 200 });
    } catch {
      return Response.json(unavailable(), { status: 503 });
    }
  };
}

export const GET = createStatusHandler({ getToken: getApimToken, getUrl: getReadyUrl, fetcher: fetch });
