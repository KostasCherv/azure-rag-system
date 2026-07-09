"use client";

import { useConfigureSuggestions } from "@copilotkit/react-core/v2";

const SUGGESTIONS = [
  {
    title: "How do I install the Tesla Powerwall 3?",
    message: "How do I install the Tesla Powerwall 3?",
  },
  {
    title: "How do I clean the Dyson V10 filter?",
    message: "How do I clean the Dyson V10 filter?",
  },
  {
    title: "What are the specs of the Ecobee Smart Thermostat Lite?",
    message: "What are the specs of the Ecobee Smart Thermostat Lite?",
  },
  {
    title: "Compare the Hive and Ecobee smart thermostats",
    message: "Compare the Hive and Ecobee smart thermostats",
  },
] as const;

const SUGGESTIONS_CONFIG = {
  suggestions: [...SUGGESTIONS],
};

export function SuggestedQuestions() {
  useConfigureSuggestions(SUGGESTIONS_CONFIG);
  return null;
}
