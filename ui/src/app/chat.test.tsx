// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

let chatProps: Record<string, unknown> = {};
let suggestionsEnabled: boolean | undefined;
const agent = {
  threadId: undefined as string | undefined,
  messages: [] as unknown[],
  isRunning: false,
  setMessages: vi.fn((messages: unknown[]) => { agent.messages = messages; }),
};

vi.mock("@copilotkit/react-core/v2", () => ({
  CopilotChat: (props: Record<string, unknown>) => { chatProps = props; return <div>chat-view</div>; },
  useAgent: () => ({ agent }),
  UseAgentUpdate: { OnMessagesChanged: "OnMessagesChanged", OnRunStatusChanged: "OnRunStatusChanged" },
}));
vi.mock("./citation-tool-renderer", () => ({ CitationToolRenderer: () => null }));
vi.mock("./citation-markdown", () => ({ CitationMarkdownRenderer: () => null }));
vi.mock("./suggested-questions", () => ({
  SuggestedQuestions: ({ enabled }: { enabled: boolean }) => {
    suggestionsEnabled = enabled;
    return null;
  },
  DiscussionSuggestions: () => null,
}));

import { Chat } from "./chat";

const SESSION_ID = "5e9f8f64-6f16-4f6a-9a3f-2b1c9c0a1234";
const savedMessages = [
  { id: "m1", role: "user", content: "what is in the corpus?" },
  { id: "m2", role: "assistant", content: "Documents about Azure." },
];

afterEach(() => { cleanup(); vi.restoreAllMocks(); agent.setMessages.mockClear(); agent.messages = []; agent.threadId = undefined; });

describe("Chat", () => {
  it("restores the saved discussion into the agent on page load", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith(`/api/sessions/${SESSION_ID}`)) {
        return new Response(JSON.stringify({
          id: SESSION_ID, title: "corpus questions", createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-02T00:00:00Z", messageCount: 2, messages: savedMessages, etag: "etag-1",
        }));
      }
      return new Response(JSON.stringify({
        items: [{ id: SESSION_ID, title: "corpus questions", createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-02T00:00:00Z", messageCount: 2 }],
      }));
    });

    render(<Chat />);
    await act(async () => {});
    await screen.findByText("chat-view");

    // history restored into the agent for the persisted thread
    expect(agent.threadId).toBe(SESSION_ID);
    expect(agent.setMessages).toHaveBeenCalledWith(savedMessages);
    expect(suggestionsEnabled).toBe(false);
    // regression: an explicit threadId makes CopilotChat's connectAgent wipe the
    // restored messages and replay from a server-side thread store we don't have
    expect(chatProps.threadId).toBeUndefined();
  });
});
