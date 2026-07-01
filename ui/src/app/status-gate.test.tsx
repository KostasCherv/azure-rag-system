// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusGate } from "./status-gate";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("StatusGate", () => {
  it("transitions from Checking to Connected, displays indexer, and gates chat", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ status: "ready", indexer: { outcome: "success", time: "2026-01-01T00:00:00Z" } })));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
    expect(screen.getByText("Checking")).toBeTruthy();
    expect(screen.queryByText("chat-ui")).toBeNull();
    await screen.findByText("Connected");
    expect(screen.getByText(/success/)).toBeTruthy();
    expect(screen.getByText(/Jan/)).toBeTruthy();
    expect(screen.getByText("chat-ui")).toBeTruthy();
  });

  it("removes stale Connected after a network error and polls every 30 seconds", async () => {
    vi.useFakeTimers();
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ status: "ready", indexer: { outcome: "success", time: null } }))).mockRejectedValueOnce(new Error("network"));
    render(<StatusGate><div>chat-ui</div></StatusGate>);
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
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => { signal = init?.signal ?? undefined; return new Response(JSON.stringify({ status: "degraded", indexer: { outcome: "failed", time: null } })); });
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
});
