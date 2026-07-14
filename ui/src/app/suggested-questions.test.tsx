// @vitest-environment jsdom
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { useConfigureSuggestions } = vi.hoisted(() => ({
  useConfigureSuggestions: vi.fn(),
}));

vi.mock("@copilotkit/react-core/v2", () => ({
  useConfigureSuggestions: (...args: unknown[]) => useConfigureSuggestions(...args),
}));

import { DiscussionSuggestions, SuggestedQuestions } from "./suggested-questions";

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
  sessionStorage.clear();
});

describe("SuggestedQuestions", () => {
  it("starts disabled, fetches uncached suggestions, and registers them before the first message", async () => {
    const fetchMock = stubFetch(
      new Response(JSON.stringify(suggestions), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<SuggestedQuestions enabled />);

    expect(useConfigureSuggestions).toHaveBeenNthCalledWith(1, null, [true, null]);
    await waitFor(() => expect(useConfigureSuggestions).toHaveBeenCalledTimes(2));

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/api/corpus/suggestions", {
      cache: "no-store",
      signal: expect.any(AbortSignal),
    });

    const [config, dependencies] = useConfigureSuggestions.mock.calls[1] as [
      { suggestions: Suggestion[]; available: string },
      [boolean, Suggestion[]],
    ];
    expect(config).toEqual({
      suggestions,
      available: "before-first-message",
    });
    expect(dependencies).toEqual([true, suggestions]);
    expect(dependencies[1]).toBe(config.suggestions);
  });

  it("registers an empty static config when the endpoint returns an empty array", async () => {
    stubFetch(new Response("[]", { status: 200 }));

    render(<SuggestedQuestions enabled />);

    await waitFor(() => expect(useConfigureSuggestions).toHaveBeenCalledTimes(2));
    expect(useConfigureSuggestions).toHaveBeenNthCalledWith(
      2,
      {
        suggestions: [],
        available: "before-first-message",
      },
      [true, []],
    );
  });

  it("stays disabled when the endpoint returns an HTTP failure", async () => {
    const json = vi.fn();
    const fetchMock = stubFetch({ ok: false, json } as unknown as Response);

    render(<SuggestedQuestions enabled />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    expect(json).not.toHaveBeenCalled();
    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [true, null]);
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

    render(<SuggestedQuestions enabled />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [true, null]);
  });

  it("stays disabled when fetch rejects", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network unavailable"));
    vi.stubGlobal("fetch", fetchMock);

    render(<SuggestedQuestions enabled />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [true, null]);
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

    const { unmount } = render(<SuggestedQuestions enabled />);

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

  it("does not load or register corpus prompts for an ongoing discussion", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<SuggestedQuestions enabled={false} />);

    await act(async () => {});
    expect(fetchMock).not.toHaveBeenCalled();
    expect(useConfigureSuggestions).toHaveBeenCalledWith(null, [false, null]);
  });
});

describe("DiscussionSuggestions", () => {
  it("makes one request and hard-caps history-based suggestions at three", async () => {
    const returned = [
      { title: "One", message: "Question one?" },
      { title: "Two", message: "Question two?" },
      { title: "Three", message: "Question three?" },
      { title: "Four", message: "Question four?" },
    ];
    const fetchMock = stubFetch(new Response(JSON.stringify(returned), { status: 200 }));
    const messages = [
      { id: "u-one-call", role: "user", content: "Tell me about deployment." },
      { id: "a-one-call", role: "assistant", content: "Deployment uses Azure." },
    ];

    render(
      <StrictMode>
        <DiscussionSuggestions
          discussionId="discussion-one-call"
          enabled
          messages={messages}
        />
      </StrictMode>,
    );

    await waitFor(() => {
      const configured = useConfigureSuggestions.mock.calls.some(
        ([config]) => config && (config as { suggestions?: Suggestion[] }).suggestions?.length === 3,
      );
      expect(configured).toBe(true);
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/api/discussion/suggestions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [
          { role: "user", content: "Tell me about deployment." },
          { role: "assistant", content: "Deployment uses Azure." },
        ],
      }),
      cache: "no-store",
    });
    const configured = useConfigureSuggestions.mock.calls
      .map(([config]) => config as { suggestions?: Suggestion[] } | null)
      .find((config) => config?.suggestions?.length === 3);
    expect(configured).toEqual({
      suggestions: returned.slice(0, 3),
      available: "after-first-message",
      consumerAgentId: "default",
    });
  });

  it("stays disabled while history is unavailable or the agent is running", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <DiscussionSuggestions
        discussionId="discussion-disabled"
        enabled={false}
        messages={[{ id: "a-disabled", role: "assistant", content: "Answer" }]}
      />,
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(useConfigureSuggestions.mock.calls.at(-1)?.[0]).toBeNull();
  });

  it("does not retry a failed request for the same completed turn", async () => {
    const fetchMock = stubFetch(new Response("failure", { status: 503 }));
    const messages = [{ id: "a-no-retry", role: "assistant", content: "Answer" }];
    const view = render(
      <DiscussionSuggestions discussionId="discussion-no-retry" enabled messages={messages} />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await act(async () => {});
    view.rerender(
      <DiscussionSuggestions discussionId="discussion-no-retry" enabled messages={messages} />,
    );
    await act(async () => {});

    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
