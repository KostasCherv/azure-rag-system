from azure_rag.config import AppConfig
from azure_rag.search_pipeline import _escape_odata_string, delete_index_documents_by_title


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


def test_escape_odata_string_doubles_single_quotes():
    assert _escape_odata_string("owner's manual.pdf") == "owner''s manual.pdf"


def test_delete_index_documents_by_title_loops_until_no_hits(monkeypatch):
    calls = {"search": 0, "delete": 0}

    def fake_request(cfg, method, path, *, credential, session, timeout=60, **kwargs):
        if method == "POST" and path.endswith("/docs/search"):
            calls["search"] += 1
            assert kwargs["json"]["filter"] == "title eq 'guide.md' and user_id eq 'user-a'"
            if calls["search"] == 1:
                return {"value": [{"document_id": "chunk-1"}, {"document_id": "chunk-2"}]}
            return {"value": []}
        if method == "POST" and path.endswith("/docs/index"):
            calls["delete"] += 1
            assert kwargs["json"] == {
                "value": [
                    {"@search.action": "delete", "document_id": "chunk-1"},
                    {"@search.action": "delete", "document_id": "chunk-2"},
                ]
            }
            return {}
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr("azure_rag.search_pipeline._request", fake_request)

    deleted = delete_index_documents_by_title(
        config(), "guide.md", user_id="user-a", credential=object(), session=object()
    )
    assert deleted == 2
    assert calls["search"] == 2
    assert calls["delete"] == 1
