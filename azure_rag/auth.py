from __future__ import annotations

import os
from typing import Callable

from azure.core.credentials import AccessToken, TokenCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider


AZURE_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"
AZURE_SEARCH_SCOPE = "https://search.azure.com/.default"


def default_credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


def openai_token_provider(credential: TokenCredential) -> str | Callable[[], str]:
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if api_key:
        return api_key
    return get_bearer_token_provider(credential, AZURE_OPENAI_SCOPE)


def bearer_headers(credential: TokenCredential, scope: str) -> dict[str, str]:
    if scope == AZURE_SEARCH_SCOPE:
        api_key = os.getenv("AZURE_SEARCH_API_KEY")
        if api_key:
            return {"api-key": api_key}
    token: AccessToken = credential.get_token(scope)
    return {"Authorization": f"Bearer {token.token}"}
