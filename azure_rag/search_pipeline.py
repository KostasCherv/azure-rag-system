from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests
from azure.storage.blob import BlobServiceClient, ContentSettings

from .config import AppConfig


class AzureSearchError(RuntimeError):
    """Raised when Azure AI Search returns an unsuccessful response."""


def _headers(config: AppConfig) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "api-key": config.search_api_key,
    }


def _url(config: AppConfig, path: str) -> str:
    return f"{config.search_endpoint}{path}?api-version={config.search_api_version}"


def _request(config: AppConfig, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, _url(config, path), headers=_headers(config), timeout=60, **kwargs)
    if response.status_code >= 400:
        raise AzureSearchError(f"{method} {path} failed: {response.status_code} {response.text}")
    if not response.content:
        return {}
    return response.json()


def upload_sample_docs(config: AppConfig, docs_dir: Path = Path("sample_docs")) -> list[str]:
    blob_service = BlobServiceClient.from_connection_string(config.storage_connection_string)
    container = blob_service.get_container_client(config.storage_container)
    try:
        container.create_container()
    except Exception:
        pass

    uploaded: list[str] = []
    for path in sorted(docs_dir.glob("*.md")):
        blob = container.get_blob_client(path.name)
        blob.upload_blob(
            path.read_text(encoding="utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type="text/markdown; charset=utf-8"),
        )
        uploaded.append(path.name)
    return uploaded


def create_or_update_index(config: AppConfig) -> None:
    body = {
        "name": config.search_index,
        "fields": [
            {"name": "document_id", "type": "Edm.String", "key": True, "filterable": True, "sortable": True, "analyzer": "keyword"},
            {"name": "parent_id", "type": "Edm.String", "filterable": True},
            {"name": "title", "type": "Edm.String", "searchable": True, "filterable": True, "retrievable": True},
            {"name": "source_path", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "chunk", "type": "Edm.String", "searchable": True, "retrievable": True},
            {
                "name": "chunk_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "retrievable": False,
                "dimensions": config.embedding_dimensions,
                "vectorSearchProfile": "rag-vector-profile",
            },
        ],
        "vectorSearch": {
            "algorithms": [
                {
                    "name": "rag-hnsw",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "metric": "cosine",
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                    },
                }
            ],
            "profiles": [
                {
                    "name": "rag-vector-profile",
                    "algorithm": "rag-hnsw",
                    "vectorizer": "rag-aoai-vectorizer",
                }
            ],
            "vectorizers": [
                {
                    "name": "rag-aoai-vectorizer",
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": config.openai_resource_url,
                        "deploymentId": config.azure_openai_embedding_deployment,
                        "modelName": config.azure_openai_embedding_deployment,
                        "apiKey": config.azure_openai_api_key,
                    },
                }
            ],
        },
        "semantic": {
            "defaultConfiguration": config.semantic_configuration,
            "configurations": [
                {
                    "name": config.semantic_configuration,
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "prioritizedContentFields": [{"fieldName": "chunk"}],
                        "prioritizedKeywordsFields": [],
                    },
                }
            ],
        },
    }
    _request(config, "PUT", f"/indexes/{config.search_index}", json=body)


def create_or_update_data_source(config: AppConfig) -> None:
    body = {
        "name": config.data_source_name,
        "type": "azureblob",
        "credentials": {"connectionString": config.storage_connection_string},
        "container": {"name": config.storage_container},
        "dataChangeDetectionPolicy": {"@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy", "highWaterMarkColumnName": "metadata_storage_last_modified"},
    }
    _request(config, "PUT", f"/datasources/{config.data_source_name}", json=body)


def create_or_update_skillset(config: AppConfig) -> None:
    body = {
        "name": config.skillset_name,
        "description": "Split sample documents into chunks and embed them with Azure OpenAI inside Azure AI Search.",
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "split-documents",
                "context": "/document",
                "textSplitMode": "pages",
                "maximumPageLength": 1800,
                "pageOverlapLength": 250,
                "defaultLanguageCode": "en",
                "inputs": [{"name": "text", "source": "/document/content"}],
                "outputs": [{"name": "textItems", "targetName": "pages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "embed-chunks",
                "context": "/document/pages/*",
                "resourceUri": config.openai_resource_url,
                "apiKey": config.azure_openai_api_key,
                "deploymentId": config.azure_openai_embedding_deployment,
                "modelName": config.azure_openai_embedding_deployment,
                "dimensions": config.embedding_dimensions,
                "inputs": [{"name": "text", "source": "/document/pages/*"}],
                "outputs": [{"name": "embedding", "targetName": "chunk_vector"}],
            },
        ],
        "indexProjections": {
            "selectors": [
                {
                    "targetIndexName": config.search_index,
                    "parentKeyFieldName": "parent_id",
                    "sourceContext": "/document/pages/*",
                    "mappings": [
                        {"name": "chunk", "source": "/document/pages/*"},
                        {"name": "chunk_vector", "source": "/document/pages/*/chunk_vector"},
                        {"name": "title", "source": "/document/metadata_storage_name"},
                        {"name": "source_path", "source": "/document/metadata_storage_path"},
                    ],
                }
            ],
            "parameters": {"projectionMode": "skipIndexingParentDocuments"},
        },
    }
    _request(config, "PUT", f"/skillsets/{config.skillset_name}", json=body)


def create_or_update_indexer(config: AppConfig) -> None:
    body = {
        "name": config.indexer_name,
        "dataSourceName": config.data_source_name,
        "targetIndexName": config.search_index,
        "skillsetName": config.skillset_name,
        "parameters": {
            "batchSize": 1,
            "maxFailedItems": 0,
            "maxFailedItemsPerBatch": 0,
            "configuration": {
                "dataToExtract": "contentAndMetadata",
                "parsingMode": "default",
            },
        },
    }
    _request(config, "PUT", f"/indexers/{config.indexer_name}", json=body)


def run_indexer(config: AppConfig, wait: bool = True) -> dict[str, Any]:
    _request(config, "POST", f"/indexers/{config.indexer_name}/run")
    if not wait:
        return {}

    deadline = time.time() + 180
    status: dict[str, Any] = {}
    while time.time() < deadline:
        status = _request(config, "GET", f"/indexers/{config.indexer_name}/status")
        last = status.get("lastResult") or {}
        if last.get("status") in {"success", "transientFailure", "persistentFailure"}:
            return status
        time.sleep(5)
    return status


def setup_pipeline(config: AppConfig, upload_samples: bool = True, run: bool = True) -> dict[str, Any]:
    uploaded = upload_sample_docs(config) if upload_samples else []
    create_or_update_index(config)
    create_or_update_data_source(config)
    create_or_update_skillset(config)
    create_or_update_indexer(config)
    status = run_indexer(config) if run else {}
    return {"uploaded": uploaded, "indexer_status": status}

