from pathlib import Path

from azure_rag.auth import AZURE_SEARCH_SCOPE
from azure_rag.config import AppConfig
from azure_rag import search_pipeline


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


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes):
        self.scopes.append(scopes)
        return type("Token", (), {"token": "search-token"})()


class FakeResponse:
    status_code = 200
    content = b"{}"
    text = "{}"

    def json(self):
        return {}


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse()


def test_search_management_request_uses_bearer_token():
    credential = FakeCredential()
    session = FakeSession()

    search_pipeline.create_or_update_index(config(), credential=credential, session=session)

    _, _, request = session.calls[0]
    assert request["headers"]["Authorization"] == "Bearer search-token"
    assert "api-key" not in request["headers"]
    assert credential.scopes == [(AZURE_SEARCH_SCOPE,)]


def test_upload_constructs_blob_client_with_account_url_and_credential(monkeypatch, tmp_path: Path):
    (tmp_path / "sample.md").write_text("hello", encoding="utf-8")
    credential = FakeCredential()
    captured = {}

    class Blob:
        def upload_blob(self, *args, **kwargs):
            captured["upload"] = (args, kwargs)

    class Container:
        def create_container(self):
            pass

        def get_blob_client(self, name):
            captured["blob_name"] = name
            return Blob()

    class Service:
        def get_container_client(self, name):
            captured["container"] = name
            return Container()

    def fake_blob_service(**kwargs):
        captured.update(kwargs)
        return Service()

    monkeypatch.setattr(search_pipeline, "BlobServiceClient", fake_blob_service)

    assert search_pipeline.upload_sample_docs(config(), tmp_path, credential=credential) == ["sample.md"]
    assert captured["account_url"] == "https://storage.blob.core.windows.net"
    assert captured["credential"] is credential
    assert captured["container"] == "docs"


def test_search_payloads_are_keyless_and_data_source_uses_resource_id():
    credential = FakeCredential()
    session = FakeSession()
    cfg = config()

    search_pipeline.create_or_update_index(cfg, credential=credential, session=session)
    search_pipeline.create_or_update_data_source(cfg, credential=credential, session=session)
    search_pipeline.create_or_update_skillset(cfg, credential=credential, session=session)

    payloads = [call[2]["json"] for call in session.calls]
    index, data_source, skillset = payloads
    vectorizer = index["vectorSearch"]["vectorizers"][0]["azureOpenAIParameters"]
    embedding_skill = skillset["skills"][1]

    assert "apiKey" not in vectorizer
    assert "authIdentity" not in vectorizer
    assert "apiKey" not in embedding_skill
    assert "authIdentity" not in embedding_skill
    assert data_source["credentials"] == {
        "connectionString": f"ResourceId={cfg.storage_resource_id};"
    }
