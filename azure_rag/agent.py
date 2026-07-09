from __future__ import annotations

from typing import Annotated, Any

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

from .auth import openai_token_provider
from .config import AppConfig
from .rag import RagService

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


def format_search_results(chunks: list[Any]) -> str:
    if not chunks:
        return "No relevant documents found above the configured score threshold."
    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        title = getattr(chunk, "title", "") or getattr(chunk, "source_path", "") or "source"
        source_path = getattr(chunk, "source_path", "") or title
        content = getattr(chunk, "chunk", "")
        score = getattr(chunk, "score", None)
        score_text = f" score={score}" if score is not None else ""
        lines.append(f"[{index}] {title} ({source_path}){score_text}\n{content}")
    return "\n\n".join(lines)


def create_search_docs_tool(rag: RagService):
    def search_docs(
        question: Annotated[str, Field(description="The knowledge-base question to search for.")],
        top: Annotated[int, Field(description="Maximum number of chunks to return.", ge=1, le=10)] = 5,
    ) -> str:
        """Search Contoso indexed documents in Azure AI Search and return relevant chunks."""
        chunks = rag.retrieve(question, top=top)
        return format_search_results(chunks)

    return search_docs


def create_chat_client(config: AppConfig, rag: RagService) -> OpenAIChatClient:
    return OpenAIChatClient(
        model=config.azure_openai_chat_deployment,
        azure_endpoint=config.openai_resource_url,
        api_key=openai_token_provider(rag.credential),
    )


def create_rag_agent(config: AppConfig, rag: RagService) -> Agent:
    return Agent(
        name="azure-rag-agent",
        instructions=AGENT_INSTRUCTIONS,
        client=create_chat_client(config, rag),
        tools=[create_search_docs_tool(rag)],
    )
