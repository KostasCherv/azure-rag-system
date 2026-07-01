"use client";

import { type ReactNode, useEffect, useState } from "react";
import type { NormalizedReadiness } from "@/lib/readiness";

const initial: NormalizedReadiness = { status: "checking", indexer: null };

function parseStatus(value: unknown): NormalizedReadiness {
  if (!value || typeof value !== "object") return { status: "unavailable", indexer: null };
  const body = value as Record<string, unknown>;
  if (!["ready", "degraded", "unavailable"].includes(String(body.status))) return { status: "unavailable", indexer: null };
  const indexer = body.indexer;
  if ((body.status === "ready" || body.status === "degraded") && (!indexer || typeof indexer !== "object" || typeof (indexer as Record<string, unknown>).outcome !== "string")) return { status: "unavailable", indexer: null };
  return body as NormalizedReadiness;
}

export function StatusGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState(initial);
  useEffect(() => {
    const controller = new AbortController();
    const poll = async () => {
      try {
        const response = await fetch("/api/status", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("unavailable");
        setStatus(parseStatus(await response.json()));
      } catch {
        if (!controller.signal.aborted) setStatus({ status: "unavailable", indexer: null });
      }
    };
    void poll();
    const timer = window.setInterval(poll, 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);

  const label = status.status === "ready" ? "Connected" : status.status[0].toUpperCase() + status.status.slice(1);
  const timestamp = status.indexer?.time ? new Date(status.indexer.time).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : null;
  return <>
    <div className="service-strip status-strip" aria-live="polite">
      <span className={`status status-${status.status}`}><i aria-hidden="true" /> {label}</span>
      {status.indexer && <span className="indexer-status">Indexer: {status.indexer.outcome}{timestamp ? ` · ${timestamp}` : ""}</span>}
    </div>
    <section className="chat-workspace" aria-label="RAG assistant">
      {status.status === "ready" ? children : <div className="chat-placeholder">The RAG assistant is {status.status}. Please check again shortly.</div>}
    </section>
  </>;
}
