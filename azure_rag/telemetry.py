from __future__ import annotations

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

tracer = trace.get_tracer("azure-rag-system")
_configured_connection_string: str | None = None


def configure_telemetry(connection_string: str | None) -> bool:
    global _configured_connection_string
    if not connection_string:
        return False
    if _configured_connection_string == connection_string:
        return True
    configure_azure_monitor(connection_string=connection_string)
    _configured_connection_string = connection_string
    return True
