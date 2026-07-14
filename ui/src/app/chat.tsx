"use client";

import { CopilotChat, useAgent, UseAgentUpdate } from "@copilotkit/react-core/v2";
import { Check, MessageSquarePlus, Pencil, RefreshCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { CitationToolRenderer } from "./citation-tool-renderer";
import { CitationMarkdownRenderer } from "./citation-markdown";
import { DiscussionSuggestions, SuggestedQuestions } from "./suggested-questions";

type SessionSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};

type SessionDocument = SessionSummary & { messages: Record<string, unknown>[]; etag: string };

async function sessionRequest<T>(path = "", init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/sessions${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const error = new Error(response.status === 409 ? "conflict" : "request failed");
    Object.assign(error, { status: response.status });
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function putSession(session: SessionDocument, messages: Record<string, unknown>[]) {
  return sessionRequest<SessionDocument>(`/${session.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "If-Match": session.etag },
    body: JSON.stringify({ messages }),
  });
}

function ChatDriver({ session, onSaved, onConflict, onSaveFailed }: {
  session: SessionDocument;
  onSaved: (value: SessionDocument) => void;
  onConflict: () => void;
  onSaveFailed: (retry: () => void) => void;
}) {
  const { agent } = useAgent({
    agentId: "default",
    updates: [UseAgentUpdate.OnMessagesChanged, UseAgentUpdate.OnRunStatusChanged],
    throttleMs: 100,
  });
  const previousRunning = useRef(false);
  const loadedId = useRef<string | null>(null);
  const saveChain = useRef<Promise<void> | null>(null);

  const persist = useCallback((messages: Record<string, unknown>[]) => {
    saveChain.current = (saveChain.current ?? Promise.resolve()).then(async () => {
      try {
        const saved = await putSession(session, messages);
        onSaved(saved);
      } catch (error) {
        if ((error as { status?: number }).status === 409) onConflict();
        else {
          function retry() {
            void putSession(session, messages).then(onSaved).catch((retryError) => {
              if ((retryError as { status?: number }).status === 409) onConflict();
              else onSaveFailed(retry);
            });
          }
          onSaveFailed(retry);
        }
      }
    });
  }, [onConflict, onSaveFailed, onSaved, session]);

  // We own thread restore: our runtime is a stateless AG-UI proxy, so passing an
  // explicit threadId to CopilotChat would make connectAgent wipe the messages
  // and replay from a server-side thread store that does not exist here.
  // eslint-disable-next-line react-hooks/immutability -- AbstractAgent is intentionally mutable; CopilotChat assigns threadId the same way
  useEffect(() => {
    if (loadedId.current === session.id) return;
    // eslint-disable-next-line react-hooks/immutability
    agent.threadId = session.id;
    agent.setMessages(session.messages as never[]);
    loadedId.current = session.id;
    previousRunning.current = agent.isRunning;
  }, [agent, session.id, session.messages]);

  useEffect(() => {
    const finished = previousRunning.current && !agent.isRunning;
    previousRunning.current = agent.isRunning;
    if (!finished) return;
    const messages = structuredClone(agent.messages) as Record<string, unknown>[];
    if (messages.length === 0) return; // never overwrite saved history with an empty snapshot
    persist(messages);
  }, [agent.isRunning, agent.messages, persist]);

  return (
    <>
      <DiscussionSuggestions
        discussionId={session.id}
        enabled={agent.threadId === session.id && agent.messages.length > 0 && !agent.isRunning}
        messages={agent.messages}
      />
      <CopilotChat
        key={session.id}
        agentId="default"
        welcomeScreen
        labels={{
          modalHeaderTitle: "RAG assistant",
          welcomeMessageText: "Ask a question about the indexed documents.",
          chatInputPlaceholder: "Ask the indexed knowledge base...",
          chatDisclaimerText: "Answers are generated from Azure AI Search results.",
        }}
        messageView={{ assistantMessage: { markdownRenderer: CitationMarkdownRenderer } }}
      />
    </>
  );
}

export function Chat() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [active, setActive] = useState<SessionDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<{ message: string; retry?: () => void } | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const refreshList = useCallback(async () => {
    const result = await sessionRequest<{ items: SessionSummary[] }>();
    setSessions(result.items);
  }, []);

  const openSession = useCallback(async (id: string) => {
    setError(null);
    try {
      setActive(await sessionRequest<SessionDocument>(`/${id}`));
    } catch {
      setError("Could not load that discussion.");
    }
  }, []);

  const createSession = useCallback(async () => {
    setError(null);
    try {
      const created = await sessionRequest<SessionDocument>("", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      setActive(created);
      await refreshList();
    } catch {
      setError("Could not create a discussion.");
    }
  }, [refreshList]);

  useEffect(() => {
    void (async () => {
      try {
        const result = await sessionRequest<{ items: SessionSummary[] }>();
        setSessions(result.items);
        if (result.items[0]) setActive(await sessionRequest<SessionDocument>(`/${result.items[0].id}`));
        else await createSession();
      } catch {
        setError("Discussion history is unavailable.");
      } finally {
        setLoading(false);
      }
    })();
  }, [createSession]);

  const rename = async (item: SessionSummary) => {
    if (!active || active.id !== item.id || !draftTitle.trim()) return;
    try {
      const saved = await sessionRequest<SessionDocument>(`/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "If-Match": active.etag },
        body: JSON.stringify({ title: draftTitle }),
      });
      setActive(saved);
      setRenaming(null);
      await refreshList();
    } catch {
      setError("Could not rename the discussion.");
    }
  };

  const remove = async (item: SessionSummary) => {
    if (!window.confirm(`Delete “${item.title}”? This cannot be undone.`)) return;
    try {
      await sessionRequest<void>(`/${item.id}`, { method: "DELETE" });
      const remaining = sessions.filter((entry) => entry.id !== item.id);
      setSessions(remaining);
      if (active?.id === item.id) {
        if (remaining[0]) await openSession(remaining[0].id);
        else await createSession();
      }
    } catch {
      setError("Could not delete the discussion.");
    }
  };

  const onSaved = useCallback((saved: SessionDocument) => {
    setActive(saved);
    setSaveError(null);
    void refreshList();
  }, [refreshList]);
  const onConflict = useCallback(() => {
    setSaveError({ message: "This discussion changed in another tab. Reload it before continuing." });
  }, []);
  const onSaveFailed = useCallback((retry: () => void) => setSaveError({ message: "History not saved.", retry }), []);

  return (
    <div className="discussion-layout">
      <aside className="discussion-sidebar" aria-label="Discussion history">
        <button type="button" className="discussion-new" onClick={() => void createSession()}><MessageSquarePlus size={16} />New discussion</button>
        {loading ? <p className="discussion-state">Loading history…</p> : null}
        {!loading && sessions.length === 0 ? <p className="discussion-state">No saved discussions.</p> : null}
        <div className="discussion-list">
          {sessions.map((item) => (
            <div className={`discussion-row ${active?.id === item.id ? "is-active" : ""}`} key={item.id}>
              {renaming === item.id ? (
                <form onSubmit={(event) => { event.preventDefault(); void rename(item); }}>
                  <input aria-label="Discussion title" value={draftTitle} maxLength={60} autoFocus onChange={(event) => setDraftTitle(event.target.value)} />
                  <button aria-label="Save title" type="submit"><Check size={14} /></button>
                  <button aria-label="Cancel rename" type="button" onClick={() => setRenaming(null)}><X size={14} /></button>
                </form>
              ) : (
                <>
                  <button type="button" className="discussion-select" onClick={() => void openSession(item.id)}>
                    <span>{item.title}</span><small>{new Date(item.updatedAt).toLocaleDateString("en-US", { timeZone: "UTC" })}</small>
                  </button>
                  <div className="discussion-actions">
                    <button type="button" aria-label={`Rename ${item.title}`} onClick={() => { if (active?.id !== item.id) void openSession(item.id); setDraftTitle(item.title); setRenaming(item.id); }}><Pencil size={13} /></button>
                    <button type="button" aria-label={`Delete ${item.title}`} onClick={() => void remove(item)}><Trash2 size={13} /></button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
        {error ? <p className="discussion-error" role="alert">{error}</p> : null}
      </aside>
      <section className="discussion-chat">
        <CitationToolRenderer />
        <SuggestedQuestions enabled={active?.messages.length === 0} />
        {saveError ? <div className="save-warning" role="alert">{saveError.message}<button type="button" onClick={saveError.retry ?? (() => { if (active) void openSession(active.id); })}><RefreshCw size={13} />{saveError.retry ? "Retry" : "Reload"}</button></div> : null}
        {active ? <ChatDriver session={active} onSaved={onSaved} onConflict={onConflict} onSaveFailed={onSaveFailed} /> : <div className="chat-placeholder">Preparing discussion…</div>}
      </section>
    </div>
  );
}
