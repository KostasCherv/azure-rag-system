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
        self.closed = False

    def get_token(self, *scopes):
        self.scopes.append(scopes)
        return type("Token", (), {"token": "search-token"})()

    def close(self):
        self.closed = True


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
        def close(self):
            captured["service_closed"] = True

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
    assert captured["service_closed"] is True
    assert credential.closed is False


def test_upload_includes_markdown_and_pdf_with_content_types(tmp_path: Path):
    (tmp_path / "sample.md").write_text("hello", encoding="utf-8")
    (tmp_path / "manual.PDF").write_bytes(b"%PDF-1.7")
    (tmp_path / "notes.txt").write_text("skip", encoding="utf-8")
    uploads = {}

    class Blob:
        def __init__(self, name):
            self.name = name

        def upload_blob(self, data, **kwargs):
            uploads[self.name] = (data, kwargs["content_settings"].content_type)

    class Service:
        def get_container_client(self, name):
            return type(
                "Container",
                (),
                {
                    "create_container": lambda self: None,
                    "get_blob_client": lambda self, name: Blob(name),
                },
            )()

    assert search_pipeline.upload_sample_docs(config(), tmp_path, blob_service_client=Service()) == [
        "manual.PDF",
        "sample.md",
    ]
    assert uploads == {
        "manual.PDF": (b"%PDF-1.7", "application/pdf"),
        "sample.md": (b"hello", "text/markdown; charset=utf-8"),
    }


def test_upload_does_not_close_injected_blob_client_or_credential(tmp_path: Path):
    (tmp_path / "sample.md").write_text("hello", encoding="utf-8")
    credential = FakeCredential()

    class Blob:
        def upload_blob(self, *args, **kwargs):
            pass

    class Service:
        closed = False

        def get_container_client(self, name):
            return type(
                "Container",
                (),
                {
                    "create_container": lambda self: None,
                    "get_blob_client": lambda self, name: Blob(),
                },
            )()

        def close(self):
            self.closed = True

    service = Service()
    search_pipeline.upload_sample_docs(
        config(), tmp_path, credential=credential, blob_service_client=service
    )

    assert service.closed is False
    assert credential.closed is False


def test_upload_closes_owned_blob_client_and_credential_on_error(monkeypatch, tmp_path: Path):
    (tmp_path / "sample.md").write_text("hello", encoding="utf-8")
    credential = FakeCredential()
    closed = {"blob": False}

    class Blob:
        def upload_blob(self, *args, **kwargs):
            raise RuntimeError("upload failed")

    class Service:
        def get_container_client(self, name):
            return type(
                "Container",
                (),
                {
                    "create_container": lambda self: None,
                    "get_blob_client": lambda self, name: Blob(),
                },
            )()

        def close(self):
            closed["blob"] = True

    monkeypatch.setattr(search_pipeline, "default_credential", lambda: credential)
    monkeypatch.setattr(search_pipeline, "BlobServiceClient", lambda **kwargs: Service())

    import pytest

    with pytest.raises(RuntimeError, match="upload failed"):
        search_pipeline.upload_sample_docs(config(), tmp_path)

    assert closed["blob"] is True
    assert credential.closed is True


def test_upload_closes_owned_credential_if_blob_client_construction_fails(monkeypatch):
    credential = FakeCredential()
    monkeypatch.setattr(search_pipeline, "default_credential", lambda: credential)

    def fail_client(**kwargs):
        raise RuntimeError("client failed")

    monkeypatch.setattr(search_pipeline, "BlobServiceClient", fail_client)

    import pytest

    with pytest.raises(RuntimeError, match="client failed"):
        search_pipeline.upload_sample_docs(config())

    assert credential.closed is True


def test_search_helper_closes_owned_credential_on_request_error(monkeypatch):
    credential = FakeCredential()

    class BrokenSession:
        def request(self, *args, **kwargs):
            raise RuntimeError("request failed")

    monkeypatch.setattr(search_pipeline, "default_credential", lambda: credential)

    import pytest

    with pytest.raises(RuntimeError, match="request failed"):
        search_pipeline.create_or_update_index(config(), session=BrokenSession())

    assert credential.closed is True


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


def test_index_and_skillset_carry_user_id_for_isolation():
    credential = FakeCredential()
    session = FakeSession()
    cfg = config()

    search_pipeline.create_or_update_index(cfg, credential=credential, session=session)
    search_pipeline.create_or_update_skillset(cfg, credential=credential, session=session)

    index, skillset = [call[2]["json"] for call in session.calls]
    user_id_field = next(field for field in index["fields"] if field["name"] == "user_id")
    assert user_id_field["filterable"] is True
    assert user_id_field["retrievable"] is False
    assert user_id_field["searchable"] is False
    mappings = skillset["indexProjections"]["selectors"][0]["mappings"]
    assert {"name": "user_id", "source": "/document/userId"} in mappings


def test_get_indexer_status_requests_indexer_status_endpoint():
    credential = FakeCredential()
    session = FakeSession()
    cfg = config()

    result = search_pipeline.get_indexer_status(cfg, credential=credential, session=session)

    assert result == {}
    method, url, _ = session.calls[0]
    assert method == "GET"
    assert f"/indexers/{cfg.indexer_name}/status" in url


def test_list_documents_scopes_to_user_prefix_and_strips_it():
    class Blob:
        def __init__(self, name, size, last_modified):
            self.name = name
            self.size = size
            self.last_modified = last_modified

    class Container:
        def list_blobs(self, name_starts_with=None):
            from datetime import datetime, timezone

            assert name_starts_with == "user-a/"
            return [
                Blob("user-a/guide.md", 12, datetime(2026, 1, 1, tzinfo=timezone.utc)),
                Blob("user-a/notes.txt", 4, None),
                Blob("user-a/manual.PDF", 99, None),
            ]

    class Service:
        def get_container_client(self, name):
            assert name == "docs"
            return Container()

    documents = search_pipeline.list_documents(config(), user_id="user-a", blob_service_client=Service())

    assert documents == [
        {"name": "guide.md", "size": 12, "last_modified": "2026-01-01T00:00:00+00:00"},
        {"name": "manual.PDF", "size": 99, "last_modified": None},
    ]


def test_upload_document_prefixes_blob_and_stamps_user_metadata():
    uploads = {}

    class Blob:
        def upload_blob(self, data, **kwargs):
            uploads["data"] = data
            uploads["content_type"] = kwargs["content_settings"].content_type
            uploads["metadata"] = kwargs["metadata"]

    class Container:
        def create_container(self):
            pass

        def get_blob_client(self, name):
            uploads["name"] = name
            return Blob()

    class Service:
        def get_container_client(self, name):
            return Container()

    uploaded = search_pipeline.upload_document(
        config(), "sample.md", b"hello", user_id="user-a", blob_service_client=Service()
    )

    assert uploaded == "sample.md"
    assert uploads == {
        "name": "user-a/sample.md",
        "data": b"hello",
        "content_type": "text/markdown; charset=utf-8",
        "metadata": {"userId": "user-a"},
    }


def test_upload_document_rejects_unsupported_extension():
    import pytest

    with pytest.raises(ValueError, match="unsupported document type"):
        search_pipeline.upload_document(
            config(), "notes.txt", b"hello", user_id="user-a", blob_service_client=object()
        )
