import pytest

from azure_rag.config import AppConfig, ConfigError


def test_config_requires_storage_values_for_indexer_pipeline(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "chat")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "search-key")
    monkeypatch.setenv("AZURE_SEARCH_INDEX", "rag-index")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONTAINER", raising=False)

    with pytest.raises(ConfigError, match="AZURE_STORAGE_CONNECTION_STRING"):
        AppConfig.from_env(load_dotenv_file=False)


def test_config_loads_required_values(monkeypatch):
    values = {
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/openai/v1",
        "AZURE_OPENAI_API_KEY": "openai-key",
        "AZURE_OPENAI_CHAT_DEPLOYMENT": "chat",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
        "AZURE_SEARCH_ENDPOINT": "https://example.search.windows.net",
        "AZURE_SEARCH_API_KEY": "search-key",
        "AZURE_SEARCH_INDEX": "rag-index",
        "AZURE_STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=https;AccountName=demo;",
        "AZURE_STORAGE_CONTAINER": "sample-docs",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    config = AppConfig.from_env(load_dotenv_file=False)

    assert config.search_index == "rag-index"
    assert config.embedding_dimensions == 1536
    assert config.semantic_configuration == "rag-index-semantic"
