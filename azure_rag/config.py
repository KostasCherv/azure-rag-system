from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True)
class AppConfig:
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    search_endpoint: str
    search_api_key: str
    search_index: str
    storage_connection_string: str
    storage_container: str
    embedding_dimensions: int = 1536
    search_api_version: str = "2026-05-01-preview"

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> "AppConfig":
        if load_dotenv_file:
            load_dotenv()
        required = {
            "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY"),
            "AZURE_OPENAI_CHAT_DEPLOYMENT": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            "AZURE_SEARCH_ENDPOINT": os.getenv("AZURE_SEARCH_ENDPOINT"),
            "AZURE_SEARCH_API_KEY": os.getenv("AZURE_SEARCH_API_KEY"),
            "AZURE_SEARCH_INDEX": os.getenv("AZURE_SEARCH_INDEX"),
            "AZURE_STORAGE_CONNECTION_STRING": os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
            "AZURE_STORAGE_CONTAINER": os.getenv("AZURE_STORAGE_CONTAINER"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            joined = ", ".join(missing)
            raise ConfigError(f"Missing required environment variable(s): {joined}")

        return cls(
            azure_openai_endpoint=required["AZURE_OPENAI_ENDPOINT"].rstrip("/"),
            azure_openai_api_key=required["AZURE_OPENAI_API_KEY"],
            azure_openai_chat_deployment=required["AZURE_OPENAI_CHAT_DEPLOYMENT"],
            azure_openai_embedding_deployment=required["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            search_endpoint=required["AZURE_SEARCH_ENDPOINT"].rstrip("/"),
            search_api_key=required["AZURE_SEARCH_API_KEY"],
            search_index=required["AZURE_SEARCH_INDEX"],
            storage_connection_string=required["AZURE_STORAGE_CONNECTION_STRING"],
            storage_container=required["AZURE_STORAGE_CONTAINER"],
        )

    @property
    def openai_base_url(self) -> str:
        if self.azure_openai_endpoint.endswith("/openai/v1"):
            return self.azure_openai_endpoint + "/"
        return self.azure_openai_endpoint + "/openai/v1/"

    @property
    def openai_resource_url(self) -> str:
        return self.azure_openai_endpoint.removesuffix("/openai/v1")

    @property
    def semantic_configuration(self) -> str:
        return f"{self.search_index}-semantic"

    @property
    def data_source_name(self) -> str:
        return f"{self.search_index}-blob-datasource"

    @property
    def skillset_name(self) -> str:
        return f"{self.search_index}-skillset"

    @property
    def indexer_name(self) -> str:
        return f"{self.search_index}-indexer"
