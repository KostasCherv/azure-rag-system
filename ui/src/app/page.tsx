import { Bot, Database, Search } from "lucide-react";
import { Chat } from "./chat";
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
        </div>
      </header>

      <StatusGate>
        <Chat />
      </StatusGate>
    </main>
  );
}
