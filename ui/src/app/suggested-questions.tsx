"use client";

import { useConfigureSuggestions } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

type Suggestion = {
  title: string;
  message: string;
};

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
  messageCount,
}: {
  discussionId: string;
  enabled: boolean;
  messageCount: number;
}) {
  useConfigureSuggestions(
    enabled
      ? {
          instructions:
            "Suggest exactly three concise follow-up questions that naturally continue the current discussion. " +
            "Use only the discussion history, prioritize the latest topic, and do not repeat questions " +
            "that were already answered or suggest unrelated indexed documents.",
          minSuggestions: 3,
          maxSuggestions: 3,
          available: "after-first-message",
          providerAgentId: "default",
          consumerAgentId: "default",
        }
      : null,
    [discussionId, enabled, messageCount],
  );

  return null;
}
