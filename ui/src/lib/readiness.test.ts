import { describe, expect, it } from "vitest";
import { normalizeReadiness, normalizeStatusResponse } from "./readiness";

describe("normalizeReadiness", () => {
  it("accepts ready and normalized indexer data", () => {
    expect(normalizeReadiness({
      status: "ready",
      search: {
        status: "available",
        document_count: 4,
        indexer: { status: "success", ended_at: "2026-01-01T00:01:00Z", last_success_ended_at: "2026-01-01T00:01:00Z" },
      },
      openai: { status: "available" },
    })).toMatchObject({
      status: "ready",
      search: "available",
      openai: "available",
      documentCount: 4,
      lastSuccess: "2026-01-01T00:01:00Z",
      indexer: { outcome: "success", time: "2026-01-01T00:01:00Z" },
    });
  });
  it("accepts degraded but rejects malformed payloads as unavailable", () => {
    expect(normalizeReadiness({ status: "degraded", search: { indexer: { status: "transientFailure", started_at: "2026-01-01T00:00:00Z" } } })).toMatchObject({ status: "degraded", indexer: { outcome: "unknown" } });
    expect(normalizeReadiness({ status: "ready" })).toEqual({
      status: "unavailable", search: null, openai: null, documentCount: null, lastSuccess: null, indexer: null,
    });
    expect(normalizeReadiness("oops")).toEqual({
      status: "unavailable", search: null, openai: null, documentCount: null, lastSuccess: null, indexer: null,
    });
  });
  it("parses unavailable bodies with dependency detail", () => {
    expect(normalizeReadiness({
      status: "unavailable",
      search: { status: "unavailable", document_count: 0, indexer: { status: "failed", last_success_ended_at: "2026-01-01T00:30:00Z" } },
      openai: { status: "unavailable" },
    })).toEqual({
      status: "unavailable",
      search: "unavailable",
      openai: "unavailable",
      documentCount: 0,
      lastSuccess: "2026-01-01T00:30:00Z",
      indexer: { outcome: "failed", time: null },
    });
  });
  it("allowlists indexer outcomes and normalizes invalid timestamps", () => {
    expect(normalizeReadiness({ status: "ready", search: { indexer: { status: "internal secret", ended_at: "not-a-date" } } })).toEqual({
      status: "ready", search: null, openai: null, documentCount: null, lastSuccess: null, indexer: { outcome: "unknown", time: null },
    });
    for (const outcome of ["success", "failed", "running", "unknown"]) {
      expect(normalizeReadiness({ status: "ready", search: { indexer: { status: outcome } } }).indexer?.outcome).toBe(outcome);
    }
  });
});

describe("normalizeStatusResponse", () => {
  it("keeps unavailable dependency detail from the status route", () => {
    expect(normalizeStatusResponse({
      status: "unavailable",
      search: "unavailable",
      openai: "available",
      documentCount: 0,
      lastSuccess: "2026-01-01T00:30:00Z",
    })).toEqual({
      status: "unavailable",
      search: "unavailable",
      openai: "available",
      documentCount: 0,
      lastSuccess: "2026-01-01T00:30:00Z",
      indexer: null,
    });
  });
});
