from __future__ import annotations

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from ag_ui.core import RunAgentInput

from .agui import agui_events
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


@app.post("/agui")
async def agui(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    accept_header = request.headers.get("accept")
    encoder_content_type = "text/event-stream"
    return StreamingResponse(
        agui_events(input_data, accept_header, rag),
        media_type=encoder_content_type,
    )
