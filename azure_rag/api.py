from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .agent import create_rag_agent
from .config import AppConfig
from .corpus import router as corpus_router
from .identity import current_user_id, validate_user_id
from .rag import RagService
from .readiness import DependencyResult, ReadinessService, probe_openai, probe_search
from .sessions import SessionStore, router as sessions_router
from .telemetry import configure_telemetry, tracer

logger = logging.getLogger(__name__)


def create_app(
    *,
    config: AppConfig | None = None,
    rag_service: RagService | None = None,
    readiness_service: ReadinessService | None = None,
    session_store: SessionStore | None = None,
    agent: Any | None = None,
    register_agui: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_config = config if config is not None else AppConfig.from_env()
        configure_telemetry(resolved_config.applicationinsights_connection_string)
        owns_rag = rag_service is None
        resolved_rag = rag_service if rag_service is not None else RagService(resolved_config)
        resolved_sessions = session_store or (
            SessionStore(resolved_config) if resolved_config.cosmos_endpoint else None
        )
        owns_sessions = session_store is None
        owns_readiness = readiness_service is None
        resolved_readiness = readiness_service or ReadinessService(
            lambda: probe_search(resolved_config, resolved_rag.credential, resolved_rag.session),
            lambda: probe_openai(resolved_config, resolved_rag.openai),
            (lambda: (resolved_sessions.probe(), DependencyResult(status="available"))[1]) if resolved_sessions else None,
        )
        resolved_agent = agent
        if register_agui and resolved_agent is None:
            resolved_agent = create_rag_agent(resolved_config, resolved_rag)
        app.state.config = resolved_config
        app.state.rag = resolved_rag
        app.state.readiness = resolved_readiness
        app.state.agent = resolved_agent
        app.state.sessions = resolved_sessions
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
                if owns_sessions and resolved_sessions is not None:
                    resolved_sessions.close()

    application = FastAPI(title="Azure AI Search RAG Demo", lifespan=lifespan)

    @application.middleware("http")
    async def trace_request(request: Request, call_next):
        started = perf_counter()
        app_config = getattr(request.app.state, "config", None)
        local_fallback = app_config.session_local_user_id if app_config else None
        forwarded_user = request.headers.get("x-rag-user-id") or local_fallback
        resolved_user = validate_user_id(forwarded_user)
        if forwarded_user and resolved_user is None:
            logger.warning("Dropping invalid X-RAG-User-ID header; agent retrieval will fail closed")
        user_token = current_user_id.set(resolved_user)
        with tracer.start_as_current_span("rag.request") as span:
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("url.path", request.url.path)
            try:
                response = await call_next(request)
                span.set_attribute("http.response.status_code", response.status_code)
                return response
            except Exception as error:
                span.record_exception(error)
                raise
            finally:
                span.set_attribute("rag.request.duration_ms", (perf_counter() - started) * 1000)
                current_user_id.reset(user_token)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/ready")
    def ready(request: Request) -> JSONResponse:
        result = request.app.state.readiness.check()
        return JSONResponse(result.response_body(), status_code=result.http_status)

    application.include_router(corpus_router)
    application.include_router(sessions_router)

    return application


app = create_app()
