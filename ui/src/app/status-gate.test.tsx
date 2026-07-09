// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusGate } from "./status-gate";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("StatusGate", () => {
  it("transitions from Checking to Connected, displays indexer, and gates chat", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      status: "ready",
      search: "available",
      openai: "available",
      documentCount: 12,
      lastSuccess: "2026-01-01T00:00:00Z",
      indexer: { outcome: "success", time: "2026-01-01T00:00:00Z" },
    })));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    expect(screen.getByText("Checking")).toBeTruthy();
    expect(screen.queryByText("chat-ui")).toBeNull();
    await screen.findByText("Connected");
    expect(screen.getByText(/success/)).toBeTruthy();
    expect(screen.getByText(/Docs: 12/)).toBeTruthy();
    expect(screen.getByText(/Last index:/)).toBeTruthy();
    expect(screen.getAllByText(/Jan/).length).toBeGreaterThan(0);
    expect(screen.getByText("chat-ui")).toBeTruthy();
  });

  it("removes stale Connected after a network error and polls every 30 seconds", async () => {
    vi.useFakeTimers();
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      status: "ready", search: "available", openai: "available", documentCount: null, lastSuccess: null, indexer: { outcome: "success", time: null },
    }))).mockRejectedValueOnce(new Error("network"));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    await act(async () => {});
    expect(screen.getByText("Connected")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.queryByText("chat-ui")).toBeNull();
  });

  it("never overlaps polls, so an older ready response cannot overwrite a newer result", async () => {
    vi.useFakeTimers();
    let resolveFirst!: (response: Response) => void;
    const first = new Promise<Response>((done) => { resolveFirst = done; });
    const fetcher = vi.spyOn(globalThis, "fetch").mockReturnValueOnce(first).mockResolvedValueOnce(new Response("bad", { status: 503 }));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetcher).toHaveBeenCalledOnce();
    resolveFirst(new Response(JSON.stringify({
      status: "ready", search: "available", openai: "available", documentCount: null, lastSuccess: null, indexer: { outcome: "success", time: null },
    })));
    await act(async () => {});
    expect(screen.getByText("Connected")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.queryByText("chat-ui")).toBeNull();
  });

  it("shows Degraded and aborts polling on unmount", async () => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => { signal = init?.signal ?? undefined; return new Response(JSON.stringify({
      status: "degraded", search: "available", openai: "available", documentCount: 1, lastSuccess: null, indexer: { outcome: "failed", time: null },
    })); });
    const view = render(<StatusGate><div>chat-ui</div></StatusGate>);
    await act(async () => {});
    expect(screen.getByText("Degraded")).toBeTruthy();
    expect(screen.queryByText("chat-ui")).toBeNull();
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("treats malformed responses as unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ status: "ready" })));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    await screen.findByText("Unavailable");
  });

  it("never renders arbitrary indexer strings and drops indexer data when unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      status: "unavailable", search: "unavailable", openai: "unavailable", documentCount: 0, lastSuccess: "2026-01-01T00:00:00Z", indexer: { outcome: "sensitive backend detail", time: "2026-01-01T00:00:00Z" },
    })));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    await screen.findByText("Unavailable");
    expect(screen.queryByText(/sensitive/)).toBeNull();
    expect(screen.queryByText(/Indexer:/)).toBeNull();
  });

  it("maps an arbitrary indexer outcome to unknown before rendering", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      status: "ready", search: "available", openai: "available", documentCount: null, lastSuccess: null, indexer: { outcome: "backend secret", time: "invalid" },
    })));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    await screen.findByText("Connected");
    expect(screen.getByText("Indexer: unknown")).toBeTruthy();
    expect(screen.queryByText(/backend secret/)).toBeNull();
  });

  it("clears the scheduled timeout and performs no state update after unmount", async () => {
    vi.useFakeTimers();
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      status: "ready", search: "available", openai: "available", documentCount: null, lastSuccess: null, indexer: { outcome: "success", time: null },
    })));
    const clear = vi.spyOn(window, "clearTimeout");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const view = render(<StatusGate><div>chat-ui</div></StatusGate>);
    await act(async () => {});
    view.unmount();
    expect(clear).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetcher).toHaveBeenCalledOnce();
    expect(consoleError).not.toHaveBeenCalled();
  });
});
