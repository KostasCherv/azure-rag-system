import pytest

from azure_rag.config import AppConfig, ConfigError


REQUIRED_ENV = {
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/openai/v1/",
    "AZURE_OPENAI_CHAT_DEPLOYMENT": "chat",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
    "AZURE_SEARCH_ENDPOINT": "https://example.search.windows.net/",
    "AZURE_SEARCH_INDEX": "rag-index",
    "AZURE_STORAGE_ACCOUNT_URL": "https://storage.blob.core.windows.net/",
    "AZURE_STORAGE_CONTAINER": "sample-docs",
    "AZURE_STORAGE_RESOURCE_ID": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/storage",
}


def _set_required_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("missing", REQUIRED_ENV)
def test_config_requires_managed_identity_resource_settings(monkeypatch, missing):
    _set_required_env(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(ConfigError, match=missing):
        AppConfig.from_env(load_dotenv_file=False)


def test_config_loads_keyless_values_and_normalizes_endpoints(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "must-not-be-used")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "must-not-be-used")

    config = AppConfig.from_env(load_dotenv_file=False)

    assert config.azure_openai_endpoint == "https://example.openai.azure.com/openai/v1"
    assert config.openai_base_url == "https://example.openai.azure.com/openai/v1/"
    assert config.openai_resource_url == "https://example.openai.azure.com"
    assert config.search_endpoint == "https://example.search.windows.net"
    assert config.storage_account_url == "https://storage.blob.core.windows.net"
    assert config.storage_resource_id == REQUIRED_ENV["AZURE_STORAGE_RESOURCE_ID"]
    assert config.semantic_configuration == "rag-index-semantic"
    assert config.data_source_name == "rag-index-blob-datasource"
    assert config.search_min_score == 2.0
    assert not hasattr(config, "azure_openai_api_key")
    assert not hasattr(config, "search_api_key")
    assert not hasattr(config, "storage_connection_string")


def test_config_loads_optional_application_insights_connection_string(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=abc")

    config = AppConfig.from_env(load_dotenv_file=False)

    assert config.applicationinsights_connection_string == "InstrumentationKey=abc"


def test_config_allows_overriding_search_min_score(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AZURE_SEARCH_MIN_SCORE", "2.75")

    config = AppConfig.from_env(load_dotenv_file=False)

    assert config.search_min_score == 2.75
