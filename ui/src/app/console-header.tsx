import Link from "next/link";
import { ArrowLeft, Bot, Database, Search } from "lucide-react";
import type { UserPrincipal } from "@/lib/user-auth";

type ConsoleHeaderProps = {
  title: string;
  variant: "chat" | "corpus";
  principal?: UserPrincipal | null;
  activePage?: "chat" | "corpus";
};

export function ConsoleHeader({ title, variant, principal = null, activePage }: ConsoleHeaderProps) {
  return (
    <header className="console-header">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <Bot size={19} strokeWidth={1.8} />
        </span>
        <div>
          <h1>{title}</h1>
        </div>
      </div>

      <nav className="service-strip" aria-label="Console navigation">
        {variant === "chat" ? (
          <>
            <span className="service-label" title="Azure AI Search">
              <Search size={14} />
              <span className="service-label-text">Azure AI Search</span>
            </span>
            <span className="service-label" title="Blob index">
              <Database size={14} />
              <span className="service-label-text">Blob index</span>
            </span>
            <Link className="nav-link" href="/corpus" aria-current={activePage === "corpus" ? "page" : undefined}>
              Corpus
            </Link>
            {principal ? (
              <span className="user-strip">
                {principal.name}
                <a className="nav-link" href="/.auth/logout">Sign out</a>
              </span>
            ) : null}
          </>
        ) : (
          <Link className="nav-link nav-link-back" href="/">
            <ArrowLeft size={14} />
            Back to chat
          </Link>
        )}
      </nav>
    </header>
  );
}
