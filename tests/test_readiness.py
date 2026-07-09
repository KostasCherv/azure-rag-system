from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic

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
    last_success = "2026-01-01T00:01:00Z" if indexer_status == "success" else None
    return SearchResult(
        status="available",
        document_count=3,
        indexer=IndexerResult(
            status=indexer_status,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:01:00Z",
            last_success_ended_at=last_success,
        ),
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
            "indexer": {
                "status": "success",
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:01:00Z",
                "last_success_ended_at": "2026-01-01T00:01:00Z",
                "error": None,
            },
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
    service = ReadinessService(lambda: blocked.wait(1), successful_openai, timeout_seconds=0.01)
    started = monotonic()
    result = service.check()
    elapsed = monotonic() - started
    assert result.http_status == 503
    assert result.search.status == "unavailable"
    assert result.search.error == "probe timed out"
    assert elapsed < 0.2
    service.close()


def test_concurrent_callers_share_one_probe_run_without_holding_cache_lock():
    release = Event()
    started = Barrier(3, timeout=0.5)
    calls = []

    def search():
        calls.append("search")
        started.wait()
        release.wait(1)
        return successful_search()

    def openai():
        calls.append("openai")
        started.wait()
        release.wait(1)
        return successful_openai()

    service = ReadinessService(search, openai, timeout_seconds=0.02)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(service.check)
        second = callers.submit(service.check)
        started.wait()
        before_release = monotonic()
        assert first.result(timeout=0.2).http_status == 503
        assert second.result(timeout=0.2).http_status == 503
        assert monotonic() - before_release < 0.2
    assert sorted(calls) == ["openai", "search"]
    release.set()
    service.close()


def test_timed_out_probe_is_not_resubmitted_or_late_promoted():
    now = [0.0]
    release = Event()
    calls = []

    def search():
        calls.append("search")
        release.wait(1)
        return successful_search()

    def openai():
        calls.append("openai")
        release.wait(1)
        return successful_openai()

    service = ReadinessService(
        search, openai, timeout_seconds=0.01, cache_seconds=30, clock=lambda: now[0]
    )
    assert service.check().status == "unavailable"
    now[0] = 31
    assert service.check().status == "unavailable"
    assert sorted(calls) == ["openai", "search"]

    release.set()
    # The timeout result, rather than a late healthy result, owns this cache window.
    assert service.check().status == "unavailable"
    service.close()


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
    assert result.error == "indexer run failed"


def test_last_success_ended_at_uses_successful_last_result():
    result = normalize_indexer({
        "lastResult": {
            "status": "success",
            "startTime": "2026-01-01T00:00:00Z",
            "endTime": "2026-01-01T00:01:00Z",
        }
    })
    assert result.last_success_ended_at == "2026-01-01T00:01:00Z"


def test_last_success_ended_at_scans_execution_history_after_failed_last_result():
    result = normalize_indexer({
        "lastResult": {
            "status": "transientFailure",
            "startTime": "2026-01-02T00:00:00Z",
            "endTime": "2026-01-02T00:01:00Z",
        },
        "executionHistory": [
            {"status": "transientFailure", "endTime": "2026-01-02T00:01:00Z"},
            {"status": "success", "endTime": "2026-01-01T00:30:00Z"},
        ],
    })
    assert result.status == "failed"
    assert result.last_success_ended_at == "2026-01-01T00:30:00Z"


def test_last_success_ended_at_is_none_without_success_history():
    result = normalize_indexer({
        "lastResult": {"status": "transientFailure", "endTime": "2026-01-02T00:01:00Z"},
        "executionHistory": [{"status": "transientFailure", "endTime": "2026-01-01T00:30:00Z"}],
    })
    assert result.last_success_ended_at is None


def test_last_success_ended_at_ignores_malformed_history_timestamps():
    result = normalize_indexer({
        "lastResult": {"status": "failed"},
        "executionHistory": [{"status": "success", "endTime": "not-a-date"}],
    })
    assert result.last_success_ended_at is None


def test_error_summaries_are_strictly_allowlisted_and_suppress_broad_secrets():
    secrets = [
        "password=hunter2", "client_secret=super-secret", "AccountKey=base64value",
        "SharedAccessSignature=sv=2026&sig=secret", "https://host/path?sig=secret",
        "Bearer abc.def.ghi", "totally novel private customer payload",
    ]
    assert {sanitize_error(value) for value in secrets} == {"operation failed"}
    assert sanitize_error("request timed out with password=hunter2") == "operation timed out"
    assert sanitize_error("HTTP 403 client_secret=secret") == "authorization failed"


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
    options = {}
    class Completions:
        def create(self, **kwargs): captured.update(kwargs)
    configured = type("Configured", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    class Client:
        def with_options(self, **kwargs):
            options.update(kwargs)
            return configured
    assert probe_openai(config(), Client(), timeout_seconds=4.75).status == "available"
    assert options == {"timeout": 4.75, "max_retries": 0}
    assert captured["model"] == "chat"
    assert captured["max_tokens"] == 1
    assert captured["temperature"] == 0


def test_openai_request_timeout_becomes_safe_unavailable_result():
    class Completions:
        def create(self, **kwargs):
            raise TimeoutError("timed out; client_secret=do-not-return")
    configured = type("Configured", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    client = type("Client", (), {"with_options": lambda self, **kwargs: configured})()
    result = ReadinessService(
        successful_search, lambda: probe_openai(config(), client, timeout_seconds=0.01)
    ).check()
    assert result.http_status == 503
    assert result.openai.error == "operation timed out"


def test_readiness_probes_execute_in_parallel():
    barrier = Barrier(2, timeout=0.25)
    def search():
        barrier.wait()
        return successful_search()
    def openai():
        barrier.wait()
        return successful_openai()
    assert ReadinessService(search, openai, timeout_seconds=0.5).check().status == "ready"
