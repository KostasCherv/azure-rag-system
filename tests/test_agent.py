from types import SimpleNamespace

from azure_rag.agent import create_rag_agent, create_search_docs_tool, format_search_results
from azure_rag.config import AppConfig
from azure_rag.rag import RetrievedChunk


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


def test_format_search_results_numbers_chunks():
    text = format_search_results(
        [
            RetrievedChunk(
                title="contoso-security.md",
                chunk="Data is encrypted at rest.",
                source_path="contoso-security.md",
                score=2.4,
            )
        ]
    )

    assert "[1] contoso-security.md" in text
    assert "(contoso-security.md)" not in text
    assert "Data is encrypted at rest." in text
    assert "score=2.4" in text


def test_format_search_results_empty_message():
    assert "No relevant documents" in format_search_results([])


def test_search_docs_tool_uses_rag_retrieve():
    class FakeRag:
        def retrieve(self, question, top=5):
            assert question == "security overview"
            assert top == 3
            return [
                RetrievedChunk(
                    title="contoso-security.md",
                    chunk="Encrypted at rest.",
                    source_path="contoso-security.md",
                    score=2.5,
                )
            ]

    tool = create_search_docs_tool(FakeRag())
    result = tool(question="security overview", top=3)

    assert "[1] contoso-security.md" in result
    assert "Encrypted at rest." in result


def test_create_rag_agent_registers_search_tool(monkeypatch):
    captured = {}

    class FakeClient:
        pass

    def fake_chat_client(config, rag):
        return FakeClient()

    monkeypatch.setattr("azure_rag.agent.create_chat_client", fake_chat_client)

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr("azure_rag.agent.Agent", fake_agent)

    agent = create_rag_agent(config(), SimpleNamespace(credential=object()))

    assert agent.name == "azure-rag-agent"
    assert "search_docs" in agent.instructions or "Contoso" in agent.instructions
    assert callable(captured["tools"][0])
    assert captured["tools"][0].__name__ == "search_docs"
