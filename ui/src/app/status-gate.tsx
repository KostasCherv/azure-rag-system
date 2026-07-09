"use client";

import { type ReactNode, useEffect, useState } from "react";
import { normalizeStatusResponse, type NormalizedReadiness, unavailable } from "@/lib/readiness";

const initial: NormalizedReadiness = {
  status: "checking",
  search: null,
  openai: null,
  documentCount: null,
  lastSuccess: null,
  indexer: null,
};

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function dependencyLabel(health: NormalizedReadiness["search"], name: string): string {
  if (health === "available") return `${name} available`;
  if (health === "unavailable") return `${name} unavailable`;
  return `${name} unknown`;
}

export function StatusGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState(initial);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const response = await fetch("/api/status", { signal: controller.signal, cache: "no-store" });
        const next = normalizeStatusResponse(await response.json());
        if (!controller.signal.aborted) setStatus(next);
      } catch {
        if (!controller.signal.aborted) setStatus(unavailable());
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(poll, 30_000);
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  const label = status.status === "ready" ? "Connected" : status.status[0].toUpperCase() + status.status.slice(1);
  const indexerTimestamp = status.indexer?.time ? formatTimestamp(status.indexer.time) : null;
  const lastSuccessTimestamp = status.lastSuccess ? formatTimestamp(status.lastSuccess) : null;
  const showLastIndex =
    lastSuccessTimestamp !== null
    && (!status.indexer || indexerTimestamp === null || lastSuccessTimestamp !== indexerTimestamp);

  return (
    <section className="console-main">
      <div className="status-strip" aria-live="polite">
        <div className="status-group">
          <span className={`status-chip status-${status.status}`}>
            <i className="status-dot" aria-hidden="true" />
            {label}
          </span>
          <span
            className={`status-chip dep-${status.search ?? "unknown"}`}
            aria-label={dependencyLabel(status.search, "Search")}
          >
            <i className="status-dot" aria-hidden="true" />
            Search
          </span>
          <span
            className={`status-chip dep-${status.openai ?? "unknown"}`}
            aria-label={dependencyLabel(status.openai, "OpenAI")}
          >
            <i className="status-dot" aria-hidden="true" />
            OpenAI
          </span>
        </div>
        <div className="status-group">
          {status.documentCount !== null ? (
            <span className="status-chip metric-chip">Docs: {status.documentCount.toLocaleString()}</span>
          ) : null}
          {showLastIndex ? (
            <span className="status-chip metric-chip">Last index: {lastSuccessTimestamp}</span>
          ) : null}
          {status.indexer ? (
            <span className="status-chip metric-chip">
              Indexer: {status.indexer.outcome}{indexerTimestamp ? ` · ${indexerTimestamp}` : ""}
            </span>
          ) : null}
        </div>
      </div>
      <section className="chat-workspace" aria-label="RAG assistant">
        {status.status === "ready" ? children : (
          <div className="chat-placeholder">The RAG assistant is {status.status}. Please check again shortly.</div>
        )}
      </section>
    </section>
  );
}
