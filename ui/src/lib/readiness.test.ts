import { describe, expect, it } from "vitest";
import { normalizeReadiness } from "./readiness";

describe("normalizeReadiness", () => {
  it("accepts ready and normalized indexer data", () => {
    expect(normalizeReadiness({ status: "ready", search: { status: "available", document_count: 4, indexer: { status: "success", ended_at: "2026-01-01T00:01:00Z" } }, openai: { status: "available" } })).toMatchObject({ status: "ready", indexer: { outcome: "success", time: "2026-01-01T00:01:00Z" } });
  });
  it("accepts degraded but rejects malformed payloads as unavailable", () => {
    expect(normalizeReadiness({ status: "degraded", search: { indexer: { status: "transientFailure", started_at: "2026-01-01T00:00:00Z" } } })).toMatchObject({ status: "degraded", indexer: { outcome: "unknown" } });
    expect(normalizeReadiness({ status: "ready" })).toEqual({ status: "unavailable", indexer: null });
    expect(normalizeReadiness("oops")).toEqual({ status: "unavailable", indexer: null });
  });
  it("allowlists indexer outcomes and normalizes invalid timestamps", () => {
    expect(normalizeReadiness({ status: "ready", search: { indexer: { status: "internal secret", ended_at: "not-a-date" } } })).toEqual({ status: "ready", indexer: { outcome: "unknown", time: null } });
    for (const outcome of ["success", "failed", "running", "unknown"]) {
      expect(normalizeReadiness({ status: "ready", search: { indexer: { status: outcome } } }).indexer?.outcome).toBe(outcome);
    }
  });
});
