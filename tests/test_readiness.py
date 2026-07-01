from datetime import datetime, timezone
from threading import Event

from fastapi.testclient import TestClient

from azure_rag.api import create_app
from azure_rag.config import AppConfig
from azure_rag.readiness import (
    DependencyResult,
    IndexerResult,
    ReadinessService,
    SearchResult,
    normalize_indexer,
    probe_openai,
    probe_search,
    sanitize_error,
)


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


def successful_search(indexer_status="success"):
    return SearchResult(
        status="available",
        document_count=3,
        indexer=IndexerResult(status=indexer_status, started_at="2026-01-01T00:00:00Z", ended_at="2026-01-01T00:01:00Z"),
    )


def successful_openai():
    return DependencyResult(status="available")


class FakeRag:
    credential = object()
    openai = object()
    def close(self): pass


def test_health_does_not_run_readiness_probes():
    calls = []
    readiness = ReadinessService(lambda: calls.append("search"), lambda: calls.append("openai"))
    app = create_app(config=config(), rag_service=FakeRag(), readiness_service=readiness)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert calls == []


def test_healthy_readiness_returns_structured_200():
    service = ReadinessService(successful_search, successful_openai)
    app = create_app(config=config(), rag_service=FakeRag(), readiness_service=service)
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "search": {
            "status": "available", "document_count": 3,
            "indexer": {"status": "success", "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T00:01:00Z", "error": None},
            "error": None,
        },
        "openai": {"status": "available", "error": None},
    }


def test_failed_historical_indexer_is_degraded_but_200():
    service = ReadinessService(lambda: successful_search("failed"), successful_openai)
    result = service.check()
    assert result.status == "degraded"
    assert result.http_status == 200


def test_zero_documents_is_unavailable_503():
    service = ReadinessService(lambda: SearchResult(status="available", document_count=0), successful_openai)
    assert service.check().http_status == 503


def test_unavailable_readiness_endpoint_returns_503():
    service = ReadinessService(lambda: SearchResult(status="available", document_count=0), successful_openai)
    app = create_app(config=config(), rag_service=FakeRag(), readiness_service=service)
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_each_dependency_failure_is_unavailable():
    for search, openai in [
        (lambda: (_ for _ in ()).throw(RuntimeError("search failed")), successful_openai),
        (successful_search, lambda: (_ for _ in ()).throw(RuntimeError("openai failed"))),
    ]:
        result = ReadinessService(search, openai).check()
        assert result.status == "unavailable"
        assert result.http_status == 503


def test_dependency_timeout_is_bounded():
    blocked = Event()
    result = ReadinessService(lambda: blocked.wait(1), successful_openai, timeout_seconds=0.01).check()
    assert result.http_status == 503
    assert result.search.status == "unavailable"
    assert result.search.error == "probe timed out"


def test_cache_is_reused_then_expires():
    now = [0.0]
    calls = []
    service = ReadinessService(
        lambda: calls.append("s") or successful_search(),
        lambda: calls.append("o") or successful_openai(),
        clock=lambda: now[0], cache_seconds=30,
    )
    first = service.check()
    now[0] = 29
    assert service.check() is first
    now[0] = 31
    assert service.check() is not first
    assert calls == ["s", "o", "s", "o"]


def test_indexer_normalization_and_error_sanitization():
    raw = {
        "lastResult": {
            "status": "transientFailure",
            "startTime": "2026-01-01T00:00:00+00:00",
            "endTime": "2026-01-01T00:01:00+00:00",
            "errorMessage": "Bearer secret-token at https://private.example/path\n" + "x" * 500,
        }
    }
    result = normalize_indexer(raw)
    assert result.status == "failed"
    assert result.started_at == "2026-01-01T00:00:00Z"
    assert result.ended_at == "2026-01-01T00:01:00Z"
    assert "secret-token" not in result.error
    assert "private.example" not in result.error
    assert len(result.error) <= 200
    assert sanitize_error(RuntimeError("api-key=abc123 endpoint https://host/path")) == "api-key=[redacted] endpoint [redacted]"


def test_search_probe_uses_count_and_indexer_endpoints_without_downloading_documents():
    calls = []

    class Credential:
        def get_token(self, *scopes):
            return type("Token", (), {"token": "managed-token"})()

    class Response:
        status_code = 200
        text = ""
        def __init__(self, value):
            self.value = value
            self.content = b"1"
        def json(self): return self.value

    class Session:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            if url.endswith("/docs/$count?api-version=2026-05-01-preview"):
                return Response(7)
            return Response({"lastResult": {"status": "success"}})

    result = probe_search(config(), Credential(), Session())
    assert result.document_count == 7
    assert result.indexer.status == "success"
    assert all(call[0] == "GET" for call in calls)
    assert all(call[2]["headers"]["Authorization"] == "Bearer managed-token" for call in calls)
    assert all(call[2]["timeout"] == 5 for call in calls)
    assert not any("/docs/search" in call[1] for call in calls)


def test_openai_probe_is_minimal_and_deterministic():
    captured = {}
    class Completions:
        def create(self, **kwargs): captured.update(kwargs)
    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    assert probe_openai(config(), client).status == "available"
    assert captured["model"] == "chat"
    assert captured["max_tokens"] == 1
    assert captured["temperature"] == 0
