// @vitest-environment jsdom
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { useConfigureSuggestions } = vi.hoisted(() => ({
  useConfigureSuggestions: vi.fn(),
}));

vi.mock("@copilotkit/react-core/v2", () => ({
  useConfigureSuggestions: (...args: unknown[]) => useConfigureSuggestions(...args),
}));

import { SuggestedQuestions } from "./suggested-questions";

type Suggestion = { title: string; message: string };

const suggestions: Suggestion[] = [
  { title: "Install Powerwall", message: "How do I install Powerwall?" },
  { title: "Clean a filter", message: "How do I clean the filter?" },
];

function stubFetch(response: Response | Promise<Response>) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("SuggestedQuestions", () => {
  it("starts disabled, fetches uncached suggestions, and registers them before the first message", async () => {
    const fetchMock = stubFetch(
      new Response(JSON.stringify(suggestions), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<SuggestedQuestions />);

    expect(useConfigureSuggestions).toHaveBeenNthCalledWith(1, null, [null]);
    await waitFor(() => expect(useConfigureSuggestions).toHaveBeenCalledTimes(2));

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/api/corpus/suggestions", {
      cache: "no-store",
      signal: expect.any(AbortSignal),
    });

    const [config, dependencies] = useConfigureSuggestions.mock.calls[1] as [
      { suggestions: Suggestion[]; available: string },
      [Suggestion[]],
    ];
    expect(config).toEqual({
      suggestions,
      available: "before-first-message",
    });
    expect(dependencies).toEqual([suggestions]);
    expect(dependencies[0]).toBe(config.suggestions);
  });

  it("registers an empty static config when the endpoint returns an empty array", async () => {
    stubFetch(new Response("[]", { status: 200 }));

    render(<SuggestedQuestions />);

    await waitFor(() => expect(useConfigureSuggestions).toHaveBeenCalledTimes(2));
    expect(useConfigureSuggestions).toHaveBeenNthCalledWith(
      2,
      {
        suggestions: [],
        available: "before-first-message",
      },
      [[]],
    );
  });

  it("stays disabled when the endpoint returns an HTTP failure", async () => {
    const json = vi.fn();
    const fetchMock = stubFetch({ ok: false, json } as unknown as Response);

    render(<SuggestedQuestions />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    expect(json).not.toHaveBeenCalled();
    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [null]);
  });

  it.each([
    ["an object", { suggestions }],
    ["a missing title", [{ message: "Question?" }]],
    ["an empty title", [{ title: "   ", message: "Question?" }]],
    ["a missing message", [{ title: "Question" }]],
    ["an empty message", [{ title: "Question", message: "" }]],
    [
      "more than four items",
      Array.from({ length: 5 }, (_, index) => ({
        title: `Question ${index}`,
        message: `Message ${index}`,
      })),
    ],
  ])("stays disabled for malformed payload: %s", async (_label, payload) => {
    const fetchMock = stubFetch(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<SuggestedQuestions />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [null]);
  });

  it("stays disabled when fetch rejects", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network unavailable"));
    vi.stubGlobal("fetch", fetchMock);

    render(<SuggestedQuestions />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [null]);
  });

  it("aborts an in-flight request and ignores its response after unmount", async () => {
    let signal: AbortSignal | undefined;
    let resolveFetch!: (response: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        signal = init?.signal ?? undefined;
        return pendingResponse;
      }),
    );

    const { unmount } = render(<SuggestedQuestions />);

    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal?.aborted).toBe(false);
    const hookCallCount = useConfigureSuggestions.mock.calls.length;

    unmount();
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      resolveFetch(
        new Response(JSON.stringify(suggestions), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      await pendingResponse;
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(useConfigureSuggestions).toHaveBeenCalledTimes(hookCallCount);
  });
});
