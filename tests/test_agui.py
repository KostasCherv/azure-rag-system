from types import SimpleNamespace

import pytest

from azure_rag.agui import latest_user_content


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
