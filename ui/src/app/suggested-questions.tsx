"use client";

import { useConfigureSuggestions } from "@copilotkit/react-core/v2";
import { useEffect, useMemo, useState } from "react";

type Suggestion = {
  title: string;
  message: string;
};

type HistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

type LoadedSuggestions = {
  turnKey: string;
  suggestions: Suggestion[];
};

const discussionRequests = new Map<string, Promise<Suggestion[]>>();
const DISCUSSION_SUGGESTION_LIMIT = 3;

function isSuggestionArray(value: unknown): value is Suggestion[] {
  return (
    Array.isArray(value) &&
    value.length <= 4 &&
    value.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as Record<string, unknown>).title === "string" &&
        (item as Record<string, string>).title.trim().length > 0 &&
        typeof (item as Record<string, unknown>).message === "string" &&
        (item as Record<string, string>).message.trim().length > 0,
    )
  );
}

function suggestionItems(value: unknown): Suggestion[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item): item is Suggestion =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as Record<string, unknown>).title === "string" &&
        (item as Record<string, string>).title.trim().length > 0 &&
        typeof (item as Record<string, unknown>).message === "string" &&
        (item as Record<string, string>).message.trim().length > 0,
    )
    .slice(0, DISCUSSION_SUGGESTION_LIMIT);
}

function textContent(message: Record<string, unknown>): string {
  if (typeof message.content === "string") return message.content.trim();
  if (!Array.isArray(message.content)) return "";
  return message.content
    .map((item) => {
      if (typeof item !== "object" || item === null) return "";
      const record = item as Record<string, unknown>;
      return record.type === "text" && typeof record.text === "string" ? record.text : "";
    })
    .join("")
    .trim();
}

function discussionHistory(messages: unknown[]): HistoryMessage[] {
  return messages
    .flatMap((value): HistoryMessage[] => {
      if (typeof value !== "object" || value === null) return [];
      const message = value as Record<string, unknown>;
      if (message.role !== "user" && message.role !== "assistant") return [];
      const content = textContent(message).slice(0, 4_000);
      return content ? [{ role: message.role, content }] : [];
    })
    .slice(-12);
}

function historyKey(discussionId: string, history: HistoryMessage[]): string {
  let hash = 2166136261;
  for (const character of JSON.stringify(history)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `${discussionId}:${history.length}:${(hash >>> 0).toString(36)}`;
}

function storageKey(discussionId: string) {
  return `discussion-suggestions:${discussionId}`;
}

function cachedSuggestions(discussionId: string, turnKey: string): Suggestion[] | null {
  try {
    const raw = sessionStorage.getItem(storageKey(discussionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { turnKey?: unknown; suggestions?: unknown };
    return parsed.turnKey === turnKey ? suggestionItems(parsed.suggestions) : null;
  } catch {
    return null;
  }
}

function requestDiscussionSuggestions(
  discussionId: string,
  turnKey: string,
  history: HistoryMessage[],
): Promise<Suggestion[]> {
  const cached = cachedSuggestions(discussionId, turnKey);
  if (cached !== null) return Promise.resolve(cached);

  const existing = discussionRequests.get(turnKey);
  if (existing) return existing;

  const request = fetch("/api/discussion/suggestions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: history }),
    cache: "no-store",
  })
    .then(async (response) => (response.ok ? suggestionItems(await response.json()) : []))
    .catch(() => [])
    .then((suggestions) => {
      try {
        sessionStorage.setItem(
          storageKey(discussionId),
          JSON.stringify({ turnKey, suggestions }),
        );
      } catch {
        // Session storage is optional; the in-memory promise still prevents duplicate calls.
      }
      return suggestions;
    });

  if (discussionRequests.size >= 100) {
    const oldest = discussionRequests.keys().next().value;
    if (oldest) discussionRequests.delete(oldest);
  }
  discussionRequests.set(turnKey, request);
  return request;
}

export function SuggestedQuestions({ enabled }: { enabled: boolean }) {
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const controller = new AbortController();

    async function loadSuggestions() {
      try {
        const response = await fetch("/api/corpus/suggestions", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) return;

        const payload: unknown = await response.json();
        if (!controller.signal.aborted && isSuggestionArray(payload)) {
          setSuggestions(payload);
        }
      } catch {
        // Suggestions are optional; keep chat available when loading fails.
      }
    }

    void loadSuggestions();
    return () => controller.abort();
  }, [enabled]);

  useConfigureSuggestions(
    !enabled || suggestions === null
      ? null
      : { suggestions, available: "before-first-message" },
    [enabled, suggestions],
  );

  return null;
}

export function DiscussionSuggestions({
  discussionId,
  enabled,
  messages,
}: {
  discussionId: string;
  enabled: boolean;
  messages: unknown[];
}) {
  const history = useMemo(() => discussionHistory(messages), [messages]);
  const turnKey = useMemo(() => historyKey(discussionId, history), [discussionId, history]);
  const [loaded, setLoaded] = useState<LoadedSuggestions | null>(null);

  useEffect(() => {
    if (!enabled || history.length === 0) return;
    let disposed = false;
    void requestDiscussionSuggestions(discussionId, turnKey, history).then((suggestions) => {
      if (!disposed) setLoaded({ turnKey, suggestions });
    });
    return () => {
      disposed = true;
    };
  }, [discussionId, enabled, history, turnKey]);

  const suggestions = loaded?.turnKey === turnKey ? loaded.suggestions : null;
  useConfigureSuggestions(
    enabled && suggestions !== null
      ? { suggestions, available: "after-first-message", consumerAgentId: "default" }
      : null,
    [discussionId, enabled, suggestions, turnKey],
  );

  return null;
}
