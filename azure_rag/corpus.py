from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .readiness import IndexerResult, normalize_indexer, sanitize_error
from .search_pipeline import (
    AzureSearchError,
    get_indexer_status,
    list_documents,
    run_indexer,
    upload_document,
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".md"}
SAFE_FILENAME = re.compile(r"^[\w\-. ]+$")

router = APIRouter(prefix="/corpus", tags=["corpus"])


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    if not base or base in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid filename")
    suffix = Path(base).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="only .pdf and .md files are supported")
    stem = re.sub(r"[^\w\-. ]", "_", Path(base).stem) or "document"
    sanitized = f"{stem}{suffix}"
    if not SAFE_FILENAME.match(sanitized):
        raise HTTPException(status_code=400, detail="invalid filename")
    return sanitized


def _indexer_payload(result: IndexerResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "error": result.error,
    }


@router.get("/documents")
def list_corpus_documents(request: Request) -> list[dict[str, Any]]:
    rag = request.app.state.rag
    try:
        return list_documents(rag.config, credential=rag.credential, blob_service_client=None)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=sanitize_error(exc, "failed to list documents"),
        ) from exc


@router.post("/documents")
async def upload_corpus_document(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    rag = request.app.state.rag
    filename = sanitize_filename(file.filename or "")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 20MB limit")
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        uploaded = upload_document(rag.config, filename, data, credential=rag.credential)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=sanitize_error(exc, "failed to upload document"),
        ) from exc
    return {"name": uploaded}


@router.get("/indexer")
def get_corpus_indexer_status(request: Request) -> dict[str, Any]:
    rag = request.app.state.rag
    try:
        payload = get_indexer_status(rag.config, credential=rag.credential, session=rag.session)
    except AzureSearchError as exc:
        raise HTTPException(
            status_code=503,
            detail=sanitize_error(exc, "failed to read indexer status"),
        ) from exc
    return _indexer_payload(normalize_indexer(payload))


@router.post("/indexer/run")
def run_corpus_indexer(request: Request) -> JSONResponse:
    rag = request.app.state.rag
    try:
        current = get_indexer_status(rag.config, credential=rag.credential, session=rag.session)
    except AzureSearchError as exc:
        raise HTTPException(
            status_code=503,
            detail=sanitize_error(exc, "failed to read indexer status"),
        ) from exc
    if normalize_indexer(current).status == "running":
        raise HTTPException(status_code=409, detail="indexer is already running")
    try:
        run_indexer(rag.config, wait=False, credential=rag.credential, session=rag.session)
    except AzureSearchError as exc:
        raise HTTPException(
            status_code=503,
            detail=sanitize_error(exc, "failed to start indexer"),
        ) from exc
    return JSONResponse({"status": "accepted"}, status_code=202)
