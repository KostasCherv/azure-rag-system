import Link from "next/link";
import { Bot } from "lucide-react";
import { CorpusPanel } from "./corpus-panel";

export default function CorpusPage() {
  return (
    <main className="console-shell">
      <header className="console-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Bot size={19} strokeWidth={1.8} />
          </span>
          <div>
            <h1>Corpus Browser</h1>
          </div>
        </div>
        <Link href="/">Back to chat</Link>
      </header>
      <section className="console-main">
        <div className="chat-workspace corpus-workspace">
          <CorpusPanel />
        </div>
      </section>
    </main>
  );
}
