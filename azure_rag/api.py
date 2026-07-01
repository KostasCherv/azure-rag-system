from __future__ import annotations

from contextlib import asynccontextmanager

from ag_ui.core import RunAgentInput
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .agui import agui_events
from .config import AppConfig
from .rag import RagService
from .readiness import ReadinessService, probe_openai, probe_search


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


def create_app(
    *,
    config: AppConfig | None = None,
    rag_service: RagService | None = None,
    readiness_service: ReadinessService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_config = config if config is not None else AppConfig.from_env()
        owns_rag = rag_service is None
        resolved_rag = rag_service if rag_service is not None else RagService(resolved_config)
        owns_readiness = readiness_service is None
        resolved_readiness = readiness_service or ReadinessService(
            lambda: probe_search(resolved_config, resolved_rag.credential, resolved_rag.session),
            lambda: probe_openai(resolved_config, resolved_rag.openai),
        )
        app.state.config = resolved_config
        app.state.rag = resolved_rag
        app.state.readiness = resolved_readiness
        try:
            yield
        finally:
            try:
                if owns_readiness:
                    resolved_readiness.close()
            finally:
                if owns_rag:
                    resolved_rag.close()

    application = FastAPI(title="Azure AI Search RAG Demo", lifespan=lifespan)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    def ready(request: Request) -> JSONResponse:
        result = request.app.state.readiness.check()
        return JSONResponse(result.response_body(), status_code=result.http_status)

    @application.post("/query", response_model=QueryResponse)
    def query(input_data: QueryRequest, request: Request) -> dict:
        return request.app.state.rag.answer(input_data.question, top=input_data.top)

    @application.post("/agui")
    async def agui(input_data: RunAgentInput, request: Request) -> StreamingResponse:
        return StreamingResponse(
            agui_events(input_data, request.headers.get("accept"), request.app.state.rag),
            media_type="text/event-stream",
        )

    return application


app = create_app()
