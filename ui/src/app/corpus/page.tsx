import { headers } from "next/headers";
import { CorpusPanel } from "./corpus-panel";
import { ConsoleHeader } from "../console-header";
import { getUserPrincipal, isUserAuthRequired } from "@/lib/user-auth";

export default async function CorpusPage() {
  const principal = isUserAuthRequired() ? getUserPrincipal(await headers()) : null;

  return (
    <main className="console-shell">
      <ConsoleHeader title="Corpus Browser" variant="corpus" activePage="corpus" principal={principal} />
      <section className="console-main">
        <div className="chat-workspace corpus-workspace">
          <CorpusPanel />
        </div>
      </section>
    </main>
  );
}
