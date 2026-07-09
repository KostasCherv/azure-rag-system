"use client";

import { type ChangeEvent, useCallback, useEffect, useState } from "react";

type CorpusDocument = {
  name: string;
  size: number;
  last_modified: string | null;
};

type IndexerStatus = {
  status: "success" | "failed" | "running" | "unknown";
  started_at: string | null;
  ended_at: string | null;
  error: string | null;
};

const initialIndexer: IndexerStatus = { status: "unknown", started_at: null, ended_at: null, error: null };

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function CorpusPanel() {
  const [documents, setDocuments] = useState<CorpusDocument[]>([]);
  const [indexer, setIndexer] = useState<IndexerStatus>(initialIndexer);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refreshDocuments = useCallback(async () => {
    const response = await fetch("/api/corpus/documents", { cache: "no-store" });
    if (!response.ok) throw new Error("failed to list documents");
    setDocuments(await response.json());
  }, []);

  const refreshIndexer = useCallback(async () => {
    const response = await fetch("/api/corpus/indexer", { cache: "no-store" });
    if (!response.ok) throw new Error("failed to read indexer status");
    setIndexer(await response.json());
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([refreshDocuments(), refreshIndexer()]);
      setMessage(null);
    } catch {
      setMessage("Unable to load corpus data.");
    } finally {
      setLoading(false);
    }
  }, [refreshDocuments, refreshIndexer]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const [documentsResponse, indexerResponse] = await Promise.all([
          fetch("/api/corpus/documents", { cache: "no-store" }),
          fetch("/api/corpus/indexer", { cache: "no-store" }),
        ]);
        if (!documentsResponse.ok || !indexerResponse.ok) throw new Error("failed to load");
        if (!active) return;
        setDocuments(await documentsResponse.json());
        setIndexer(await indexerResponse.json());
        setMessage(null);
      } catch {
        if (active) setMessage("Unable to load corpus data.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (indexer.status !== "running") return;
    const timer = window.setInterval(() => { void refreshIndexer(); }, 5000);
    return () => window.clearInterval(timer);
  }, [indexer.status, refreshIndexer]);

  const onUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/corpus/documents", { method: "POST", body: form });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "upload failed");
      }
      await refreshDocuments();
      setMessage(`Uploaded ${file.name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onRunIndexer = async () => {
    setRunning(true);
    setMessage(null);
    try {
      const response = await fetch("/api/corpus/indexer", { method: "POST" });
      if (response.status === 409) throw new Error("Indexer is already running.");
      if (!response.ok) throw new Error("failed to start indexer");
      await refreshIndexer();
      setMessage("Indexer run started.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "failed to start indexer");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="corpus-panel">
      <div className="corpus-actions">
        <label className="corpus-upload">
          <input type="file" accept=".pdf,.md" onChange={onUpload} disabled={uploading} />
          {uploading ? "Uploading..." : "Upload document"}
        </label>
        <button type="button" onClick={() => void onRunIndexer()} disabled={running || indexer.status === "running"}>
          {running ? "Starting..." : "Run indexer"}
        </button>
        <button type="button" onClick={() => void refreshAll()} disabled={loading}>
          Refresh
        </button>
      </div>

      <p className="corpus-indexer" aria-live="polite">
        Indexer: {indexer.status}
        {indexer.ended_at ? ` · ${new Date(indexer.ended_at).toLocaleString()}` : ""}
        {indexer.error ? ` · ${indexer.error}` : ""}
      </p>

      {message && <p className="corpus-message">{message}</p>}

      {loading ? (
        <p className="corpus-placeholder">Loading documents...</p>
      ) : documents.length === 0 ? (
        <p className="corpus-placeholder">No documents in the corpus container.</p>
      ) : (
        <table className="corpus-table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Size</th>
              <th scope="col">Last modified</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.name}>
                <td>{document.name}</td>
                <td>{formatBytes(document.size)}</td>
                <td>{document.last_modified ? new Date(document.last_modified).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
