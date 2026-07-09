from __future__ import annotations

import json
from contextvars import ContextVar
from time import perf_counter
from typing import Annotated, Any

from agent_framework import Agent, AgentMiddleware, ChatMiddleware
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

from .auth import openai_token_provider
from .config import AppConfig
from .rag import RagService, source_label
from .telemetry import start_langsmith_run, tracer

AGENT_INSTRUCTIONS = """
You are a document assistant backed by Azure AI Search.

Use the search_docs tool for questions about the indexed documents. The tool
returns JSON with context for you and citations for the UI. Answer from the
context field and cite with [1], [2], etc. Do not mention internal source
filenames or retrieval scores in user-facing answers.

Use inline citations in the answer body. Every factual claim based on retrieved
documents should include the relevant citation marker, such as [1], in the same
sentence. Do not collect citations only at the end.

After search_docs returns results, answer from those results. Do not repeat the
same search query in the same turn. If results are imperfect, answer with the
relevant parts you found and say what is missing.

For greetings and capability questions, explain that you can answer questions
from the indexed documents. Do not say the context is empty.

For personal or conversational details already shared in the chat history
(for example the user's name), answer from history and do not call search_docs.

When the user scopes a question to a specific document or product (for example
"in the ecobee manual" or "for the Tesla Powerwall"), pass that name in the
source parameter of search_docs so retrieval is limited to matching titles.
""".strip()

_model_call_count: ContextVar[int] = ContextVar("model_call_count", default=0)
_search_queries: ContextVar[set[tuple[str, int]] | None] = ContextVar(
    "search_queries",
    default=None,
)


def text_value(value: Any) -> str:
    text = getattr(value, "text", "")
    return text if isinstance(text, str) else str(value)


def item_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def text_content(value: Any) -> str:
    if item_value(value, "type") != "text":
        return ""
    text = item_value(value, "text", "")
    return text if isinstance(text, str) else ""


def final_answer_text(value: Any) -> str:
    messages = item_value(value, "messages")
    if messages is None and hasattr(value, "to_dict"):
        messages = value.to_dict().get("messages")
    for message in reversed(messages or []):
        if str(item_value(message, "role", "")).lower() != "assistant":
            continue
        answer = "".join(
            text_content(content)
            for content in item_value(message, "contents", [])
        ).strip()
        if answer and not answer.startswith("["):
            return answer
    return text_value(value)


def trace_payload(value: Any) -> Any:
    if value is None:
        return ""
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list | tuple):
        return [trace_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: trace_payload(item) for key, item in value.items()}
    text = getattr(value, "text", None)
    if isinstance(text, str) and text:
        return text
    return str(value)


def latest_user_message(messages: Any) -> str:
    for message in reversed(list(messages)):
        role = getattr(message, "role", None)
        if str(role).lower().endswith("user"):
            return text_value(message)
    return text_value(messages[-1]) if messages else ""


def reset_model_call_count(token: Any) -> None:
    try:
        _model_call_count.reset(token)
    except ValueError:
        _model_call_count.set(0)


def reset_search_queries(token: Any) -> None:
    try:
        _search_queries.reset(token)
    except ValueError:
        _search_queries.set(None)


class ModelTelemetryMiddleware(ChatMiddleware):
    def __init__(self, deployment: str):
        self.deployment = deployment

    def record_model_span(
        self,
        *,
        name: str,
        model_input: Any,
        started: float,
        output: Any = None,
        error: Exception | None = None,
    ) -> None:
        with tracer.start_as_current_span("rag.model.response") as span:
            span.set_attribute("gen_ai.system", "azure_openai")
            span.set_attribute("gen_ai.request.model", self.deployment)
            span.set_attribute("azure.openai.deployment", self.deployment)
            span.set_attribute("rag.model.input", str(model_input))
            if output is not None:
                span.set_attribute("rag.model.output", str(output))
            span.set_attribute("rag.model.duration_ms", (perf_counter() - started) * 1000)
            if error is not None:
                span.record_exception(error)

    async def process(self, context: Any, call_next: Any) -> None:
        started = perf_counter()
        model_input = trace_payload(context.messages)
        call_number = _model_call_count.get() + 1
        _model_call_count.set(call_number)
        name = (
            "Model Call: tool selection"
            if call_number == 1
            else f"Model Call {call_number}: answer attempt"
        )
        run = start_langsmith_run(
            name=name,
            run_type="llm",
            inputs={"messages": model_input},
            metadata={
                "ls_provider": "azure_openai",
                "ls_model_name": self.deployment,
                "azure.openai.deployment": self.deployment,
                "model_call_number": call_number,
            },
        )

        async def record_response(response: Any) -> Any:
            output = trace_payload(response)
            self.record_model_span(
                name=name,
                model_input=model_input,
                output=output,
                started=started,
            )
            if run is not None:
                run.end(outputs={"output": output})
            return response

        if context.stream:
            context.stream_result_hooks.append(record_response)
            try:
                await call_next()
            except Exception as error:
                self.record_model_span(
                    name=name,
                    model_input=model_input,
                    started=started,
                    error=error,
                )
                if run is not None:
                    run.end(error=error, traceback=error.__traceback__)
                raise
            return

        try:
            await call_next()
            output = trace_payload(context.result)
            self.record_model_span(
                name=name,
                model_input=model_input,
                output=output,
                started=started,
            )
        except Exception as error:
            self.record_model_span(
                name=name,
                model_input=model_input,
                started=started,
                error=error,
            )
            if run is not None:
                run.end(error=error, traceback=error.__traceback__)
            raise
        if run is not None:
            run.end(outputs={"output": output})


class LangSmithRunTelemetryMiddleware(AgentMiddleware):
    def __init__(self, deployment: str):
        self.deployment = deployment

    async def process(self, context: Any, call_next: Any) -> None:
        token = _model_call_count.set(0)
        search_token = _search_queries.set(set())
        run = start_langsmith_run(
            name="RAG Request",
            run_type="chain",
            inputs={
                "question": latest_user_message(context.messages),
                "message_count": len(context.messages),
            },
            metadata={
                "app.agent.name": "azure-rag-agent",
                "ls_provider": "azure_openai",
                "ls_model_name": self.deployment,
                "azure.openai.deployment": self.deployment,
            },
        )
        if run is None:
            try:
                await call_next()
            finally:
                reset_model_call_count(token)
                reset_search_queries(search_token)
            return

        async def end_stream(response: Any) -> Any:
            run.end(outputs={"answer": final_answer_text(response)})
            reset_model_call_count(token)
            reset_search_queries(search_token)
            return response

        try:
            if context.stream:
                context.stream_result_hooks.append(end_stream)
                await call_next()
            else:
                await call_next()
                run.end(
                    outputs={
                        "answer": final_answer_text(context.result)
                        if context.result is not None
                        else ""
                    }
                )
                reset_model_call_count(token)
                reset_search_queries(search_token)
        except Exception as error:
            run.end(error=error, traceback=error.__traceback__)
            reset_model_call_count(token)
            reset_search_queries(search_token)
            raise


def format_search_results(chunks: list[Any], *, retrieval_ms: int | None = None) -> str:
    if not chunks:
        payload: dict[str, Any] = {
            "context": "No relevant documents found above the configured score threshold.",
            "citations": [],
        }
        if retrieval_ms is not None:
            payload["retrieval_ms"] = retrieval_ms
        return json.dumps(payload)
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        content = getattr(chunk, "caption", "") or getattr(chunk, "chunk", "")
        lines.append(f"[{index}]\n{content}")
        citations.append(
            {
                "id": index,
                "document": source_label(chunk),
                "chunk": content,
            }
        )
    payload = {"context": "\n\n".join(lines), "citations": citations}
    if retrieval_ms is not None:
        payload["retrieval_ms"] = retrieval_ms
    return json.dumps(payload)


def create_search_docs_tool(rag: RagService):
    def search_docs(
        question: Annotated[str, Field(description="The knowledge-base question to search for.")],
        top: Annotated[int, Field(description="Maximum number of chunks to return.", ge=1, le=10)] = 5,
        source: Annotated[
            str | None,
            Field(
                description="Optional document or product name to scope search to (matched against title).",
                default=None,
            ),
        ] = None,
    ) -> str:
        """Search indexed documents in Azure AI Search and return relevant chunks."""
        with tracer.start_as_current_span("rag.search_docs_tool") as span:
            span.set_attribute("rag.question", question)
            span.set_attribute("rag.retrieval.top", top)
            if source:
                span.set_attribute("rag.retrieval.source", source)
            query_key = (question.strip().casefold(), top, (source or "").strip().casefold())
            seen_queries = _search_queries.get()
            tool_inputs: dict[str, Any] = {"question": question, "top": top}
            if source:
                tool_inputs["source"] = source
            run = start_langsmith_run(
                name="Search Docs Tool",
                run_type="tool",
                inputs=tool_inputs,
                metadata={"tool": "search_docs"},
            )
            try:
                if seen_queries is not None and query_key in seen_queries:
                    result = (
                        "This exact search was already performed in this turn. "
                        "Use the earlier search_docs results to answer the user."
                    )
                    span.set_attribute("rag.retrieval.result_count", 0)
                    span.set_attribute("rag.tool.output", result)
                    if run is not None:
                        run.end(outputs={"context": result, "result_count": 0})
                    return result
                if seen_queries is not None:
                    seen_queries.add(query_key)
                retrieval_started = perf_counter()
                chunks = rag.retrieve(question, top=top, source=source)
                retrieval_ms = round((perf_counter() - retrieval_started) * 1000)
                result = format_search_results(chunks, retrieval_ms=retrieval_ms)
                span.set_attribute("rag.retrieval.result_count", len(chunks))
                span.set_attribute("rag.tool.output", result)
                if run is not None:
                    run.end(outputs={"context": result, "result_count": len(chunks)})
                return result
            except Exception as error:
                span.record_exception(error)
                if run is not None:
                    run.end(error=error, traceback=error.__traceback__)
                raise

    return search_docs


def create_chat_client(config: AppConfig, rag: RagService) -> OpenAIChatClient:
    return OpenAIChatClient(
        model=config.azure_openai_chat_deployment,
        azure_endpoint=config.openai_resource_url,
        api_key=openai_token_provider(rag.credential),
    )


def create_rag_agent(config: AppConfig, rag: RagService) -> Agent:
    with tracer.start_as_current_span("rag.agent.create") as span:
        span.set_attribute("gen_ai.system", "azure_openai")
        span.set_attribute("gen_ai.request.model", config.azure_openai_chat_deployment)
        span.set_attribute("azure.openai.deployment", config.azure_openai_chat_deployment)
        span.set_attribute("app.agent.name", "azure-rag-agent")
        return Agent(
            name="azure-rag-agent",
            instructions=AGENT_INSTRUCTIONS,
            client=create_chat_client(config, rag),
            tools=[create_search_docs_tool(rag)],
            default_options=config.agent_default_options(),
            middleware=[
                LangSmithRunTelemetryMiddleware(config.azure_openai_chat_deployment),
                ModelTelemetryMiddleware(config.azure_openai_chat_deployment),
            ],
        )
