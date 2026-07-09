// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SearchDocsSources, parseSearchDocsResult } from "./citations";

afterEach(cleanup);

describe("search docs citations", () => {
  it("parses structured citation results and never exposes retrieval scores", () => {
    const result = JSON.stringify({
      context: "[1]\nChunk text",
      citations: [
        { id: 1, document: "contoso-product.md", chunk: "Chunk text", score: 2.4 },
      ],
    });

    expect(parseSearchDocsResult(result)).toEqual([
      { id: 1, document: "contoso-product.md", chunk: "Chunk text" },
    ]);
  });

  it("renders citation chunks behind native details", () => {
    render(
      <SearchDocsSources
        result={JSON.stringify({
          citations: [{ id: 1, document: "Contoso Product", chunk: "Fresh dashboards." }],
        })}
      />,
    );

    expect(screen.getByText("Sources")).toBeTruthy();
    expect(screen.getByText("[1] Contoso Product")).toBeTruthy();
    expect(screen.getByText("Fresh dashboards.")).toBeTruthy();
  });
});
