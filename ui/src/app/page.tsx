import { headers } from "next/headers";
import { Chat } from "./chat";
import { ConsoleHeader } from "./console-header";
import { StatusGate } from "./status-gate";
import { getUserPrincipal, isUserAuthRequired } from "@/lib/user-auth";

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
