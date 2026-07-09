from __future__ import annotations

from time import perf_counter
from typing import Annotated, Any

from agent_framework import Agent, ChatMiddleware
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

from .auth import openai_token_provider
from .config import AppConfig
from .rag import RagService, source_label
from .telemetry import tracer

AGENT_INSTRUCTIONS = """
You are a Contoso document assistant backed by Azure AI Search.

Use the search_docs tool for knowledge-base questions about Contoso support,
product, or security. Cite tool results with [1], [2], etc. and mention source
titles when helpful.

For greetings and capability questions, explain that you can answer Contoso
support, product, and security questions from the indexed docs. Do not say the
context is empty.

For personal or conversational details already shared in the chat history
(for example the user's name), answer from history and do not call search_docs.
""".strip()


def text_value(value: Any) -> str:
    text = getattr(value, "text", "")
    return text if isinstance(text, str) else str(value)


class ModelTelemetryMiddleware(ChatMiddleware):
    def __init__(self, deployment: str):
        self.deployment = deployment

    def record_model_span(
        self,
        *,
        model_input: str,
        started: float,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        with tracer.start_as_current_span("rag.model.response") as span:
            span.set_attribute("gen_ai.system", "azure_openai")
            span.set_attribute("gen_ai.request.model", self.deployment)
            span.set_attribute("azure.openai.deployment", self.deployment)
            span.set_attribute("rag.model.input", model_input)
            if output is not None:
                span.set_attribute("rag.model.output", output)
            span.set_attribute("rag.model.duration_ms", (perf_counter() - started) * 1000)
            if error is not None:
                span.record_exception(error)

    async def process(self, context: Any, call_next: Any) -> None:
        started = perf_counter()
        model_input = "\n".join(text_value(message) for message in context.messages)

        async def record_response(response: Any) -> Any:
            self.record_model_span(
                model_input=model_input,
                output=text_value(response),
                started=started,
            )
            return response

        if context.stream:
            context.stream_result_hooks.append(record_response)
            try:
                await call_next()
            except Exception as error:
                self.record_model_span(model_input=model_input, started=started, error=error)
                raise
            return

        try:
            await call_next()
            self.record_model_span(
                model_input=model_input,
                output=text_value(context.result) if context.result is not None else None,
                started=started,
            )
        except Exception as error:
            self.record_model_span(model_input=model_input, started=started, error=error)
            raise


def format_search_results(chunks: list[Any]) -> str:
    if not chunks:
        return "No relevant documents found above the configured score threshold."
    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        content = getattr(chunk, "chunk", "")
        score = getattr(chunk, "score", None)
        score_text = f" score={score}" if score is not None else ""
        lines.append(f"[{index}] {source_label(chunk)}{score_text}\n{content}")
    return "\n\n".join(lines)


def create_search_docs_tool(rag: RagService):
    def search_docs(
        question: Annotated[str, Field(description="The knowledge-base question to search for.")],
        top: Annotated[int, Field(description="Maximum number of chunks to return.", ge=1, le=10)] = 5,
    ) -> str:
        """Search Contoso indexed documents in Azure AI Search and return relevant chunks."""
        with tracer.start_as_current_span("rag.search_docs_tool") as span:
            span.set_attribute("rag.question", question)
            span.set_attribute("rag.retrieval.top", top)
            try:
                chunks = rag.retrieve(question, top=top)
                result = format_search_results(chunks)
                span.set_attribute("rag.retrieval.result_count", len(chunks))
                span.set_attribute("rag.tool.output", result)
                return result
            except Exception as error:
                span.record_exception(error)
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
            middleware=[ModelTelemetryMiddleware(config.azure_openai_chat_deployment)],
        )
