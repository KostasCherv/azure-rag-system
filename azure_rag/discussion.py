from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from .identity import resolve_user_id
from .suggestions import ChatSuggestion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discussion", tags=["discussion"])


class DiscussionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class DiscussionSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[DiscussionMessage] = Field(min_length=1, max_length=12)


@router.post("/suggestions")
def suggest_from_discussion(
    payload: DiscussionSuggestionRequest,
    request: Request,
    x_rag_user_id: str | None = Header(None),
) -> list[ChatSuggestion]:
    resolve_user_id(request, x_rag_user_id)
    try:
        messages = [message.model_dump() for message in payload.messages]
        return request.app.state.rag.suggest_followups(messages)[:3]
    except Exception as error:
        logger.warning(
            "Discussion suggestion generation failed",
            extra={"error_type": type(error).__name__},
        )
        return []
