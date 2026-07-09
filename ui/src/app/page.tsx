import Link from "next/link";
import { CopilotChat } from "@copilotkit/react-core/v2";
import { Bot, Database, Search } from "lucide-react";
import { CitationToolRenderer } from "./citation-tool-renderer";
import { StatusGate } from "./status-gate";

export default function Home() {
  return (
    <main className="console-shell">
      <header className="console-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Bot size={19} strokeWidth={1.8} />
          </span>
          <div>
            <h1>Azure RAG Console</h1>
          </div>
        </div>

        <div className="service-strip" aria-label="Active Azure services">
          <span><Search size={14} /> Azure AI Search</span>
          <span><Database size={14} /> Blob index</span>
          <Link href="/corpus">Corpus</Link>
        </div>
      </header>

      <StatusGate>
        <CitationToolRenderer />
        <CopilotChat
          agentId="default"
          welcomeScreen
          labels={{
            modalHeaderTitle: "RAG assistant",
            welcomeMessageText: "Ask a question about the indexed documents.",
            chatInputPlaceholder: "Ask the indexed knowledge base...",
            chatDisclaimerText: "Answers are generated from Azure AI Search results.",
          }}
        />
      </StatusGate>
    </main>
  );
}
