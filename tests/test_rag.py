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


def test_rag_service_uses_injected_openai_client_and_search_bearer_token():
    credential = FakeCredential()
    session = FakeSession()
    openai_client = FakeOpenAIClient()
    service = RagService(config(), credential=credential, openai_client=openai_client, session=session)

    chunks = service.retrieve("question", top=3)

    assert service.openai is openai_client
    assert chunks[0].title == "doc"
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
            source_path="/sample-docs/contoso-support.md",
            score=2.4,
        )
    )
    assert label == "contoso-support.md"


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
    chunks = service.retrieve("security")

    assert len(chunks) == 1
    assert chunks[0].source_path == "high.md"

