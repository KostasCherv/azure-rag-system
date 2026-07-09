import { CorpusPanel } from "./corpus-panel";
import { ConsoleHeader } from "../console-header";

export default function CorpusPage() {
  return (
    <main className="console-shell">
      <ConsoleHeader title="Corpus Browser" variant="corpus" activePage="corpus" />
      <section className="console-main">
        <div className="chat-workspace corpus-workspace">
          <CorpusPanel />
        </div>
      </section>
    </main>
  );
}
