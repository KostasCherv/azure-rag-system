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
    app = create_app(config=config(), rag_service=service, register_agui=False)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert service.closed is False

    assert service.closed is False


def test_app_lifespan_closes_internally_created_rag_service(monkeypatch):
    service = FakeRagService()
    monkeypatch.setattr("azure_rag.api.RagService", lambda config: service)
    app = create_app(config=config(), register_agui=False)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert service.closed is False

    assert service.closed is True


def test_app_registers_agui_endpoint_with_agent_framework(monkeypatch):
    captured = {}

    def fake_add_endpoint(app, agent, path="/", **kwargs):
        captured["app"] = app
        captured["agent"] = agent
        captured["path"] = path

        @app.post(path)
        def agui_stub():
            return {"ok": True}

    monkeypatch.setattr("azure_rag.api.add_agent_framework_fastapi_endpoint", fake_add_endpoint)
    monkeypatch.setattr("azure_rag.api.create_rag_agent", lambda config, rag: {"name": "fake-agent"})

    service = FakeRagService()
    app = create_app(config=config(), rag_service=service, register_agui=True)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert captured["path"] == "/agui"
        assert captured["agent"] == {"name": "fake-agent"}
        assert client.post("/agui").status_code == 200


def test_app_lifespan_configures_telemetry_when_connection_string_exists(monkeypatch):
    captured = {}
    app_config = AppConfig(
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
        search_endpoint="https://example.search.windows.net",
        search_index="rag-index",
        storage_account_url="https://storage.blob.core.windows.net",
        storage_container="docs",
        storage_resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/storage",
        applicationinsights_connection_string="InstrumentationKey=abc",
    )

    def fake_configure(connection_string):
        captured["connection_string"] = connection_string
        return True

    monkeypatch.setattr("azure_rag.api.configure_telemetry", fake_configure)
    app = create_app(config=app_config, rag_service=FakeRagService(), register_agui=False)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert captured["connection_string"] == "InstrumentationKey=abc"
