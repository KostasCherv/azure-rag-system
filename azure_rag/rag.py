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
from .identity import validate_user_id
from .suggestions import SUGGESTION_TITLE_QUERY_TOP, dedupe_titles
from .telemetry import start_langsmith_run, tracer


@dataclass(frozen=True)
class RetrievedChunk:
    title: str
    chunk: str
    source_path: str
    score: float | None = None
    caption: str = ""


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

    def list_visible_titles(
        self,
        *,
        user_id: str,
        top: int = SUGGESTION_TITLE_QUERY_TOP,
    ) -> list[str]:
        if validate_user_id(user_id) is None:
            raise ValueError("invalid user id")
        started = perf_counter()
        with tracer.start_as_current_span("rag.suggestions", record_exception=False) as span:
            span.set_attribute("azure.search.index", self.config.search_index)
            span.set_attribute("rag.suggestions.top", top)
            span.set_attribute("rag.suggestions.raw_hit_count", 0)
            span.set_attribute("rag.suggestions.result_count", 0)
            try:
                url = (
                    f"{self.config.search_endpoint}/indexes/{self.config.search_index}/docs/search"
                    f"?api-version={self.config.search_api_version}"
                )
                response = self.session.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        **bearer_headers(self.credential, AZURE_SEARCH_SCOPE),
                    },
                    json={
                        "search": "*",
                        "filter": f"user_id eq '{user_id}'",
                        "select": "title",
                        "top": top,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                    raise ValueError("invalid Azure Search response")
                values = payload["value"]
                titles = dedupe_titles(
                    [
                        item["title"]
                        for item in values
                        if isinstance(item, dict) and isinstance(item.get("title"), str)
                    ]
                )
                span.set_attribute("rag.suggestions.raw_hit_count", len(values))
                span.set_attribute("rag.suggestions.result_count", len(titles))
                span.set_attribute(
                    "rag.suggestions.outcome",
                    "success" if titles else "empty",
                )
                return titles
            except Exception as error:
                span.set_attribute("rag.suggestions.outcome", "error")
                span.record_exception(error)
                raise
            finally:
                span.set_attribute(
                    "rag.suggestions.duration_ms",
                    (perf_counter() - started) * 1000,
                )

    def retrieve(
        self,
        question: str,
        top: int = 5,
        *,
        user_id: str,
        source: str | None = None,
    ) -> list[RetrievedChunk]:
        if validate_user_id(user_id) is None:
            raise ValueError("invalid user id")
        started = perf_counter()
        with tracer.start_as_current_span("rag.retrieve") as span:
            span.set_attribute("rag.question", question)
            span.set_attribute("azure.search.index", self.config.search_index)
            span.set_attribute("rag.retrieval.top", top)
            if source:
                span.set_attribute("rag.retrieval.source", source)
            run_inputs: dict[str, Any] = {"question": question, "top": top}
            if source:
                run_inputs["source"] = source
            run = start_langsmith_run(
                name="Retrieve Context",
                run_type="retriever",
                inputs=run_inputs,
                metadata={"azure.search.index": self.config.search_index},
            )
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
                def execute(query_filter: str) -> list[RetrievedChunk]:
                    response = self.session.post(
                        url,
                        headers={
                            "Content-Type": "application/json",
                            **bearer_headers(self.credential, AZURE_SEARCH_SCOPE),
                        },
                        json={**body, "filter": query_filter},
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
                            caption=((item.get("@search.captions") or [{}])[0].get("text") or ""),
                        )
                        for item in results
                    ]
                    return [
                        chunk
                        for chunk in chunks
                        if chunk.score is not None and chunk.score >= self.config.search_min_score
                    ]

                # Unconditional isolation filter derived from the trusted caller identity.
                user_filter = f"user_id eq '{user_id}'"
                if source:
                    escaped = source.replace("'", "''")
                    filtered = execute(
                        user_filter + f" and search.ismatch('{escaped}', 'title')"
                    )
                    if not filtered:
                        # The title analyzer only matches the exact filename, so
                        # a partial source (e.g. missing ".pdf") scopes to zero
                        # chunks. Retry unscoped rather than report no content.
                        span.set_attribute("rag.retrieval.source_fallback", True)
                        filtered = execute(user_filter)
                else:
                    filtered = execute(user_filter)
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
                chunk_outputs = [
                    {
                        "title": chunk.title,
                        "source_path": chunk.source_path,
                        "score": chunk.score,
                        "chunk": chunk.chunk,
                    }
                    for chunk in filtered
                ]
                if run is not None:
                    run.end(outputs={"chunks": chunk_outputs, "result_count": len(filtered)})
                return filtered
            except Exception as error:
                span.record_exception(error)
                if run is not None:
                    run.end(error=error, traceback=error.__traceback__)
                raise
            finally:
                span.set_attribute(
                    "rag.retrieval.duration_ms",
                    (perf_counter() - started) * 1000,
                )
