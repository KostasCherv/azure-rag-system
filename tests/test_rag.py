from azure_rag.auth import AZURE_SEARCH_SCOPE
from azure_rag.config import AppConfig
from azure_rag.rag import RagService, RetrievedChunk, source_label


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
        search_min_score=2.0,
    )


class FakeCredential:
    def __init__(self):
        self.scopes = []
        self.closed = False

    def get_token(self, *scopes):
        self.scopes.append(scopes)
        return type("Token", (), {"token": "search-token"})()

    def close(self):
        self.closed = True


class FakeOpenAIClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "value": [
                {
                    "title": "doc",
                    "chunk": "text",
                    "source_path": "doc.md",
                    "@search.captions": [{"text": "caption text"}],
                    "@search.rerankerScore": 2.5,
                }
            ]
        }


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class CapturingSpan:
    def __init__(self):
        self.attributes = {}
        self.exceptions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_exception(self, error):
        self.exceptions.append(error)


class CapturingTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name):
        span = CapturingSpan()
        span.name = name
        self.spans.append(span)
        return span


class FakeLangSmithRun:
    def __init__(self, calls):
        self.calls = calls

    def end(self, **kwargs):
        self.calls.append({"ended": kwargs})


def test_list_visible_titles_queries_search_and_normalizes_titles():
    class TitleResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "value": [
                    {"title": "  Zebra   Guide "},
                    {"title": "alpha manual"},
                    {"title": "ALPHA MANUAL"},
                    {"title": "   "},
                    {"title": ""},
                    {"title": None},
                    {"title": 42},
                    "not-a-document",
                ]
            }

    class TitleSession:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return TitleResponse()

    credential = FakeCredential()
    session = TitleSession()
    service = RagService(
        config(),
        credential=credential,
        openai_client=FakeOpenAIClient(),
        session=session,
    )

    titles = service.list_visible_titles(user_id="user-a")

    assert titles == ["alpha manual", "Zebra Guide"]
    assert session.calls == [
        (
            "https://example.search.windows.net/indexes/rag-index/docs/search?api-version=2026-05-01-preview",
            {
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer search-token",
                },
                "json": {
                    "search": "*",
                    "filter": "(user_id eq 'user-a' or user_id eq null)",
                    "select": "title",
                    "top": 100,
                },
                "timeout": 30,
            },
        )
    ]
    assert credential.scopes == [(AZURE_SEARCH_SCOPE,)]


def test_list_visible_titles_rejects_invalid_user_id():
    import pytest

    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=FakeSession(),
    )

    with pytest.raises(ValueError, match="^invalid user id$"):
        service.list_visible_titles(user_id="bad'id")


def test_list_visible_titles_records_privacy_safe_telemetry(monkeypatch):
    class TitleResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": [{"title": "Private Manual"}]}

    class TitleSession:
        def post(self, *_args, **_kwargs):
            return TitleResponse()

    tracer = CapturingTracer()
    monkeypatch.setattr("azure_rag.rag.tracer", tracer)
    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=TitleSession(),
    )

    assert service.list_visible_titles(user_id="user-a", top=7) == ["Private Manual"]

    span = tracer.spans[0]
    assert span.name == "rag.suggestions"
    assert span.attributes["azure.search.index"] == "rag-index"
    assert span.attributes["rag.suggestions.top"] == 7
    assert span.attributes["rag.suggestions.raw_hit_count"] == 1
    assert span.attributes["rag.suggestions.result_count"] == 1
    assert span.attributes["rag.suggestions.outcome"] == "success"
    assert span.attributes["rag.suggestions.duration_ms"] >= 0
    assert set(span.attributes) == {
        "azure.search.index",
        "rag.suggestions.top",
        "rag.suggestions.raw_hit_count",
        "rag.suggestions.result_count",
        "rag.suggestions.outcome",
        "rag.suggestions.duration_ms",
    }
    assert "user-a" not in repr(span.attributes)
    assert "Private Manual" not in repr(span.attributes)


def test_list_visible_titles_records_error_without_sensitive_telemetry(monkeypatch):
    import pytest

    class FailingSession:
        def post(self, *_args, **_kwargs):
            raise RuntimeError("search failed")

    tracer = CapturingTracer()
    monkeypatch.setattr("azure_rag.rag.tracer", tracer)
    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=FailingSession(),
    )

    with pytest.raises(RuntimeError, match="search failed"):
        service.list_visible_titles(user_id="user-a")

    span = tracer.spans[0]
    assert span.attributes["rag.suggestions.raw_hit_count"] == 0
    assert span.attributes["rag.suggestions.result_count"] == 0
    assert span.attributes["rag.suggestions.outcome"] == "error"
    assert span.exceptions
    assert "user-a" not in repr(span.attributes)


def test_list_visible_titles_rejects_malformed_search_responses(monkeypatch):
    import pytest

    class MalformedResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class MalformedSession:
        def __init__(self, payload):
            self.payload = payload

        def post(self, *_args, **_kwargs):
            return MalformedResponse(self.payload)

    for payload in ({"value": "secret-title"}, ["secret-title"]):
        tracer = CapturingTracer()
        monkeypatch.setattr("azure_rag.rag.tracer", tracer)
        service = RagService(
            config(),
            credential=FakeCredential(),
            openai_client=FakeOpenAIClient(),
            session=MalformedSession(payload),
        )

        with pytest.raises(ValueError, match="^invalid Azure Search response$") as error:
            service.list_visible_titles(user_id="user-a")

        span = tracer.spans[0]
        assert str(error.value) == "invalid Azure Search response"
        assert span.attributes["rag.suggestions.outcome"] == "error"
        assert span.exceptions == [error.value]
        assert "secret-title" not in repr(span.attributes)


def test_rag_service_uses_injected_openai_client_and_search_bearer_token():
    credential = FakeCredential()
    session = FakeSession()
    openai_client = FakeOpenAIClient()
    service = RagService(config(), credential=credential, openai_client=openai_client, session=session)

    chunks = service.retrieve("question", top=3, user_id="user-a")

    assert service.openai is openai_client
    assert chunks[0].title == "doc"
    assert chunks[0].caption == "caption text"
    _, request = session.calls[0]
    assert request["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer search-token",
    }
    assert "api-key" not in request["headers"]
    assert credential.scopes == [(AZURE_SEARCH_SCOPE,)]

    service.close()

    assert credential.closed is False
    assert openai_client.closed is False


def test_rag_service_constructs_v1_openai_client_with_token_provider(monkeypatch):
    captured = {}
    credential = FakeCredential()

    monkeypatch.setattr("azure_rag.rag.openai_token_provider", lambda value: "token-provider")
    monkeypatch.setattr("azure_rag.rag.OpenAI", lambda **kwargs: captured.update(kwargs) or object())

    RagService(config(), credential=credential, session=FakeSession())

    assert captured == {
        "base_url": "https://example.openai.azure.com/openai/v1/",
        "api_key": "token-provider",
    }


def test_rag_service_closes_only_internally_created_resources(monkeypatch):
    credential = FakeCredential()
    openai_client = FakeOpenAIClient()
    monkeypatch.setattr("azure_rag.rag.default_credential", lambda: credential)
    monkeypatch.setattr("azure_rag.rag.OpenAI", lambda **kwargs: openai_client)

    service = RagService(config(), session=FakeSession())
    service.close()

    assert openai_client.closed is True
    assert credential.closed is True


def test_rag_service_closes_owned_credential_even_if_owned_client_close_fails(monkeypatch):
    credential = FakeCredential()

    class BrokenClient:
        def close(self):
            raise RuntimeError("close failed")

    monkeypatch.setattr("azure_rag.rag.default_credential", lambda: credential)
    monkeypatch.setattr("azure_rag.rag.OpenAI", lambda **kwargs: BrokenClient())

    service = RagService(config(), session=FakeSession())

    import pytest

    with pytest.raises(RuntimeError, match="close failed"):
        service.close()
    assert credential.closed is True


def test_rag_service_closes_owned_credential_if_client_construction_fails(monkeypatch):
    credential = FakeCredential()
    monkeypatch.setattr("azure_rag.rag.default_credential", lambda: credential)

    def fail_client(**kwargs):
        raise RuntimeError("client failed")

    monkeypatch.setattr("azure_rag.rag.OpenAI", fail_client)

    import pytest

    with pytest.raises(RuntimeError, match="client failed"):
        RagService(config(), session=FakeSession())

    assert credential.closed is True


def test_source_label_falls_back_to_source_filename_when_title_missing():
    label = source_label(
        RetrievedChunk(
            title="",
            chunk="text",
            source_path="/sample-docs/product-manual.pdf",
            score=2.4,
        )
    )
    assert label == "product-manual.pdf"


def test_retrieve_filters_out_low_scoring_chunks():
    class FilterResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "value": [
                    {
                        "title": "high",
                        "chunk": "keep",
                        "source_path": "high.md",
                        "@search.rerankerScore": 2.6,
                    },
                    {
                        "title": "low",
                        "chunk": "drop",
                        "source_path": "low.md",
                        "@search.rerankerScore": 1.8,
                    },
                    {
                        "title": "none",
                        "chunk": "drop",
                        "source_path": "none.md",
                    },
                ]
            }

    class FilterSession:
        def post(self, *_args, **_kwargs):
            return FilterResponse()

    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=FilterSession(),
    )
    chunks = service.retrieve("security", user_id="user-a")

    assert len(chunks) == 1
    assert chunks[0].source_path == "high.md"


def test_retrieve_applies_source_title_filter():
    class FilterResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": []}

    class FilterSession:
        def __init__(self):
            self.calls = []

        def post(self, _url, **kwargs):
            self.calls.append(kwargs)
            return FilterResponse()

    session = FilterSession()
    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=session,
    )
    service.retrieve("battery capacity", user_id="user-a", source="Tesla Powerwall")

    assert session.calls[0]["json"]["filter"] == "(user_id eq 'user-a' or user_id eq null) and search.ismatch('Tesla Powerwall', 'title')"


def test_retrieve_escapes_single_quotes_in_source_filter():
    class FilterResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"value": []}

    class FilterSession:
        def __init__(self):
            self.calls = []

        def post(self, _url, **kwargs):
            self.calls.append(kwargs)
            return FilterResponse()

    session = FilterSession()
    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=session,
    )
    service.retrieve("warranty", user_id="user-a", source="Bob's Manual")

    assert session.calls[0]["json"]["filter"] == "(user_id eq 'user-a' or user_id eq null) and search.ismatch('Bob''s Manual', 'title')"


def test_retrieve_rejects_invalid_user_id():
    import pytest

    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=FakeSession(),
    )
    with pytest.raises(ValueError, match="invalid user id"):
        service.retrieve("security", user_id="bad'id")


def test_retrieve_always_applies_user_isolation_filter():
    session = FakeSession()
    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=session,
    )
    service.retrieve("security", user_id="user-a")

    assert session.calls[0][1]["json"]["filter"] == "(user_id eq 'user-a' or user_id eq null)"


def test_retrieve_records_question_context_scores_and_duration(monkeypatch):
    tracer = CapturingTracer()
    monkeypatch.setattr("azure_rag.rag.tracer", tracer)
    runs = []

    def fake_start_langsmith_run(**kwargs):
        runs.append({"started": kwargs})
        return FakeLangSmithRun(runs)

    monkeypatch.setattr("azure_rag.rag.start_langsmith_run", fake_start_langsmith_run)
    service = RagService(
        config(),
        credential=FakeCredential(),
        openai_client=FakeOpenAIClient(),
        session=FakeSession(),
    )

    service.retrieve("security", top=3, user_id="user-a")

    span = tracer.spans[0]
    assert span.name == "rag.retrieve"
    assert span.attributes["rag.question"] == "security"
    assert span.attributes["azure.search.index"] == "rag-index"
    assert span.attributes["rag.retrieval.top"] == 3
    assert span.attributes["rag.retrieval.result_count"] == 1
    assert "doc.md" in span.attributes["rag.retrieval.context"]
    assert "2.5" in span.attributes["rag.retrieval.context"]
    assert span.attributes["rag.retrieval.duration_ms"] >= 0
    assert runs[0]["started"]["name"] == "Retrieve Context"
    assert runs[0]["started"]["run_type"] == "retriever"
    assert runs[0]["started"]["inputs"] == {"question": "security", "top": 3}
    assert runs[1]["ended"]["outputs"]["result_count"] == 1
    assert runs[1]["ended"]["outputs"]["chunks"][0]["source_path"] == "doc.md"
