from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True)
class AppConfig:
    azure_openai_endpoint: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    search_endpoint: str
    search_index: str
    storage_account_url: str
    storage_container: str
    storage_resource_id: str
    applicationinsights_connection_string: str | None = None
    embedding_dimensions: int = 1536
    search_api_version: str = "2026-05-01-preview"
    search_min_score: float = 1.5
    answer_max_tokens: int = 5000

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> "AppConfig":
        if load_dotenv_file:
            load_dotenv()
        required = {
            "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "AZURE_OPENAI_CHAT_DEPLOYMENT": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": os.getenv(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
            ),
            "AZURE_SEARCH_ENDPOINT": os.getenv("AZURE_SEARCH_ENDPOINT"),
            "AZURE_SEARCH_INDEX": os.getenv("AZURE_SEARCH_INDEX"),
            "AZURE_STORAGE_ACCOUNT_URL": os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
            "AZURE_STORAGE_CONTAINER": os.getenv("AZURE_STORAGE_CONTAINER"),
            "AZURE_STORAGE_RESOURCE_ID": os.getenv("AZURE_STORAGE_RESOURCE_ID"),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            joined = ", ".join(missing)
            raise ConfigError(f"Missing required environment variable(s): {joined}")

        return cls(
            azure_openai_endpoint=required["AZURE_OPENAI_ENDPOINT"].rstrip("/"),
            azure_openai_chat_deployment=required["AZURE_OPENAI_CHAT_DEPLOYMENT"],
            azure_openai_embedding_deployment=required[
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
            ],
            search_endpoint=required["AZURE_SEARCH_ENDPOINT"].rstrip("/"),
            search_index=required["AZURE_SEARCH_INDEX"],
            storage_account_url=required["AZURE_STORAGE_ACCOUNT_URL"].rstrip("/"),
            storage_container=required["AZURE_STORAGE_CONTAINER"],
            storage_resource_id=required["AZURE_STORAGE_RESOURCE_ID"],
            applicationinsights_connection_string=os.getenv(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            ),
            search_min_score=float(os.getenv("AZURE_SEARCH_MIN_SCORE", "2.0")),
            answer_max_tokens=int(os.getenv("RAG_ANSWER_MAX_TOKENS", "5000")),
        )

    @property
    def chat_uses_completion_token_limit(self) -> bool:
        name = self.azure_openai_chat_deployment.casefold()
        return name.startswith(("gpt-5", "o1", "o3", "o4"))

    def agent_default_options(self) -> dict[str, int]:
        # Agent Framework's OpenAIChatClient uses the Responses API and maps
        # max_tokens -> max_output_tokens internally.
        return {"max_tokens": self.answer_max_tokens}

    def readiness_probe_options(self) -> dict[str, int | float]:
        if self.chat_uses_completion_token_limit:
            return {"max_completion_tokens": 16}
        return {"max_tokens": 1, "temperature": 0}

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
