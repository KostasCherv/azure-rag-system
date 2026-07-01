from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import AppConfig
from .rag import RagService


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top: int = Field(default=5, ge=1, le=10)


class Source(BaseModel):
    title: str
    source_path: str
    score: float | None = None
    preview: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


config = AppConfig.from_env()
rag = RagService(config)
app = FastAPI(title="Azure AI Search RAG Demo")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "index": config.search_index}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> dict:
    return rag.answer(request.question, top=request.top)

