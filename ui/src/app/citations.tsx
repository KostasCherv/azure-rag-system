"use client";

import { ChevronRight, FileText } from "lucide-react";

type Citation = {
  id: number;
  document: string;
  chunk: string;
};

export function parseSearchDocsResult(result: string | undefined): Citation[] {
  if (!result) return [];
  try {
    const parsed = JSON.parse(result) as { citations?: unknown };
    if (!Array.isArray(parsed.citations)) return [];
    return parsed.citations.flatMap((item) => {
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
  } catch {
    return [];
  }
}

export function SearchDocsSources({ result }: { result: string | undefined }) {
  const citations = parseSearchDocsResult(result);
  if (citations.length === 0) return null;

  return (
    <details className="citation-panel" open>
      <summary>
        <FileText size={15} />
        Sources
      </summary>
      <div className="citation-list">
        {citations.map((citation) => (
          <details className="citation-item" key={citation.id}>
            <summary>
              <ChevronRight size={14} />
              <span>[{citation.id}] {citation.document}</span>
            </summary>
            <p>{citation.chunk}</p>
          </details>
        ))}
      </div>
    </details>
  );
}
