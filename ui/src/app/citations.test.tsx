// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchDocsSources, parseSearchDocsResult, scrollToCitation } from "./citations";

afterEach(cleanup);

describe("search docs citations", () => {
  it("parses structured citation results and never exposes retrieval scores", () => {
    const result = JSON.stringify({
      context: "[1]\nChunk text",
      retrieval_ms: 280,
      citations: [
        { id: 1, document: "contoso-product.md", chunk: "Chunk text", score: 2.4 },
      ],
    });

    expect(parseSearchDocsResult(result)).toEqual({
      citations: [{ id: 1, document: "contoso-product.md", chunk: "Chunk text" }],
      retrievalMs: 280,
    });
    expect(result).toContain("score");
  });

  it("renders citation chunks with anchor ids and latency badge", () => {
    render(
      <SearchDocsSources
        toolCallId="tool-1"
        result={JSON.stringify({
          retrieval_ms: 320,
          citations: [{ id: 1, document: "Contoso Product", chunk: "Fresh dashboards." }],
        })}
      />,
    );

    expect(screen.getByText("Sources · 1")).toBeTruthy();
    expect(screen.getByLabelText("Retrieved in 320 milliseconds")).toBeTruthy();
    expect(screen.getByText("[1] Contoso Product — Fresh dashboards.")).toBeTruthy();
    expect(screen.getByText("Fresh dashboards.")).toBeTruthy();
    expect(document.querySelector('[data-citation-anchor="tool-1"]')).toBeTruthy();
    expect(document.querySelector('[data-citation-id="1"]')?.id).toBe("cite-tool-1-1");
  });

  it("omits latency badge when retrieval_ms is absent", () => {
    render(
      <SearchDocsSources
        toolCallId="tool-2"
        result={JSON.stringify({
          citations: [{ id: 1, document: "Contoso Product", chunk: "Fresh dashboards." }],
        })}
      />,
    );

    expect(screen.queryByLabelText(/Retrieved in/i)).toBeNull();
  });

  it("scrollToCitation opens the nearest preceding source panel", () => {
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    render(
      <>
        <SearchDocsSources
          toolCallId="tool-a"
          result={JSON.stringify({
            citations: [{ id: 1, document: "Older source", chunk: "Older chunk." }],
          })}
        />
        <SearchDocsSources
          toolCallId="tool-b"
          result={JSON.stringify({
            citations: [{ id: 2, document: "Newer source", chunk: "Newer chunk." }],
          })}
        />
        <button type="button" data-testid="marker">
          [2]
        </button>
      </>,
    );

    const marker = screen.getByTestId("marker");
    const newerItem = document.querySelector<HTMLDetailsElement>('[data-citation-id="2"]');
    expect(newerItem?.open).toBe(false);

    scrollToCitation(marker, 2);

    expect(newerItem?.open).toBe(true);
    expect(newerItem?.classList.contains("citation-highlight")).toBe(true);
    expect(scrollIntoView).toHaveBeenCalled();
  });
});
