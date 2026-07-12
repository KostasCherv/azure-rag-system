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

export function SuggestedQuestions() {
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);

  useEffect(() => {
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
  }, []);

  useConfigureSuggestions(
    suggestions === null
      ? null
      : { suggestions, available: "before-first-message" },
    [suggestions],
  );

  return null;
}
