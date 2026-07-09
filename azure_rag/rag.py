from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from azure.core.credentials import TokenCredential
from openai import OpenAI

from .auth import AZURE_SEARCH_SCOPE, bearer_headers, default_credential, openai_token_provider
from .config import AppConfig


@dataclass(frozen=True)
class RetrievedChunk:
    title: str
    chunk: str
    source_path: str
    score: float | None = None


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    context = "\n\n".join(
        f"[{idx}] title: {chunk.title}\nsource: {chunk.source_path}\ncontent: {chunk.chunk}"
        for idx, chunk in enumerate(chunks, start=1)
    )
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are a grounded assistant for a RAG demo. Use the provided context for "
                "knowledge-base facts and cite those sources using [1], [2], etc. Use prior "
                "conversation history for personal or conversational details the user already "
                "shared. If neither the context nor the conversation history is enough, say "
                "what is missing."
            ),
        },
    ]
    if history:
        messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        }
    )
    return messages


class RagService:
    def __init__(
        self,
        config: AppConfig,
        *,
        credential: TokenCredential | None = None,
        openai_client: Any | None = None,
        session: Any = requests,
    ):
        self.config = config
        self._owns_credential = credential is None
        self._owns_openai = openai_client is None
        self.credential = credential if credential is not None else default_credential()
        self.session = session
        if openai_client is not None:
            self.openai = openai_client
        else:
            try:
                self.openai = OpenAI(
                    base_url=config.openai_base_url,
                    api_key=openai_token_provider(self.credential),
                )
            except Exception:
                if self._owns_credential:
                    self.credential.close()
                raise

    def close(self) -> None:
        try:
            if self._owns_openai:
                self.openai.close()
        finally:
            if self._owns_credential:
                self.credential.close()

    def retrieve(self, question: str, top: int = 5) -> list[RetrievedChunk]:
        url = (
            f"{self.config.search_endpoint}/indexes/{self.config.search_index}/docs/search"
            f"?api-version={self.config.search_api_version}"
        )
        body: dict[str, Any] = {
            "search": question,
            "searchMode": "all",
            "queryType": "semantic",
            "semanticConfiguration": self.config.semantic_configuration,
            "captions": "extractive",
            "answers": "extractive|count-3",
            "select": "title,chunk,source_path",
            "top": top,
            "vectorQueries": [
                {
                    "kind": "text",
                    "text": question,
                    "fields": "chunk_vector",
                    "k": 50,
                }
            ],
        }
        response = self.session.post(
            url,
            headers={
                "Content-Type": "application/json",
                **bearer_headers(self.credential, AZURE_SEARCH_SCOPE),
            },
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("value", [])
        chunks = [
            RetrievedChunk(
                title=item.get("title", ""),
                chunk=item.get("chunk", ""),
                source_path=item.get("source_path", ""),
                score=item.get("@search.rerankerScore") or item.get("@search.score"),
            )
            for item in results
        ]
        return [
            chunk for chunk in chunks if chunk.score is not None and chunk.score >= self.config.search_min_score
        ]

    def answer(
        self,
        question: str,
        top: int = 5,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        chunks = self.retrieve(question, top=top)
        completion = self.openai.chat.completions.create(
            model=self.config.azure_openai_chat_deployment,
            messages=build_messages(question, chunks, history=history),
            temperature=0.2,
        )
        answer = completion.choices[0].message.content or ""
        return {
            "answer": answer,
            "sources": [
                {
                    "title": chunk.title,
                    "source_path": chunk.source_path,
                    "score": chunk.score,
                    "preview": chunk.chunk[:280],
                }
                for chunk in chunks
            ],
        }
