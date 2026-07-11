from fastapi.testclient import TestClient

from azure_rag.api import create_app
from azure_rag.config import AppConfig
from azure_rag.corpus import sanitize_filename
from azure_rag.search_pipeline import AzureSearchError


def config():
    return AppConfig(
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
        search_endpoint="https://example.search.windows.net",
        search_index="rag-index",
        storage_account_url="https://storage.blob.core.windows.net",
        storage_container="docs",
        storage_resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/storage",
    )


class FakeRagService:
    def __init__(self):
        self.config = config()
        self.credential = object()
        self.session = object()
        self.closed = False

    def close(self):
        self.closed = True


def test_sanitize_filename_accepts_safe_names_and_rejects_unsafe():
    assert sanitize_filename("guide.md") == "guide.md"
    assert sanitize_filename("../evil.pdf") == "evil.pdf"
    assert sanitize_filename("my doc (1).pdf") == "my doc _1_.pdf"

    client = TestClient(create_app(config=config(), rag_service=FakeRagService(), register_agui=False))
    with client:
        assert client.post("/corpus/documents", files={"file": ("notes.txt", b"hello", "text/plain")}).status_code == 400


def test_corpus_documents_list_and_upload(monkeypatch):
    seen_user_ids = []

    def fake_list(*args, **kwargs):
        seen_user_ids.append(kwargs["user_id"])
        return [{"name": "guide.md", "size": 10, "last_modified": None}]

    def fake_upload(*args, **kwargs):
        seen_user_ids.append(kwargs["user_id"])
        return "guide.md"

    monkeypatch.setattr("azure_rag.corpus.list_documents", fake_list)
    monkeypatch.setattr("azure_rag.corpus.upload_document", fake_upload)

    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.get("/corpus/documents", headers={"X-RAG-User-ID": "user-a"})
        assert response.status_code == 200
        assert response.json() == [{"name": "guide.md", "size": 10, "last_modified": None}]

        upload = client.post(
            "/corpus/documents",
            files={"file": ("guide.md", b"# hello", "text/markdown")},
        )
        assert upload.status_code == 200
        assert upload.json() == {"name": "guide.md"}
    # header wins when present, local fallback otherwise
    assert seen_user_ids == ["user-a", "local-development-user"]


def test_corpus_documents_fail_closed_without_identity(monkeypatch):
    monkeypatch.setattr("azure_rag.corpus.list_documents", lambda *args, **kwargs: [])
    from dataclasses import replace

    no_fallback = replace(config(), session_local_user_id=None)
    rag = FakeRagService()
    rag.config = no_fallback
    app = create_app(config=no_fallback, rag_service=rag, register_agui=False)
    with TestClient(app) as client:
        assert client.get("/corpus/documents").status_code == 401
        assert (
            client.post("/corpus/documents", files={"file": ("g.md", b"x", "text/markdown")}).status_code == 401
        )
        assert client.delete("/corpus/documents/guide.md").status_code == 401
        assert client.get("/corpus/documents", headers={"X-RAG-User-ID": "bad id!"}).status_code == 401


def test_corpus_upload_rejects_large_files(monkeypatch):
    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.post(
            "/corpus/documents",
            files={"file": ("guide.md", b"x" * (20 * 1024 * 1024 + 1), "text/markdown")},
        )
        assert response.status_code == 413


def test_corpus_indexer_status_and_run(monkeypatch):
    statuses = [
        {"lastResult": {"status": "success"}},
        {"lastResult": {"status": "inProgress"}},
        {"lastResult": {"status": "success"}},
    ]

    def fake_status(*args, **kwargs):
        return statuses.pop(0)

    started = {"called": False}

    def fake_run(*args, **kwargs):
        started["called"] = True
        assert kwargs["wait"] is False
        return {}

    monkeypatch.setattr("azure_rag.corpus.get_indexer_status", fake_status)
    monkeypatch.setattr("azure_rag.corpus.run_indexer", fake_run)

    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        status = client.get("/corpus/indexer")
        assert status.status_code == 200
        assert status.json()["status"] == "success"

        running = client.post("/corpus/indexer/run")
        assert running.status_code == 409

        run = client.post("/corpus/indexer/run")
        assert run.status_code == 202
        assert run.json() == {"status": "accepted"}
        assert started["called"] is True


def test_corpus_maps_azure_failures_to_sanitized_errors(monkeypatch):
    monkeypatch.setattr(
        "azure_rag.corpus.get_indexer_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AzureSearchError("GET failed: 403 forbidden secret")),
    )

    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.get("/corpus/indexer")
        assert response.status_code == 503
        assert response.json()["detail"] == "authorization failed"


def test_corpus_documents_delete(monkeypatch):
    monkeypatch.setattr(
        "azure_rag.corpus.remove_corpus_document",
        lambda *args, **kwargs: {"name": "guide.md", "deleted_chunks": 3},
    )

    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.delete("/corpus/documents/guide.md")
        assert response.status_code == 200
        assert response.json() == {"name": "guide.md", "deleted_chunks": 3}


def test_corpus_documents_delete_rejects_invalid_name(monkeypatch):
    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.delete("/corpus/documents/notes.txt")
        assert response.status_code == 400


def test_corpus_documents_delete_returns_not_found(monkeypatch):
    def fake_remove(*args, **kwargs):
        raise FileNotFoundError("guide.md")

    monkeypatch.setattr("azure_rag.corpus.remove_corpus_document", fake_remove)

    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.delete("/corpus/documents/guide.md")
        assert response.status_code == 404
        assert response.json()["detail"] == "document not found"


def test_corpus_documents_delete_maps_azure_failures(monkeypatch):
    monkeypatch.setattr(
        "azure_rag.corpus.remove_corpus_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(AzureSearchError("POST failed: 403 forbidden secret")),
    )

    app = create_app(config=config(), rag_service=FakeRagService(), register_agui=False)
    with TestClient(app) as client:
        response = client.delete("/corpus/documents/guide.md")
        assert response.status_code == 503
        assert response.json()["detail"] == "authorization failed"
