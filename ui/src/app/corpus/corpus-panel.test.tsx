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

  function mockCorpusFetch(options: { failNames?: string[] } = {}) {
    const uploads: string[] = [];
    let indexerRuns = 0;
    const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/corpus/documents" && init?.method === "POST") {
        const file = (init.body as FormData).get("file") as File;
        if (options.failNames?.includes(file.name)) {
          return new Response(JSON.stringify({ detail: "file exceeds 20MB limit" }), { status: 413 });
        }
        uploads.push(file.name);
        return new Response(JSON.stringify({ name: file.name }));
      }
      if (url === "/api/corpus/documents") {
        return new Response(JSON.stringify(uploads.map((name) => ({ name, size: 10, last_modified: null }))));
      }
      if (url === "/api/corpus/indexer" && init?.method === "POST") {
        indexerRuns += 1;
        return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
      }
      if (url === "/api/corpus/indexer") {
        return new Response(JSON.stringify({ status: "unknown", started_at: null, ended_at: null, error: null }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    return { fetcher, uploads, indexerRuns: () => indexerRuns };
  }

  it("uploads a document, starts indexing, and refreshes the list", async () => {
    const { fetcher, indexerRuns } = mockCorpusFetch();
    render(<CorpusPanel />);
    await screen.findByText("No documents in the corpus container.");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["pdf"], "sample.pdf", { type: "application/pdf" });
    await act(async () => { fireEvent.change(input, { target: { files: [file] } }); });
    await screen.findByText("Uploaded sample.pdf. Indexing started.");
    expect(fetcher).toHaveBeenCalledWith("/api/corpus/documents", expect.objectContaining({ method: "POST" }));
    expect(indexerRuns()).toBe(1);
  });

  it("uploads multiple documents in one pass and starts a single indexer run", async () => {
    const { uploads, indexerRuns } = mockCorpusFetch();
    render(<CorpusPanel />);
    await screen.findByText("No documents in the corpus container.");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = [
      new File(["a"], "a.pdf", { type: "application/pdf" }),
      new File(["b"], "b.md", { type: "text/markdown" }),
      new File(["c"], "c.pdf", { type: "application/pdf" }),
    ];
    await act(async () => { fireEvent.change(input, { target: { files } }); });
    await screen.findByText("Uploaded 3 of 3 documents. Indexing started.");
    expect(uploads.sort()).toEqual(["a.pdf", "b.md", "c.pdf"]);
    expect(indexerRuns()).toBe(1);
    expect(screen.getByText("a.pdf")).toBeTruthy();
  });

  it("reports per-file failures but still indexes successful uploads", async () => {
    const { indexerRuns } = mockCorpusFetch({ failNames: ["big.pdf"] });
    render(<CorpusPanel />);
    await screen.findByText("No documents in the corpus container.");
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const files = [
      new File(["a"], "a.pdf", { type: "application/pdf" }),
      new File(["b"], "big.pdf", { type: "application/pdf" }),
    ];
    await act(async () => { fireEvent.change(input, { target: { files } }); });
    await screen.findByText("Uploaded 1 of 2 documents. Indexing started. big.pdf: file exceeds 20MB limit");
    expect(indexerRuns()).toBe(1);
  });

  it("starts the indexer and refreshes corpus while running", async () => {
    vi.useFakeTimers();
    let indexerStatus: {
      status: "success" | "running";
      started_at: string | null;
      ended_at: string | null;
      error: string | null;
    } = { status: "success", started_at: null, ended_at: null, error: null };
    const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/corpus/documents" && init?.method === "POST") {
        return new Response(JSON.stringify({ name: "sample.pdf" }));
      }
      if (url === "/api/corpus/documents") {
        return new Response(JSON.stringify([]));
      }
      if (url === "/api/corpus/indexer" && init?.method === "POST") {
        indexerStatus = { status: "running", started_at: "2026-01-01T00:00:00Z", ended_at: null, error: null };
        return new Response(JSON.stringify({ status: "accepted" }), { status: 202 });
      }
      if (url === "/api/corpus/indexer") {
        return new Response(JSON.stringify(indexerStatus));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    render(<CorpusPanel />);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getByText("Run indexer")); });
    await act(async () => {});
    expect(fetcher).toHaveBeenCalledWith("/api/corpus/indexer", { method: "POST" });
    const documentGetsBeforePoll = fetcher.mock.calls.filter(([url, init]) => url === "/api/corpus/documents" && init?.method !== "POST");
    const indexerGetsBeforePoll = fetcher.mock.calls.filter(([url, init]) => url === "/api/corpus/indexer" && init?.method !== "POST");
    expect(documentGetsBeforePoll.length).toBeGreaterThan(1);
    expect(indexerGetsBeforePoll.length).toBeGreaterThan(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    const documentGetsAfterPoll = fetcher.mock.calls.filter(([url, init]) => url === "/api/corpus/documents" && init?.method !== "POST");
    const indexerGetsAfterPoll = fetcher.mock.calls.filter(([url, init]) => url === "/api/corpus/indexer" && init?.method !== "POST");
    expect(documentGetsAfterPoll.length).toBeGreaterThan(documentGetsBeforePoll.length);
    expect(indexerGetsAfterPoll.length).toBeGreaterThan(indexerGetsBeforePoll.length);
    vi.useRealTimers();
  });
});
