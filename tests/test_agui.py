from types import SimpleNamespace

import pytest

from azure_rag.agui import (
    format_answer_payload,
    latest_user_content,
    prior_conversation_messages,
)


def test_latest_user_content_returns_last_user_message():
    messages = [
        SimpleNamespace(role="system", content="Ignore this."),
        SimpleNamespace(role="user", content="First question"),
        SimpleNamespace(role="assistant", content="First answer"),
        SimpleNamespace(role="user", content="Second question"),
    ]

    assert latest_user_content(messages) == "Second question"


def test_latest_user_content_rejects_missing_user_message():
    with pytest.raises(ValueError, match="user message"):
        latest_user_content([SimpleNamespace(role="assistant", content="No question")])


def test_prior_conversation_messages_excludes_latest_user_turn():
    messages = [
        SimpleNamespace(role="system", content="Ignore this."),
        SimpleNamespace(role="user", content="Hi my name is kostas"),
        SimpleNamespace(role="assistant", content="Hello Kostas."),
        SimpleNamespace(role="user", content="whats my name"),
    ]

    assert prior_conversation_messages(messages) == [
        {"role": "user", "content": "Hi my name is kostas"},
        {"role": "assistant", "content": "Hello Kostas."},
    ]


def test_format_answer_payload_omits_sources_without_citations():
    payload = format_answer_payload(
        {
            "answer": "Your name is Kostas.",
            "sources": [
                {"title": "contoso-support.md", "source_path": "contoso-support.md"},
                {"title": "contoso-product.md", "source_path": "contoso-product.md"},
            ],
        }
    )

    assert payload == "Your name is Kostas."
    assert "Sources:" not in payload


def test_format_answer_payload_includes_sources_when_answer_cites_them():
    payload = format_answer_payload(
        {
            "answer": "Premium support replies within 4 business hours. [1]",
            "sources": [
                {"title": "contoso-support.md", "source_path": "contoso-support.md"},
            ],
        }
    )

    assert "Sources:" in payload
    assert "[1] contoso-support.md" in payload


def test_agui_events_passes_prior_history_to_rag():
    import asyncio

    from azure_rag.agui import agui_events

    class FakeRag:
        def __init__(self):
            self.calls = []

        def answer(self, question, top=5, history=None):
            self.calls.append({"question": question, "history": history})
            return {"answer": "Your name is Kostas.", "sources": []}

    rag = FakeRag()
    input_data = SimpleNamespace(
        thread_id="thread-1",
        run_id="run-1",
        messages=[
            SimpleNamespace(role="user", content="Hi my name is kostas"),
            SimpleNamespace(role="assistant", content="Hello Kostas."),
            SimpleNamespace(role="user", content="whats my name"),
        ],
    )

    async def collect():
        return [event async for event in agui_events(input_data, "text/event-stream", rag)]

    events = asyncio.run(collect())

    assert rag.calls == [
        {
            "question": "whats my name",
            "history": [
                {"role": "user", "content": "Hi my name is kostas"},
                {"role": "assistant", "content": "Hello Kostas."},
            ],
        }
    ]
    assert any("Your name is Kostas." in event for event in events)
