from dataclasses import replace

from fastapi.testclient import TestClient

from azure_rag.api import create_app
from azure_rag.config import AppConfig


def config() -> AppConfig:
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
    def __init__(self, app_config: AppConfig | None = None):
        self.config = app_config or config()
        self.credential = object()
        self.session = object()
        self.openai = object()
        self.calls: list[list[dict[str, str]]] = []
        self.error: Exception | None = None

    def close(self):
        pass

    def suggest_followups(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return [
            {"title": "One", "message": "Question one?"},
            {"title": "Two", "message": "Question two?"},
            {"title": "Three", "message": "Question three?"},
            {"title": "Four", "message": "Question four?"},
        ]


def test_discussion_suggestions_calls_model_service_once_and_caps_results():
    rag = FakeRagService()
    app = create_app(config=config(), rag_service=rag, register_agui=False)

    with TestClient(app) as client:
        response = client.post(
            "/discussion/suggestions",
            headers={"X-RAG-User-ID": "user-a"},
            json={"messages": [{"role": "user", "content": "Question"}]},
        )

    assert response.status_code == 200
    assert len(response.json()) == 3
    assert rag.calls == [[{"role": "user", "content": "Question"}]]


def test_discussion_suggestions_returns_empty_after_one_failure():
    rag = FakeRagService()
    rag.error = TimeoutError("secret upstream details")
    app = create_app(config=config(), rag_service=rag, register_agui=False)

    with TestClient(app) as client:
        response = client.post(
            "/discussion/suggestions",
            headers={"X-RAG-User-ID": "user-a"},
            json={"messages": [{"role": "user", "content": "Question"}]},
        )

    assert response.status_code == 200
    assert response.json() == []
    assert len(rag.calls) == 1


def test_discussion_suggestions_requires_identity_without_calling_service():
    app_config = replace(config(), session_local_user_id=None)
    rag = FakeRagService(app_config)
    app = create_app(config=app_config, rag_service=rag, register_agui=False)

    with TestClient(app) as client:
        response = client.post(
            "/discussion/suggestions",
            json={"messages": [{"role": "user", "content": "Question"}]},
        )

    assert response.status_code == 401
    assert rag.calls == []
