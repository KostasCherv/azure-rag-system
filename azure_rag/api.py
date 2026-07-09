from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .agent import create_rag_agent
from .config import AppConfig
from .rag import RagService
from .readiness import ReadinessService, probe_openai, probe_search


def create_app(
    *,
    config: AppConfig | None = None,
    rag_service: RagService | None = None,
    readiness_service: ReadinessService | None = None,
    agent: Any | None = None,
    register_agui: bool = True,
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
        resolved_agent = agent
        if register_agui and resolved_agent is None:
            resolved_agent = create_rag_agent(resolved_config, resolved_rag)
        app.state.config = resolved_config
        app.state.rag = resolved_rag
        app.state.readiness = resolved_readiness
        app.state.agent = resolved_agent
        if register_agui and resolved_agent is not None and not getattr(app.state, "agui_registered", False):
            add_agent_framework_fastapi_endpoint(app, resolved_agent, "/agui")
            app.state.agui_registered = True
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

    return application


app = create_app()
