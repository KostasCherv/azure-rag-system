from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from openai import OpenAI

from .config import AppConfig


@dataclass(frozen=True)
class RetrievedChunk:
    title: str
    chunk: str
    source_path: str
    score: float | None = None


def build_messages(question: str, chunks: list[RetrievedChunk]) -> list[dict[str, str]]:
    context = "\n\n".join(
        f"[{idx}] title: {chunk.title}\nsource: {chunk.source_path}\ncontent: {chunk.chunk}"
        for idx, chunk in enumerate(chunks, start=1)
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a grounded assistant for a RAG demo. Answer only from the provided context. "
                "If the context is insufficient, say what is missing. Cite sources using [1], [2], etc."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        },
    ]


class RagService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.openai = OpenAI(base_url=config.openai_base_url, api_key=config.azure_openai_api_key)

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
        response = requests.post(
            url,
            headers={"Content-Type": "application/json", "api-key": self.config.search_api_key},
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("value", [])
        return [
            RetrievedChunk(
                title=item.get("title", ""),
                chunk=item.get("chunk", ""),
                source_path=item.get("source_path", ""),
                score=item.get("@search.rerankerScore") or item.get("@search.score"),
            )
            for item in results
        ]

    def answer(self, question: str, top: int = 5) -> dict[str, Any]:
        chunks = self.retrieve(question, top=top)
        completion = self.openai.chat.completions.create(
            model=self.config.azure_openai_chat_deployment,
            messages=build_messages(question, chunks),
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

