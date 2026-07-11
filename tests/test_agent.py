import json
from types import SimpleNamespace

import anyio
import azure_rag.agent as agent_module

from azure_rag.agent import (
    LangSmithRunTelemetryMiddleware,
    ModelTelemetryMiddleware,
    create_rag_agent,
    create_search_docs_tool,
    final_answer_text,
    format_search_results,
)
from azure_rag.config import AppConfig
from azure_rag.identity import current_user_id
from azure_rag.rag import RetrievedChunk

import pytest


@pytest.fixture(autouse=True)
def user_context():
    token = current_user_id.set("user-a")
    yield
    current_user_id.reset(token)


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


def test_format_search_results_numbers_chunks():
    text = format_search_results(
        [
            RetrievedChunk(
                title="product-manual.pdf",
                chunk="Long surrounding page text.",
                source_path="product-manual.pdf",
                score=2.4,
                caption="Data is encrypted at rest.",
            )
        ]
    )

    payload = json.loads(text)
    assert payload["context"] == "[1]\nData is encrypted at rest."
    assert payload["citations"] == [
        {
            "id": 1,
            "document": "product-manual.pdf",
            "chunk": "Data is encrypted at rest.",
        }
    ]
    assert "score" not in payload["citations"][0]
    assert "product-manual.pdf" not in payload["context"]
    assert "score=2.4" not in text


def test_format_search_results_includes_retrieval_ms():
    text = format_search_results(
        [
            RetrievedChunk(
                title="product-manual.pdf",
                chunk="Encrypted at rest.",
                source_path="product-manual.pdf",
                score=2.5,
            )
        ],
        retrieval_ms=320,
    )

    payload = json.loads(text)
    assert payload["retrieval_ms"] == 320
    assert isinstance(payload["retrieval_ms"], int)
    assert "score" not in text


def test_format_search_results_empty_message():
    assert "No relevant documents" in format_search_results([])


def test_search_docs_tool_uses_rag_retrieve():
    class FakeRag:
        def retrieve(self, question, top=5, *, user_id, source=None):
            assert question == "security overview"
            assert top == 3
            assert user_id == "user-a"
            assert source is None
            return [
                RetrievedChunk(
                    title="product-manual.pdf",
                    chunk="Encrypted at rest.",
                    source_path="product-manual.pdf",
                    score=2.5,
                )
            ]

    tool = create_search_docs_tool(FakeRag())
    result = tool(question="security overview", top=3)
    payload = json.loads(result)

    assert "[1]" in result
    assert "product-manual.pdf" not in payload["context"]
    assert "Encrypted at rest." in result
    assert isinstance(payload["retrieval_ms"], int)
    assert payload["retrieval_ms"] >= 0
    assert "score" not in payload["citations"][0]


def test_search_docs_tool_passes_source_to_retrieve():
    class FakeRag:
        def retrieve(self, question, top=5, *, user_id, source=None):
            assert question == "battery capacity"
            assert top == 5
            assert user_id == "user-a"
            assert source == "Tesla Powerwall"
            return [
                RetrievedChunk(
                    title="tesla-powerwall-3-owner-manual.pdf",
                    chunk="Battery capacity is 13.5 kWh.",
                    source_path="tesla-powerwall-3-owner-manual.pdf",
                    score=2.8,
                )
            ]

    tool = create_search_docs_tool(FakeRag())
    result = tool(question="battery capacity", source="Tesla Powerwall")

    payload = json.loads(result)
    assert "13.5 kWh" in payload["context"]


def test_final_answer_text_ignores_tool_context_messages():
    response = SimpleNamespace(
        text="[1] product-manual.pdf score=2.4\nraw context",
        messages=[
            SimpleNamespace(
                role="assistant",
                contents=[
                    SimpleNamespace(
                        type="text",
                        text="[1] product-manual.pdf score=2.4\nraw context",
                    )
                ],
            ),
            SimpleNamespace(
                role="assistant",
                contents=[
                    SimpleNamespace(
                        type="text", text="The product supports app control [1]."
                    )
                ],
            ),
        ],
    )

    assert final_answer_text(response) == "The product supports app control [1]."


def test_search_docs_tool_records_question_and_returned_context(monkeypatch):
    tracer = CapturingTracer()
    monkeypatch.setattr("azure_rag.agent.tracer", tracer)
    runs = []

    def fake_start_langsmith_run(**kwargs):
        runs.append({"started": kwargs})
        return FakeLangSmithRun(runs)

    monkeypatch.setattr("azure_rag.agent.start_langsmith_run", fake_start_langsmith_run)

    class FakeRag:
        def retrieve(self, question, top=5, *, user_id, source=None):
            return [
                RetrievedChunk(
                    title="product-manual.pdf",
                    chunk="Encrypted at rest.",
                    source_path="product-manual.pdf",
                    score=2.5,
                )
            ]

    tool = create_search_docs_tool(FakeRag())
    result = tool(question="security overview", top=3)

    span = tracer.spans[0]
    assert span.name == "rag.search_docs_tool"
    assert span.attributes["rag.question"] == "security overview"
    assert span.attributes["rag.retrieval.top"] == 3
    assert span.attributes["rag.retrieval.result_count"] == 1
    assert span.attributes["rag.tool.output"] == result
    assert runs[0]["started"]["name"] == "Search Docs Tool"
    assert runs[0]["started"]["run_type"] == "tool"
    assert runs[0]["started"]["inputs"] == {"question": "security overview", "top": 3}
    assert runs[1]["ended"] == {"outputs": {"context": result, "result_count": 1}}


def test_search_docs_tool_blocks_duplicate_query_in_same_turn(monkeypatch):
    class FakeRag:
        def __init__(self):
            self.calls = 0

        def retrieve(self, _question, top=5, *, user_id, source=None):
            self.calls += 1
            return [
                RetrievedChunk(
                    title="product-manual.pdf",
                    chunk="Product details.",
                    source_path="product-manual.pdf",
                    score=3.0,
                )
            ]

    monkeypatch.setattr("azure_rag.agent.start_langsmith_run", lambda **_kwargs: None)
    rag = FakeRag()
    tool = create_search_docs_tool(rag)
    token = agent_module._search_queries.set(set())
    try:
        first = tool(question="product information", top=5)
        second = tool(question="product information", top=5)
    finally:
        agent_module._search_queries.reset(token)

    assert "Product details." in first
    assert "already performed" in second
    assert rag.calls == 1


def test_search_docs_tool_fails_closed_without_user_identity(monkeypatch):
    class ExplodingRag:
        def retrieve(self, *args, **kwargs):
            raise AssertionError("retrieve must not run without a user identity")

    monkeypatch.setattr("azure_rag.agent.start_langsmith_run", lambda **_kwargs: None)
    tool = create_search_docs_tool(ExplodingRag())
    token = current_user_id.set(None)
    try:
        result = tool(question="anything")
    finally:
        current_user_id.reset(token)

    assert "No relevant documents" in result


def test_model_middleware_records_streamed_final_response(monkeypatch):
    tracer = CapturingTracer()
    monkeypatch.setattr("azure_rag.agent.tracer", tracer)
    runs = []

    def fake_start_langsmith_run(**kwargs):
        runs.append({"started": kwargs})
        return FakeLangSmithRun(runs)

    monkeypatch.setattr("azure_rag.agent.start_langsmith_run", fake_start_langsmith_run)
    middleware = ModelTelemetryMiddleware("chat")
    context = SimpleNamespace(
        messages=[SimpleNamespace(text="What is covered?")],
        stream=True,
        stream_result_hooks=[],
    )

    async def call_next():
        return None

    anyio.run(middleware.process, context, call_next)
    response = SimpleNamespace(text="Security is covered.", usage_details=None)
    returned = anyio.run(context.stream_result_hooks[0], response)

    span = tracer.spans[0]
    assert returned is response
    assert span.name == "rag.model.response"
    assert "What is covered?" in span.attributes["rag.model.input"]
    assert span.attributes["rag.model.output"] == "Security is covered."
    assert span.attributes["azure.openai.deployment"] == "chat"
    assert span.attributes["rag.model.duration_ms"] >= 0
    assert runs[0]["started"]["name"] == "Model Call: tool selection"
    assert runs[0]["started"]["run_type"] == "llm"
    assert runs[0]["started"]["inputs"] == {"messages": ["What is covered?"]}
    assert runs[0]["started"]["metadata"]["ls_model_name"] == "chat"
    assert runs[1]["ended"] == {"outputs": {"output": "Security is covered."}}


def test_langsmith_run_middleware_groups_streamed_user_query(monkeypatch):
    ended = []

    class FakeRun:
        def end(self, **kwargs):
            ended.append(kwargs)

    def fake_start_langsmith_run(**kwargs):
        ended.append({"started": kwargs})
        return FakeRun()

    monkeypatch.setattr("azure_rag.agent.start_langsmith_run", fake_start_langsmith_run)
    middleware = LangSmithRunTelemetryMiddleware("chat")
    context = SimpleNamespace(
        messages=[SimpleNamespace(text="What does the manual say about encryption?")],
        stream=True,
        stream_result_hooks=[],
    )

    async def call_next():
        return None

    anyio.run(middleware.process, context, call_next)
    response = SimpleNamespace(text="The manual says data is encrypted at rest.")
    returned = anyio.run(context.stream_result_hooks[0], response)

    assert returned is response
    assert ended[0]["started"]["name"] == "RAG Request"
    assert ended[0]["started"]["run_type"] == "chain"
    assert ended[0]["started"]["inputs"] == {
        "question": "What does the manual say about encryption?",
        "message_count": 1,
    }
    assert ended[1] == {
        "outputs": {"answer": "The manual says data is encrypted at rest."}
    }


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
    assert "search_docs" in agent.instructions
    assert "source parameter" in agent.instructions
    assert "indexed documents" in agent.instructions
    assert "Use inline citations in the answer body" in agent.instructions
    assert "Do not collect citations only at the end" in agent.instructions
    assert callable(captured["tools"][0])
    assert captured["tools"][0].__name__ == "search_docs"


def test_create_rag_agent_uses_completion_token_limit_for_gpt5(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "azure_rag.agent.create_chat_client",
        lambda config, rag: object(),
    )

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr("azure_rag.agent.Agent", fake_agent)

    gpt5_config = AppConfig(
        azure_openai_endpoint="https://example.openai.azure.com/openai/v1",
        azure_openai_chat_deployment="gpt-5-mini",
        azure_openai_embedding_deployment="embedding",
        search_endpoint="https://example.search.windows.net",
        search_index="rag-index",
        storage_account_url="https://storage.blob.core.windows.net",
        storage_container="docs",
        storage_resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/storage",
    )
    create_rag_agent(gpt5_config, SimpleNamespace(credential=object()))

    assert captured["default_options"] == {"max_tokens": 5000}


def test_create_chat_client_uses_credential_for_entra_auth(monkeypatch):
    captured = {}
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "azure_rag.agent.OpenAIChatClient",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(**kwargs),
    )
    agent_module.create_chat_client(config(), SimpleNamespace(credential=object()))

    assert callable(captured["credential"])
    assert captured["model"] == "chat"
    assert captured["azure_endpoint"] == "https://example.openai.azure.com"
    assert "api_key" not in captured


def test_create_chat_client_prefers_api_key_when_set(monkeypatch):
    captured = {}
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret-key")
    monkeypatch.setattr(
        "azure_rag.agent.OpenAIChatClient",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(**kwargs),
    )

    agent_module.create_chat_client(config(), SimpleNamespace(credential=object()))

    assert captured["api_key"] == "secret-key"
    assert "credential" not in captured
