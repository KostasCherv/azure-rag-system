from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import requests
from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from .auth import AZURE_SEARCH_SCOPE, bearer_headers, default_credential
from .config import AppConfig

SUPPORTED_SAMPLE_DOC_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
}


class AzureSearchError(RuntimeError):
    """Raised when Azure AI Search returns an unsuccessful response."""


def _headers(credential: TokenCredential) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        **bearer_headers(credential, AZURE_SEARCH_SCOPE),
    }


def _url(config: AppConfig, path: str) -> str:
    return f"{config.search_endpoint}{path}?api-version={config.search_api_version}"


def _request(
    config: AppConfig,
    method: str,
    path: str,
    *,
    credential: TokenCredential,
    session: Any = requests,
    timeout: float = 60,
    **kwargs: Any,
) -> Any:
    response = session.request(method, _url(config, path), headers=_headers(credential), timeout=timeout, **kwargs)
    if response.status_code >= 400:
        raise AzureSearchError(f"{method} {path} failed: {response.status_code} {response.text}")
    if not response.content:
        return {}
    return response.json()


@contextmanager
def _credential_scope(credential: TokenCredential | None) -> Iterator[TokenCredential]:
    owned = credential is None
    resolved = credential if credential is not None else default_credential()
    try:
        yield resolved
    finally:
        if owned:
            resolved.close()


def _managed_request(
    config: AppConfig,
    method: str,
    path: str,
    *,
    credential: TokenCredential | None,
    session: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    with _credential_scope(credential) as resolved:
        return _request(
            config,
            method,
            path,
            credential=resolved,
            session=session,
            **kwargs,
        )


def get_indexer_status(
    config: AppConfig,
    *,
    credential: TokenCredential,
    session: Any = requests,
) -> dict[str, Any]:
    return _request(
        config,
        "GET",
        f"/indexers/{config.indexer_name}/status",
        credential=credential,
        session=session,
    )


def list_documents(
    config: AppConfig,
    *,
    credential: TokenCredential | None = None,
    blob_service_client: Any | None = None,
) -> list[dict[str, Any]]:
    owns_blob_service = blob_service_client is None
    owns_credential = credential is None and owns_blob_service
    resolved_credential = credential
    try:
        if owns_blob_service:
            resolved_credential = credential if credential is not None else default_credential()
            blob_service_client = BlobServiceClient(
                account_url=config.storage_account_url,
                credential=resolved_credential,
            )
        container = blob_service_client.get_container_client(config.storage_container)
        documents: list[dict[str, Any]] = []
        for blob in container.list_blobs():
            suffix = Path(blob.name).suffix.lower()
            if suffix not in SUPPORTED_SAMPLE_DOC_TYPES:
                continue
            documents.append(
                {
                    "name": blob.name,
                    "size": blob.size,
                    "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
                }
            )
        return sorted(documents, key=lambda item: item["name"])
    finally:
        try:
            if owns_blob_service and blob_service_client is not None:
                blob_service_client.close()
        finally:
            if owns_credential and resolved_credential is not None:
                resolved_credential.close()


def upload_document(
    config: AppConfig,
    name: str,
    data: bytes,
    *,
    credential: TokenCredential | None = None,
    blob_service_client: Any | None = None,
) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SAMPLE_DOC_TYPES:
        raise ValueError(f"unsupported document type: {suffix}")

    owns_blob_service = blob_service_client is None
    owns_credential = credential is None and owns_blob_service
    resolved_credential = credential
    try:
        if owns_blob_service:
            resolved_credential = credential if credential is not None else default_credential()
            blob_service_client = BlobServiceClient(
                account_url=config.storage_account_url,
                credential=resolved_credential,
            )
        container = blob_service_client.get_container_client(config.storage_container)
        try:
            container.create_container()
        except Exception:
            pass
        blob = container.get_blob_client(name)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=SUPPORTED_SAMPLE_DOC_TYPES[suffix]),
        )
        return name
    finally:
        try:
            if owns_blob_service and blob_service_client is not None:
                blob_service_client.close()
        finally:
            if owns_credential and resolved_credential is not None:
                resolved_credential.close()


def upload_sample_docs(
    config: AppConfig,
    docs_dir: Path = Path("sample_docs"),
    *,
    credential: TokenCredential | None = None,
    blob_service_client: Any | None = None,
) -> list[str]:
    owns_blob_service = blob_service_client is None
    owns_credential = credential is None and owns_blob_service
    resolved_credential = credential
    try:
        if owns_blob_service:
            resolved_credential = credential if credential is not None else default_credential()
            blob_service_client = BlobServiceClient(
                account_url=config.storage_account_url,
                credential=resolved_credential,
            )
        container = blob_service_client.get_container_client(config.storage_container)
        try:
            container.create_container()
        except Exception:
            pass

        uploaded: list[str] = []
        paths = [
            path
            for path in sorted(docs_dir.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_SAMPLE_DOC_TYPES
        ]
        for path in paths:
            blob = container.get_blob_client(path.name)
            blob.upload_blob(
                path.read_bytes(),
                overwrite=True,
                content_settings=ContentSettings(content_type=SUPPORTED_SAMPLE_DOC_TYPES[path.suffix.lower()]),
            )
            uploaded.append(path.name)
        return uploaded
    finally:
        try:
            if owns_blob_service and blob_service_client is not None:
                blob_service_client.close()
        finally:
            if owns_credential and resolved_credential is not None:
                resolved_credential.close()


def create_or_update_index(
    config: AppConfig, *, credential: TokenCredential | None = None, session: Any = requests
) -> None:
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
    _managed_request(config, "PUT", f"/indexes/{config.search_index}", credential=credential, session=session, json=body)


def create_or_update_data_source(
    config: AppConfig, *, credential: TokenCredential | None = None, session: Any = requests
) -> None:
    body = {
        "name": config.data_source_name,
        "type": "azureblob",
        "credentials": {"connectionString": f"ResourceId={config.storage_resource_id};"},
        "container": {"name": config.storage_container},
        "dataChangeDetectionPolicy": {"@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy", "highWaterMarkColumnName": "metadata_storage_last_modified"},
    }
    _managed_request(config, "PUT", f"/datasources/{config.data_source_name}", credential=credential, session=session, json=body)


def create_or_update_skillset(
    config: AppConfig, *, credential: TokenCredential | None = None, session: Any = requests
) -> None:
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
    _managed_request(config, "PUT", f"/skillsets/{config.skillset_name}", credential=credential, session=session, json=body)


def create_or_update_indexer(
    config: AppConfig, *, credential: TokenCredential | None = None, session: Any = requests
) -> None:
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
    _managed_request(config, "PUT", f"/indexers/{config.indexer_name}", credential=credential, session=session, json=body)


def run_indexer(
    config: AppConfig,
    wait: bool = True,
    *,
    credential: TokenCredential | None = None,
    session: Any = requests,
) -> dict[str, Any]:
    with _credential_scope(credential) as resolved:
        _request(config, "POST", f"/indexers/{config.indexer_name}/run", credential=resolved, session=session)
        if not wait:
            return {}

        deadline = time.time() + 180
        status: dict[str, Any] = {}
        while time.time() < deadline:
            status = get_indexer_status(config, credential=resolved, session=session)
            last = status.get("lastResult") or {}
            if last.get("status") in {"success", "transientFailure", "persistentFailure"}:
                return status
            time.sleep(5)
        return status


def setup_pipeline(
    config: AppConfig,
    upload_samples: bool = True,
    run: bool = True,
    *,
    credential: TokenCredential | None = None,
    session: Any = requests,
) -> dict[str, Any]:
    with _credential_scope(credential) as resolved:
        uploaded = upload_sample_docs(config, credential=resolved) if upload_samples else []
        create_or_update_index(config, credential=resolved, session=session)
        create_or_update_data_source(config, credential=resolved, session=session)
        create_or_update_skillset(config, credential=resolved, session=session)
        create_or_update_indexer(config, credential=resolved, session=session)
        status = run_indexer(config, credential=resolved, session=session) if run else {}
        return {"uploaded": uploaded, "indexer_status": status}
