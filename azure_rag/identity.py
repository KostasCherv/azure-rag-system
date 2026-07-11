from __future__ import annotations

import re
from contextvars import ContextVar

from fastapi import HTTPException, Request

# Entra oids and the local-dev fallback; excludes quotes and whitespace so a
# validated id is safe to interpolate into OData filters and blob prefixes.
USER_ID_PATTERN = re.compile(r"[A-Za-z0-9._:@-]+")
MAX_USER_ID_LENGTH = 128

# Caller identity for paths without direct header access (the agent tool).
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def validate_user_id(value: str | None) -> str | None:
    if not value or len(value) > MAX_USER_ID_LENGTH or not USER_ID_PATTERN.fullmatch(value):
        return None
    return value


def resolve_user_id(request: Request, forwarded: str | None) -> str:
    config = request.app.state.config
    value = validate_user_id(forwarded or config.session_local_user_id)
    if value is None:
        raise HTTPException(status_code=401, detail="user identity required")
    return value
