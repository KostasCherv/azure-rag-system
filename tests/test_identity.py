import pytest
from fastapi import HTTPException

from azure_rag.identity import current_user_id, resolve_user_id, validate_user_id


class FakeRequest:
    def __init__(self, local_user_id=None):
        config = type("Config", (), {"session_local_user_id": local_user_id})()
        state = type("State", (), {"config": config})()
        self.app = type("App", (), {"state": state})()


def test_validate_user_id_accepts_oids_and_local_ids():
    assert validate_user_id("11111111-1111-1111-1111-111111111111") == "11111111-1111-1111-1111-111111111111"
    assert validate_user_id("local-development-user") == "local-development-user"


@pytest.mark.parametrize("value", [None, "", "a" * 129, "user id", "user'id", "user/id", ".", ".."])
def test_validate_user_id_rejects_unsafe_values(value):
    assert validate_user_id(value) is None


def test_resolve_user_id_prefers_forwarded_header():
    assert resolve_user_id(FakeRequest(local_user_id="local"), "user-a") == "user-a"


def test_resolve_user_id_falls_back_to_local_config():
    assert resolve_user_id(FakeRequest(local_user_id="local"), None) == "local"


def test_resolve_user_id_fails_closed():
    with pytest.raises(HTTPException) as excinfo:
        resolve_user_id(FakeRequest(), None)
    assert excinfo.value.status_code == 401

    with pytest.raises(HTTPException):
        resolve_user_id(FakeRequest(), "bad'value")


def test_current_user_id_defaults_to_none():
    assert current_user_id.get() is None
