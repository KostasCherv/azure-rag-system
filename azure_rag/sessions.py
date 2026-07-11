from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from azure.core import MatchConditions
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosHttpResponseError,
    CosmosResourceNotFoundError,
)
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from .auth import default_credential
from .config import AppConfig
from .telemetry import tracer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])
TTL_SECONDS = 90 * 24 * 60 * 60
MAX_TITLE_LENGTH = 60
MAX_MESSAGES = 500


class SessionCreate(BaseModel):
    id: UUID | None = None


class SessionUpdate(BaseModel):
    messages: list[dict[str, Any]] = Field(max_length=MAX_MESSAGES)


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:MAX_TITLE_LENGTH]


def title_from_messages(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if str(message.get("role", "")).lower() != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and normalize_title(content):
            return normalize_title(content)
    return "New discussion"


def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc


class SessionStore:
    def __init__(self, config: AppConfig, *, client: Any | None = None):
        if not config.cosmos_endpoint:
            raise ValueError("AZURE_COSMOS_ENDPOINT is not configured")
        self.client = client or CosmosClient(
            config.cosmos_endpoint,
            credential=default_credential(),
            retry_total=3,
            retry_connect=3,
            retry_read=3,
            retry_backoff_factor=0.5,
            retry_backoff_max=4,
        )
        self.container = self.client.get_database_client(config.cosmos_database).get_container_client(
            config.cosmos_sessions_container
        )

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close:
            close()

    def probe(self) -> None:
        self.container.read()

    def list(self, user_id: str, *, limit: int, before: str | None) -> dict[str, Any]:
        parameters: list[dict[str, Any]] = [{"name": "@userId", "value": user_id}]
        where = "c.userId = @userId"
        if before:
            where += " AND c.updatedAt < @before"
            parameters.append({"name": "@before", "value": _decode_cursor(before)})
        query = (
            "SELECT c.id, c.title, c.createdAt, c.updatedAt, c.messageCount "
            f"FROM c WHERE {where} ORDER BY c.updatedAt DESC OFFSET 0 LIMIT {limit + 1}"
        )
        items = list(self.container.query_items(query=query, parameters=parameters, partition_key=user_id))
        has_more = len(items) > limit
        visible = items[:limit]
        return {
            "items": visible,
            "nextCursor": _encode_cursor(visible[-1]["updatedAt"]) if has_more and visible else None,
        }

    def create(self, user_id: str, requested_id: UUID | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item = {
            "id": str(requested_id or uuid4()),
            "userId": user_id,
            "title": "New discussion",
            "createdAt": now,
            "updatedAt": now,
            "messageCount": 0,
            "messages": [],
            "schemaVersion": 1,
            "ttl": TTL_SECONDS,
        }
        return self.container.create_item(item)

    def get(self, user_id: str, session_id: UUID) -> dict[str, Any]:
        try:
            return self.container.read_item(str(session_id), partition_key=user_id)
        except CosmosResourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc

    def update(self, user_id: str, session_id: UUID, messages: list[dict[str, Any]], etag: str) -> dict[str, Any]:
        item = self.get(user_id, session_id)
        item["messages"] = messages
        item["messageCount"] = len(messages)
        item["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item["ttl"] = TTL_SECONDS
        if item.get("title") == "New discussion":
            item["title"] = title_from_messages(messages)
        try:
            return self.container.replace_item(
                str(session_id), item, etag=etag, match_condition=MatchConditions.IfNotModified
            )
        except CosmosAccessConditionFailedError as exc:
            raise HTTPException(status_code=409, detail="session was updated elsewhere") from exc

    def rename(self, user_id: str, session_id: UUID, title: str, etag: str) -> dict[str, Any]:
        item = self.get(user_id, session_id)
        item["title"] = normalize_title(title)
        item["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        item["ttl"] = TTL_SECONDS
        try:
            return self.container.replace_item(
                str(session_id), item, etag=etag, match_condition=MatchConditions.IfNotModified
            )
        except CosmosAccessConditionFailedError as exc:
            raise HTTPException(status_code=409, detail="session was updated elsewhere") from exc

    def delete(self, user_id: str, session_id: UUID) -> None:
        try:
            self.container.delete_item(str(session_id), partition_key=user_id)
        except CosmosResourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc


def _user_id(request: Request, forwarded: str | None) -> str:
    config: AppConfig = request.app.state.config
    value = forwarded or config.session_local_user_id
    if not value or len(value) > 128 or not re.fullmatch(r"[A-Za-z0-9._:@-]+", value):
        raise HTTPException(status_code=401, detail="user identity required")
    return value


def _store(request: Request) -> SessionStore:
    store = getattr(request.app.state, "sessions", None)
    if store is None:
        raise HTTPException(status_code=503, detail="session persistence unavailable")
    return store


def _document(item: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in item.items() if not key.startswith("_") and key != "userId"}
    result["etag"] = item.get("_etag")
    return result


def _run(operation: str, callback: Any) -> Any:
    started = perf_counter()
    with tracer.start_as_current_span(f"sessions.{operation}") as span:
        try:
            result = callback()
            span.set_attribute("sessions.operation", operation)
            return result
        except HTTPException:
            raise
        except CosmosHttpResponseError as exc:
            span.record_exception(exc)
            logger.warning("Session operation %s failed with Cosmos status %s", operation, exc.status_code)
            raise HTTPException(status_code=503, detail="session persistence unavailable") from exc
        finally:
            span.set_attribute("sessions.duration_ms", (perf_counter() - started) * 1000)


@router.get("")
def list_sessions(request: Request, limit: int = Query(30, ge=1, le=100), before: str | None = None,
                  x_rag_user_id: str | None = Header(None)) -> dict[str, Any]:
    user_id = _user_id(request, x_rag_user_id)
    return _run("list", lambda: _store(request).list(user_id, limit=limit, before=before))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_session(body: SessionCreate, request: Request, x_rag_user_id: str | None = Header(None)) -> dict[str, Any]:
    user_id = _user_id(request, x_rag_user_id)
    return _run("create", lambda: _document(_store(request).create(user_id, body.id)))


@router.get("/{session_id}")
def get_session(session_id: UUID, request: Request, x_rag_user_id: str | None = Header(None)) -> dict[str, Any]:
    user_id = _user_id(request, x_rag_user_id)
    return _run("get", lambda: _document(_store(request).get(user_id, session_id)))


@router.put("/{session_id}")
def update_session(session_id: UUID, body: SessionUpdate, request: Request, if_match: str = Header(...),
                   x_rag_user_id: str | None = Header(None)) -> dict[str, Any]:
    user_id = _user_id(request, x_rag_user_id)
    return _run("update", lambda: _document(_store(request).update(user_id, session_id, body.messages, if_match)))


@router.patch("/{session_id}")
def rename_session(session_id: UUID, body: SessionRename, request: Request, if_match: str = Header(...),
                   x_rag_user_id: str | None = Header(None)) -> dict[str, Any]:
    user_id = _user_id(request, x_rag_user_id)
    return _run("rename", lambda: _document(_store(request).rename(user_id, session_id, body.title, if_match)))


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: UUID, request: Request, x_rag_user_id: str | None = Header(None)) -> Response:
    user_id = _user_id(request, x_rag_user_id)
    _run("delete", lambda: _store(request).delete(user_id, session_id))
    return Response(status_code=204)
