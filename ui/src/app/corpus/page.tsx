import { headers } from "next/headers";
import { CorpusPanel } from "./corpus-panel";
import { ConsoleHeader } from "../console-header";
import { getUserPrincipal, isUserAuthRequired } from "@/lib/user-auth";

// Render per-request: REQUIRE_USER_AUTH is unset at image build time, so a
// static prerender would bake in a null principal and hide the user strip.
export const dynamic = "force-dynamic";

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
