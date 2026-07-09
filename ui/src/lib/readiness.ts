export type ServiceStatus = "checking" | "ready" | "degraded" | "unavailable";
export type DependencyHealth = "available" | "unavailable" | null;
export type IndexerOutcome = "success" | "failed" | "running" | "unknown";
export type NormalizedReadiness = {
  status: ServiceStatus;
  search: DependencyHealth;
  openai: DependencyHealth;
  documentCount: number | null;
  lastSuccess: string | null;
  indexer: { outcome: IndexerOutcome; time: string | null } | null;
};

const outcomes = new Set<IndexerOutcome>(["success", "failed", "running", "unknown"]);

function normalizeOutcome(value: unknown): IndexerOutcome {
  return typeof value === "string" && outcomes.has(value as IndexerOutcome) ? value as IndexerOutcome : "unknown";
}

function normalizeTime(value: unknown): string | null {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : null;
}

function normalizeDependencyHealth(value: unknown): DependencyHealth {
  return value === "available" || value === "unavailable" ? value : null;
}

function emptyReadiness(status: ServiceStatus): NormalizedReadiness {
  return { status, search: null, openai: null, documentCount: null, lastSuccess: null, indexer: null };
}

function parseSearchSection(search: Record<string, unknown>) {
  const documentCount = typeof search.document_count === "number" && Number.isFinite(search.document_count)
    ? search.document_count
    : null;
  const indexerRaw = search.indexer;
  if (!indexerRaw || typeof indexerRaw !== "object" || typeof (indexerRaw as Record<string, unknown>).status !== "string") {
    return { documentCount, indexer: null, lastSuccess: null };
  }
  const run = indexerRaw as Record<string, unknown>;
  return {
    documentCount,
    indexer: {
      outcome: normalizeOutcome(run.status),
      time: normalizeTime(run.ended_at) ?? normalizeTime(run.started_at),
    },
    lastSuccess: normalizeTime(run.last_success_ended_at),
  };
}

export function normalizeReadiness(value: unknown): NormalizedReadiness {
  if (!value || typeof value !== "object") return unavailable();
  const body = value as Record<string, unknown>;
  const status = body.status;
  if (status !== "ready" && status !== "degraded" && status !== "unavailable") return unavailable();

  const search = body.search;
  const openai = body.openai;
  const searchHealth = search && typeof search === "object"
    ? normalizeDependencyHealth((search as Record<string, unknown>).status)
    : null;
  const openaiHealth = openai && typeof openai === "object"
    ? normalizeDependencyHealth((openai as Record<string, unknown>).status)
    : null;
  const parsedSearch = search && typeof search === "object"
    ? parseSearchSection(search as Record<string, unknown>)
    : { documentCount: null, indexer: null, lastSuccess: null };

  if ((status === "ready" || status === "degraded") && !parsedSearch.indexer) return unavailable();

  return {
    status,
    search: searchHealth,
    openai: openaiHealth,
    documentCount: parsedSearch.documentCount,
    lastSuccess: parsedSearch.lastSuccess,
    indexer: parsedSearch.indexer,
  };
}

export function normalizeStatusResponse(value: unknown): NormalizedReadiness {
  if (!value || typeof value !== "object") return unavailable();
  const body = value as Record<string, unknown>;
  if (body.status === "unavailable") {
    return {
      status: "unavailable",
      search: normalizeDependencyHealth(body.search),
      openai: normalizeDependencyHealth(body.openai),
      documentCount: typeof body.documentCount === "number" && Number.isFinite(body.documentCount) ? body.documentCount : null,
      lastSuccess: normalizeTime(body.lastSuccess),
      indexer: null,
    };
  }
  if (body.status !== "ready" && body.status !== "degraded" && body.status !== "checking") return unavailable();
  const run = body.indexer;
  const indexer = run && typeof run === "object" && typeof (run as Record<string, unknown>).outcome === "string"
    ? {
        outcome: normalizeOutcome((run as Record<string, unknown>).outcome),
        time: normalizeTime((run as Record<string, unknown>).time),
      }
    : null;
  if ((body.status === "ready" || body.status === "degraded") && !indexer) return unavailable();
  return {
    status: body.status,
    search: normalizeDependencyHealth(body.search),
    openai: normalizeDependencyHealth(body.openai),
    documentCount: typeof body.documentCount === "number" && Number.isFinite(body.documentCount) ? body.documentCount : null,
    lastSuccess: normalizeTime(body.lastSuccess),
    indexer,
  };
}

export function unavailable(): NormalizedReadiness { return emptyReadiness("unavailable"); }
