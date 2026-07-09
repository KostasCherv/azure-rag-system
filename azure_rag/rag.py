from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import requests
from azure.core.credentials import TokenCredential
from openai import OpenAI

from .auth import (
    AZURE_SEARCH_SCOPE,
    bearer_headers,
    default_credential,
    openai_token_provider,
)
from .config import AppConfig

Intent = Literal["kb", "meta", "memory"]

_INTENT_LABELS = {"kb", "meta", "memory"}

_CLASSIFY_SYSTEM_PROMPT = (
    "Classify the latest user message for a Contoso document RAG assistant. "
    "Reply with exactly one label: kb, meta, or memory.\n"
    "- meta: greetings, capability questions, or what the assistant can do "
    "(for example: hello, how can you help, what can you do).\n"
    "- memory: personal or conversational details that rely on prior chat turns "
    "(for example: my name is X, what is my name, do you remember what I said).\n"
    "- kb: questions that need Contoso knowledge-base documents "
    "(support, product, security, policies).\n"
    "If unsure, reply kb."
)


@dataclass(frozen=True)
class RetrievedChunk:
    title: str
    chunk: str
    source_path: str
    score: float | None = None


def parse_intent_label(raw: str) -> Intent:
    text = (raw or "").strip().lower()
    if text in _INTENT_LABELS:
        return text  # type: ignore[return-value]

    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            candidate = str(payload.get("intent", "")).strip().lower()
            if candidate in _INTENT_LABELS:
                return candidate  # type: ignore[return-value]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\b(kb|meta|memory)\b", text)
    if match:
        return match.group(1)  # type: ignore[return-value]
    return "kb"


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]] | None = None,
    *,
    intent: Intent = "kb",
) -> list[dict[str, str]]:
    if intent == "meta":
        system = (
            "You are a helpful assistant for an Azure RAG demo over Contoso documents. "
            "Explain briefly that you can answer questions about Contoso support policy, "
            "product notes, and security overview from the indexed knowledge base. "
            "Do not claim the context is empty. Invite the user to ask a specific question about product, security, or support."
        )
        user_content = question
    elif intent == "memory":
        system = (
            "You are a grounded assistant for a RAG demo. Answer using prior conversation "
            "history for personal or conversational details the user already shared. "
            "If history is insufficient, say what is missing. Do not invent knowledge-base facts."
        )
        user_content = f"Question: {question}"
    else:
        context = "\n\n".join(
            f"[{idx}] title: {chunk.title}\nsource: {chunk.source_path}\ncontent: {chunk.chunk}"
            for idx, chunk in enumerate(chunks, start=1)
        )
        system = (
            "You are a grounded assistant for a RAG demo. Use the provided context for "
            "knowledge-base facts and cite those sources using [1], [2], etc. Use prior "
            "conversation history for personal or conversational details the user already "
            "shared. If neither the context nor the conversation history is enough, say "
            "what is missing."
        )
        user_content = f"Context:\n{context}\n\nQuestion: {question}"

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
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

    def classify_intent(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> Intent:
        history_preview = ""
        if history:
            recent = history[-4:]
            history_preview = "\n".join(
                f"{item['role']}: {item['content']}" for item in recent
            )

        user_prompt = f"Latest user message:\n{question.strip()}"
        if history_preview:
            user_prompt = f"Recent conversation:\n{history_preview}\n\n{user_prompt}"

        try:
            completion = self.openai.chat.completions.create(
                model=self.config.azure_openai_chat_deployment,
                messages=[
                    {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=8,
            )
            raw = completion.choices[0].message.content or ""
            return parse_intent_label(raw)
        except Exception:
            return "kb"

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
            chunk
            for chunk in chunks
            if chunk.score is not None and chunk.score >= self.config.search_min_score
        ]

    def answer(
        self,
        question: str,
        top: int = 5,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        intent = self.classify_intent(question, history=history)
        chunks: list[RetrievedChunk] = []
        if intent == "kb":
            chunks = self.retrieve(question, top=top)

        completion = self.openai.chat.completions.create(
            model=self.config.azure_openai_chat_deployment,
            messages=build_messages(question, chunks, history=history, intent=intent),
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
