// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CorpusPanel } from "./corpus-panel";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("CorpusPanel", () => {
  it("lists documents and shows indexer status", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([{ name: "guide.md", size: 5000, last_modified: "2026-01-01T00:00:00Z" }])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "success", started_at: null, ended_at: "2026-01-01T00:00:00Z", error: null })));
    render(<CorpusPanel />);
    expect(screen.getByText("Loading documents...")).toBeTruthy();
    await screen.findByText("guide.md");
    expect(screen.getByText(/Indexer:/)).toBeTruthy();
    expect(screen.getByText("success")).toBeTruthy();
  });

  it("uploads a document and refreshes the list", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "unknown", started_at: null, ended_at: null, error: null })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ name: "sample.pdf" })))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ name: "sample.pdf", size: 10, last_modified: null }])));
    render(<CorpusPanel />);
    await screen.findByText("No documents in the corpus container.");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["pdf"], "sample.pdf", { type: "application/pdf" });
    await act(async () => { fireEvent.change(input, { target: { files: [file] } }); });
    await screen.findByText("Uploaded sample.pdf.");
    expect(fetcher).toHaveBeenCalledWith("/api/corpus/documents", expect.objectContaining({ method: "POST" }));
  });

  it("starts the indexer and polls while running", async () => {
    vi.useFakeTimers();
    const fetcher = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "success", started_at: null, ended_at: null, error: null })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "accepted" }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "running", started_at: "2026-01-01T00:00:00Z", ended_at: null, error: null })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "success", started_at: null, ended_at: "2026-01-01T00:00:00Z", error: null })));
    render(<CorpusPanel />);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getByText("Run indexer")); });
    await act(async () => {});
    expect(fetcher).toHaveBeenCalledWith("/api/corpus/indexer", { method: "POST" });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(fetcher.mock.calls.some(([url]) => url === "/api/corpus/indexer" && !("method" in (fetcher.mock.calls.at(-1)?.[1] ?? {})))).toBe(true);
    vi.useRealTimers();
  });
});
