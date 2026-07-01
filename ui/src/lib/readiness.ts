export type ServiceStatus = "checking" | "ready" | "degraded" | "unavailable";
export type IndexerOutcome = "success" | "failed" | "running" | "unknown";
export type NormalizedReadiness = { status: ServiceStatus; indexer: { outcome: IndexerOutcome; time: string | null } | null };

const outcomes = new Set<IndexerOutcome>(["success", "failed", "running", "unknown"]);

function normalizeOutcome(value: unknown): IndexerOutcome {
  return typeof value === "string" && outcomes.has(value as IndexerOutcome) ? value as IndexerOutcome : "unknown";
}

function normalizeTime(value: unknown): string | null {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : null;
}

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
  const time = normalizeTime(run.ended_at) ?? normalizeTime(run.started_at);
  return { status: body.status, indexer: { outcome: normalizeOutcome(run.status), time } };
}

export function normalizeStatusResponse(value: unknown): NormalizedReadiness {
  if (!value || typeof value !== "object") return unavailable();
  const body = value as Record<string, unknown>;
  if (body.status === "unavailable") return unavailable();
  if (body.status !== "ready" && body.status !== "degraded") return unavailable();
  const run = body.indexer;
  if (!run || typeof run !== "object") return unavailable();
  const indexer = run as Record<string, unknown>;
  if (typeof indexer.outcome !== "string") return unavailable();
  return { status: body.status, indexer: { outcome: normalizeOutcome(indexer.outcome), time: normalizeTime(indexer.time) } };
}

export function unavailable(): NormalizedReadiness { return { status: "unavailable", indexer: null }; }
