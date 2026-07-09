from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import requests
from azure.core.credentials import TokenCredential
from openai import OpenAI

from .auth import AZURE_SEARCH_SCOPE, bearer_headers, default_credential, openai_token_provider
from .config import AppConfig
from .telemetry import tracer


@dataclass(frozen=True)
class RetrievedChunk:
    title: str
    chunk: str
    source_path: str
    score: float | None = None


def source_label(chunk: RetrievedChunk) -> str:
    if chunk.title:
        return chunk.title
    source = chunk.source_path.strip()
    if not source:
        return "source"
    parsed = urlparse(source)
    if parsed.path:
        name = PurePosixPath(parsed.path).name
        if name:
            return name
    return PurePosixPath(source).name or source


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
        started = perf_counter()
        with tracer.start_as_current_span("rag.retrieve") as span:
            span.set_attribute("rag.question", question)
            span.set_attribute("azure.search.index", self.config.search_index)
            span.set_attribute("rag.retrieval.top", top)
            try:
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
                filtered = [
                    chunk
                    for chunk in chunks
                    if chunk.score is not None and chunk.score >= self.config.search_min_score
                ]
                span.set_attribute("rag.retrieval.result_count", len(filtered))
                span.set_attribute(
                    "rag.retrieval.context",
                    json.dumps(
                        [
                            {
                                "title": chunk.title,
                                "source_path": chunk.source_path,
                                "score": chunk.score,
                                "chunk": chunk.chunk,
                            }
                            for chunk in filtered
                        ]
                    ),
                )
                return filtered
            except Exception as error:
                span.record_exception(error)
                raise
            finally:
                span.set_attribute(
                    "rag.retrieval.duration_ms",
                    (perf_counter() - started) * 1000,
                )
