"use client";

import { ChevronRight, FileText } from "lucide-react";

type Citation = {
  id: number;
  document: string;
  chunk: string;
};

export type SearchDocsPayload = {
  citations: Citation[];
  retrievalMs?: number;
};

export function parseSearchDocsResult(result: string | undefined): SearchDocsPayload {
  if (!result) return { citations: [] };
  try {
    const parsed = JSON.parse(result) as { citations?: unknown; retrieval_ms?: unknown };
    const retrievalMs =
      typeof parsed.retrieval_ms === "number" && Number.isFinite(parsed.retrieval_ms)
        ? Math.round(parsed.retrieval_ms)
        : undefined;
    if (!Array.isArray(parsed.citations)) return { citations: [], retrievalMs };
    const citations = parsed.citations.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const citation = item as Record<string, unknown>;
      if (
        typeof citation.id !== "number" ||
        typeof citation.document !== "string" ||
        typeof citation.chunk !== "string"
      ) {
        return [];
      }
      return [{ id: citation.id, document: citation.document, chunk: citation.chunk }];
    });
    return { citations, retrievalMs };
  } catch {
    return { citations: [] };
  }
}

export function scrollToCitation(markerEl: HTMLElement, citationId: number): void {
  const anchors = Array.from(document.querySelectorAll<HTMLElement>("[data-citation-anchor]"));
  const preceding = anchors.filter(
    (anchor) => anchor.compareDocumentPosition(markerEl) & Node.DOCUMENT_POSITION_FOLLOWING,
  );
  const panel = preceding.at(-1);
  if (!panel) return;

  panel.querySelector<HTMLDetailsElement>(".citation-panel")?.setAttribute("open", "");
  const target = panel.querySelector<HTMLElement>(`[data-citation-id="${citationId}"]`);
  if (!target) return;

  if (target instanceof HTMLDetailsElement) target.open = true;
  target.classList.add("citation-highlight");
  window.setTimeout(() => target.classList.remove("citation-highlight"), 1500);
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

export function SearchDocsSources({
  result,
  toolCallId,
}: {
  result: string | undefined;
  toolCallId: string;
}) {
  const { citations, retrievalMs } = parseSearchDocsResult(result);
  if (citations.length === 0) return null;

  const summaryParts = ["Sources", String(citations.length)];

  return (
    <div data-citation-anchor={toolCallId}>
      <details className="citation-panel" open>
        <summary>
          <FileText size={15} />
          <span className="citation-panel-title">{summaryParts.join(" · ")}</span>
          {retrievalMs !== undefined && (
            <span className="citation-latency-badge" aria-label={`Retrieved in ${retrievalMs} milliseconds`}>
              {retrievalMs} ms
            </span>
          )}
        </summary>
        <div className="citation-list">
          {citations.map((citation) => (
            <details
              className="citation-item"
              key={citation.id}
              id={`cite-${toolCallId}-${citation.id}`}
              data-citation-id={citation.id}
            >
              <summary>
                <ChevronRight size={14} />
                <span>[{citation.id}] {citation.document}</span>
              </summary>
              <p>{citation.chunk}</p>
            </details>
          ))}
        </div>
      </details>
    </div>
  );
}
