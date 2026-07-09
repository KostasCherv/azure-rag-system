from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ag_ui.core import (
    EventType,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.encoder import EventEncoder

from .rag import RagService


def latest_user_content(messages: Sequence[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "role", None) == "user" and getattr(message, "content", None):
            return message.content
    raise ValueError("AG-UI input must include at least one user message with content.")


def prior_conversation_messages(messages: Sequence[Any]) -> list[dict[str, str]]:
    """Return user/assistant turns before the latest user message."""
    latest_user_index: int | None = None
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if getattr(message, "role", None) == "user" and getattr(message, "content", None):
            latest_user_index = index
            break
    if latest_user_index is None:
        raise ValueError("AG-UI input must include at least one user message with content.")

    history: list[dict[str, str]] = []
    for message in messages[:latest_user_index]:
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content})
    return history


def answer_cites_sources(answer: str) -> bool:
    return bool(re.search(r"\[\d+\]", answer))


def format_answer_payload(result: dict[str, Any]) -> str:
    answer = result["answer"]
    sources = result.get("sources") or []
    if not sources or not answer_cites_sources(answer):
        return answer

    source_lines = [
        f"[{index}] {source.get('title') or source.get('source_path') or 'source'}"
        for index, source in enumerate(sources, start=1)
    ]
    return f"{answer}\n\nSources:\n" + "\n".join(source_lines)


async def agui_events(
    input_data: RunAgentInput,
    accept_header: str | None,
    rag: RagService,
) -> AsyncIterator[str]:
    encoder = EventEncoder(accept=accept_header)
    message_id = str(uuid.uuid4())

    try:
        yield encoder.encode(
            RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id,
            )
        )

        question = latest_user_content(input_data.messages)
        history = prior_conversation_messages(input_data.messages)
        result = rag.answer(question, history=history)
        content = format_answer_payload(result)

        yield encoder.encode(
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            )
        )
        yield encoder.encode(
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=content,
            )
        )
        yield encoder.encode(
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            )
        )
        yield encoder.encode(
            RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id,
            )
        )
    except Exception as error:
        yield encoder.encode(
            RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(error),
            )
        )
