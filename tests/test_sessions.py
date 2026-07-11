from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from azure_rag.api import create_app
from azure_rag.config import AppConfig
from azure_rag.sessions import MAX_TITLE_LENGTH, TTL_SECONDS, normalize_title, title_from_messages


class FakeRag:
    credential = object()
    openai = object()
    session = object()

    def close(self):
        pass


class FakeStore:
    def __init__(self):
        self.items = {}
        self.last_user = None

    def probe(self):
        pass

    def list(self, user_id, *, limit, before):
        self.last_user = user_id
        return {"items": [], "nextCursor": None}

    def create(self, user_id, requested_id=None):
        self.last_user = user_id
        item = {
            "id": str(requested_id or UUID("00000000-0000-4000-8000-000000000001")),
            "userId": user_id,
            "title": "New discussion",
            "messages": [],
            "messageCount": 0,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
            "ttl": TTL_SECONDS,
            "_etag": "one",
        }
        self.items[(user_id, item["id"])] = item
        return item

    def get(self, user_id, session_id):
        self.last_user = user_id
        return self.items[(user_id, str(session_id))]

    def update(self, user_id, session_id, messages, etag):
        item = self.get(user_id, session_id)
        item.update(messages=messages, messageCount=len(messages), _etag="two")
        return item

    def rename(self, user_id, session_id, title, etag):
        item = self.get(user_id, session_id)
        item.update(title=normalize_title(title), _etag="two")
        return item

    def delete(self, user_id, session_id):
        del self.items[(user_id, str(session_id))]


def config() -> AppConfig:
    return AppConfig(
        azure_openai_endpoint="https://openai.test",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embed",
        search_endpoint="https://search.test",
        search_index="docs",
        storage_account_url="https://storage.test",
        storage_container="docs",
        storage_resource_id="/storage",
    )


def test_title_normalization_and_default_title():
    assert normalize_title("  A   useful\nquestion  ") == "A useful question"
    assert len(normalize_title("x" * 100)) == MAX_TITLE_LENGTH
    assert title_from_messages([{"role": "assistant", "content": "ignore"}]) == "New discussion"
    assert title_from_messages([{"role": "user", "content": " First   question "}]) == "First question"


def test_session_api_uses_forwarded_user_and_preserves_messages():
    store = FakeStore()
    app = create_app(config=config(), rag_service=FakeRag(), session_store=store, register_agui=False)
    with TestClient(app) as client:
        created = client.post("/sessions", json={}, headers={"X-RAG-User-ID": "user-one"})
        assert created.status_code == 201
        session_id = created.json()["id"]
        assert "userId" not in created.json()
        saved = client.put(
            f"/sessions/{session_id}",
            json={"messages": [{"id": "m1", "role": "user", "content": "Hello"}]},
            headers={"X-RAG-User-ID": "user-one", "If-Match": "one"},
        )
        assert saved.status_code == 200
        assert saved.json()["messages"][0]["content"] == "Hello"
        assert store.last_user == "user-one"


def test_session_api_uses_local_identity_and_rejects_invalid_forwarded_identity():
    store = FakeStore()
    app = create_app(config=config(), rag_service=FakeRag(), session_store=store, register_agui=False)
    with TestClient(app) as client:
        assert client.get("/sessions").status_code == 200
        assert store.last_user == "local-development-user"
        assert client.get("/sessions", headers={"X-RAG-User-ID": "bad identity!"}).status_code == 401


def test_sessions_are_unavailable_when_cosmos_is_not_configured():
    app = create_app(config=config(), rag_service=FakeRag(), register_agui=False)
    with TestClient(app) as client:
        assert client.get("/sessions").status_code == 503
