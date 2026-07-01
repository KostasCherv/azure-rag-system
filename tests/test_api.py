from fastapi.testclient import TestClient

from azure_rag.api import create_app
from azure_rag.config import AppConfig


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
        self.closed = False

    def close(self):
        self.closed = True


def test_app_lifespan_does_not_close_injected_rag_service():
    service = FakeRagService()
    app = create_app(config=config(), rag_service=service)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert service.closed is False

    assert service.closed is False


def test_app_lifespan_closes_internally_created_rag_service(monkeypatch):
    service = FakeRagService()
    monkeypatch.setattr("azure_rag.api.RagService", lambda config: service)
    app = create_app(config=config())

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert service.closed is False

    assert service.closed is True
