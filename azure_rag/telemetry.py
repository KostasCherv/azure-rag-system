from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from azure.monitor.opentelemetry import configure_azure_monitor
import langsmith as ls
from opentelemetry import trace

tracer = trace.get_tracer("azure-rag-system")
_configured_connection_string: str | None = None
_langsmith_parent: ContextVar[Any | None] = ContextVar("langsmith_parent", default=None)


def configure_telemetry(connection_string: str | None) -> bool:
    global _configured_connection_string
    if not connection_string:
        return False
    if _configured_connection_string == connection_string:
        return True
    configure_azure_monitor(connection_string=connection_string)
    _configured_connection_string = connection_string
    return True


def langsmith_enabled() -> bool:
    return (
        os.getenv("LANGSMITH_TRACING", "").lower() == "true"
        and bool(os.getenv("LANGSMITH_API_KEY"))
    )


def langsmith_span(
    *,
    name: str,
    run_type: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not langsmith_enabled():
        return
    run = start_langsmith_run(
        name=name,
        run_type=run_type,
        inputs=inputs,
        metadata=metadata or {},
    )
    if run is not None:
        run.end(outputs=outputs or {})


@dataclass
class LangSmithRun:
    run: Any
    context: Any
    token: Any

    def end(
        self,
        *,
        outputs: dict[str, Any] | None = None,
        error: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if error is None:
            self.run.end(outputs=outputs or {})
            self.context.__exit__(None, None, None)
        else:
            self.context.__exit__(type(error), error, traceback)
        try:
            _langsmith_parent.reset(self.token)
        except ValueError:
            _langsmith_parent.set(None)


def start_langsmith_run(
    *,
    name: str,
    run_type: str,
    inputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> LangSmithRun | None:
    if not langsmith_enabled():
        return None
    context = ls.trace(
        name=name,
        run_type=run_type,
        inputs=inputs,
        metadata=metadata or {},
        parent=_langsmith_parent.get(),
    )
    run = context.__enter__()
    token = _langsmith_parent.set(run)
    return LangSmithRun(run=run, context=context, token=token)
