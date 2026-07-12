"use client";

import { FileText } from "lucide-react";
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
  const [deletingName, setDeletingName] = useState<string | null>(null);
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

  const refreshCorpus = useCallback(async () => {
    await Promise.all([refreshDocuments(), refreshIndexer()]);
  }, [refreshDocuments, refreshIndexer]);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      await refreshCorpus();
      setMessage(null);
    } catch {
      setMessage("Unable to load corpus data.");
    } finally {
      setLoading(false);
    }
  }, [refreshCorpus]);

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
    const timer = window.setInterval(() => { void refreshCorpus(); }, 5000);
    return () => window.clearInterval(timer);
  }, [indexer.status, refreshCorpus]);

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
      await refreshCorpus();
      setMessage("Indexer run started.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "failed to start indexer");
    } finally {
      setRunning(false);
    }
  };

  const onDelete = async (name: string) => {
    if (!window.confirm(`Remove ${name} from corpus and search index?`)) return;
    setDeletingName(name);
    setMessage(null);
    try {
      const response = await fetch(`/api/corpus/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "delete failed");
      }
      const result = await response.json() as { name: string; deleted_chunks: number };
      await refreshDocuments();
      setMessage(`Deleted ${result.name} (${result.deleted_chunks} chunks removed).`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "delete failed");
    } finally {
      setDeletingName(null);
    }
  };

  return (
    <section className="corpus-panel">
      <div className="corpus-actions">
        <label className="corpus-btn corpus-btn-primary corpus-upload">
          <input type="file" accept=".pdf,.md" onChange={onUpload} disabled={uploading} />
          {uploading ? "Uploading..." : "Upload document"}
        </label>
        <button
          type="button"
          className="corpus-btn"
          onClick={() => void onRunIndexer()}
          disabled={running || indexer.status === "running"}
        >
          {running ? "Starting..." : "Run indexer"}
        </button>
        <button type="button" className="corpus-btn" onClick={() => void refreshAll()} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className="corpus-meta">
        <p className="corpus-indexer" aria-live="polite">
          Indexer:{" "}
          <span className={`indexer-badge indexer-${indexer.status}`}>{indexer.status}</span>
          {indexer.ended_at ? ` · ${new Date(indexer.ended_at).toLocaleString()}` : ""}
          {indexer.error ? ` · ${indexer.error}` : ""}
        </p>
      </div>

      {message && <p className="corpus-message">{message}</p>}

      {loading ? (
        <p className="corpus-placeholder">Loading documents...</p>
      ) : documents.length === 0 ? (
        <p className="corpus-placeholder">No documents in the corpus container.</p>
      ) : (
        <div className="corpus-table-wrap">
          <table className="corpus-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Size</th>
                <th scope="col">Last modified</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.name}>
                  <td>
                    <div className="corpus-file-name">
                      <FileText size={15} aria-hidden="true" />
                      <span>{document.name}</span>
                    </div>
                  </td>
                  <td className="corpus-size">{formatBytes(document.size)}</td>
                  <td>{document.last_modified ? new Date(document.last_modified).toLocaleString() : "—"}</td>
                  <td>
                    <button
                      type="button"
                      className="corpus-delete"
                      onClick={() => void onDelete(document.name)}
                      disabled={deletingName === document.name}
                    >
                      {deletingName === document.name ? "Deleting..." : "Delete"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
