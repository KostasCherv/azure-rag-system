import { headers } from "next/headers";
import { Chat } from "./chat";
import { ConsoleHeader } from "./console-header";
import { StatusGate } from "./status-gate";
import { getUserPrincipal, isUserAuthRequired } from "@/lib/user-auth";

// Render per-request: REQUIRE_USER_AUTH is unset at image build time, so a
// static prerender would bake in a null principal and hide the user strip.
export const dynamic = "force-dynamic";

export default async function Home() {
  const principal = isUserAuthRequired() ? getUserPrincipal(await headers()) : null;

  return (
    <main className="console-shell">
      <ConsoleHeader title="Azure RAG Console" variant="chat" activePage="chat" principal={principal} />
      <StatusGate>
        <Chat />
      </StatusGate>
    </main>
  );
}
