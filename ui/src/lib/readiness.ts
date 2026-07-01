export type ServiceStatus = "checking" | "ready" | "degraded" | "unavailable";
export type NormalizedReadiness = { status: ServiceStatus; indexer: { outcome: string; time: string | null } | null };

export function normalizeReadiness(value: unknown): NormalizedReadiness {
  if (!value || typeof value !== "object") return unavailable();
  const body = value as Record<string, unknown>;
  if (body.status !== "ready" && body.status !== "degraded") return unavailable();
  const search = body.search;
  if (!search || typeof search !== "object") return unavailable();
  const indexer = (search as Record<string, unknown>).indexer;
  if (!indexer || typeof indexer !== "object") return unavailable();
  const run = indexer as Record<string, unknown>;
  if (typeof run.status !== "string") return unavailable();
  const time = typeof run.ended_at === "string" ? run.ended_at : typeof run.started_at === "string" ? run.started_at : null;
  return { status: body.status, indexer: { outcome: run.status, time } };
}

export function unavailable(): NormalizedReadiness { return { status: "unavailable", indexer: null }; }
