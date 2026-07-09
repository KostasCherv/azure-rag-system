// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@copilotkit/react-core/v2", () => ({
  CopilotChatAssistantMessage: {
    MarkdownRenderer: ({ content }: { content: string }) => <div>{content}</div>,
  },
}));

import { CitationAnchor, linkifyCitations } from "./citation-markdown";

afterEach(cleanup);

describe("linkifyCitations", () => {
  it("converts inline citation markers into cite links", () => {
    expect(linkifyCitations("Encrypted at rest [1] and in transit [10].")).toBe(
      "Encrypted at rest [1](#cite-1) and in transit [10](#cite-10).",
    );
    expect(linkifyCitations("Adjacent [1][2] markers.")).toBe(
      "Adjacent [1](#cite-1)[2](#cite-2) markers.",
    );
  });

  it("leaves markdown links and incomplete markers untouched", () => {
    const input = "See [1](https://example.com) and partial [1";
    expect(linkifyCitations(input)).toBe(input);
  });
});

describe("CitationAnchor", () => {
  it("renders cite links as citation marker buttons and keeps normal links", () => {
    const { rerender } = render(
      <CitationAnchor href="#cite-1">1</CitationAnchor>,
    );

    const marker = screen.getByRole("button", { name: "Go to source 1" });
    expect(marker.className).toContain("citation-marker");

    rerender(
      <CitationAnchor href="https://example.com">docs</CitationAnchor>,
    );
    expect(screen.getByRole("link", { name: "docs" }).getAttribute("href")).toBe(
      "https://example.com",
    );
  });
});
