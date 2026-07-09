"use client";

import { CopilotChat } from "@copilotkit/react-core/v2";
import { CitationToolRenderer } from "./citation-tool-renderer";
import { CitationMarkdownRenderer } from "./citation-markdown";
import { SuggestedQuestions } from "./suggested-questions";

export function Chat() {
  return (
    <>
      <CitationToolRenderer />
      <SuggestedQuestions />
      <CopilotChat
        agentId="default"
        welcomeScreen
        labels={{
          modalHeaderTitle: "RAG assistant",
          welcomeMessageText: "Ask a question about the indexed documents.",
          chatInputPlaceholder: "Ask the indexed knowledge base...",
          chatDisclaimerText: "Answers are generated from Azure AI Search results.",
        }}
        messageView={{
          assistantMessage: {
            markdownRenderer: CitationMarkdownRenderer,
          },
        }}
      />
    </>
  );
}
