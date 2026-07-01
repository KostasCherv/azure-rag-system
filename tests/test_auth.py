from azure_rag.auth import (
    AZURE_OPENAI_SCOPE,
    AZURE_SEARCH_SCOPE,
    bearer_headers,
    openai_token_provider,
)


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes):
        self.scopes.append(scopes)
        return type("Token", (), {"token": "managed-identity-token"})()


def test_search_bearer_headers_request_search_scope():
    credential = FakeCredential()

    headers = bearer_headers(credential, AZURE_SEARCH_SCOPE)

    assert headers == {"Authorization": "Bearer managed-identity-token"}
    assert credential.scopes == [("https://search.azure.com/.default",)]


def test_openai_provider_is_wired_to_cognitive_services_scope(monkeypatch):
    captured = {}

    def fake_provider(credential, scope):
        captured.update(credential=credential, scope=scope)
        return "provider"

    monkeypatch.setattr("azure_rag.auth.get_bearer_token_provider", fake_provider)
    credential = FakeCredential()

    assert openai_token_provider(credential) == "provider"
    assert captured == {"credential": credential, "scope": AZURE_OPENAI_SCOPE}
