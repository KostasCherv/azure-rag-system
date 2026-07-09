// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const useConfigureSuggestions = vi.fn();

vi.mock("@copilotkit/react-core/v2", () => ({
  useConfigureSuggestions: (...args: unknown[]) => useConfigureSuggestions(...args),
}));

import { SuggestedQuestions } from "./suggested-questions";

afterEach(cleanup);

describe("SuggestedQuestions", () => {
  it("registers four static suggestions", () => {
    render(<SuggestedQuestions />);

    expect(useConfigureSuggestions).toHaveBeenCalledOnce();
    const config = useConfigureSuggestions.mock.calls[0][0] as {
      suggestions: Array<{ title: string; message: string }>;
    };
    expect(config.suggestions).toHaveLength(4);
    expect(config.suggestions.map((suggestion) => suggestion.message)).toEqual([
      "How do I install the Tesla Powerwall 3?",
      "How do I clean the Dyson V10 filter?",
      "What are the specs of the Ecobee Smart Thermostat Lite?",
      "Compare the Hive and Ecobee smart thermostats",
    ]);
  });
});
