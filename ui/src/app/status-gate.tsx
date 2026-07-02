"use client";

import { type ReactNode, useEffect, useState } from "react";
import { normalizeStatusResponse, type NormalizedReadiness } from "@/lib/readiness";

const initial: NormalizedReadiness = { status: "checking", indexer: null };

export function StatusGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState(initial);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const response = await fetch("/api/status", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("unavailable");
        const next = normalizeStatusResponse(await response.json());
        if (!controller.signal.aborted) setStatus(next);
      } catch {
        if (!controller.signal.aborted) setStatus({ status: "unavailable", indexer: null });
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
  const timestamp = status.indexer?.time ? new Date(status.indexer.time).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : null;
  return (
    <section className="console-main">
      <div className="service-strip status-strip" aria-live="polite">
        <span className={`status status-${status.status}`}><i aria-hidden="true" /> {label}</span>
        {status.indexer && <span className="indexer-status">Indexer: {status.indexer.outcome}{timestamp ? ` · ${timestamp}` : ""}</span>}
      </div>
      <section className="chat-workspace" aria-label="RAG assistant">
        {status.status === "ready" ? children : <div className="chat-placeholder">The RAG assistant is {status.status}. Please check again shortly.</div>}
      </section>
    </section>
  );
}
