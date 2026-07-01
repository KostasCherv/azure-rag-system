from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Callable, Literal

from azure.core.credentials import TokenCredential

from .config import AppConfig
from .search_pipeline import _request

DependencyStatus = Literal["available", "unavailable"]
OverallStatus = Literal["ready", "degraded", "unavailable"]


@dataclass(frozen=True)
class DependencyResult:
    status: DependencyStatus
    error: str | None = None


@dataclass(frozen=True)
class IndexerResult:
    status: Literal["success", "failed", "running", "unknown"] = "unknown"
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SearchResult(DependencyResult):
    document_count: int | None = None
    indexer: IndexerResult = IndexerResult()


@dataclass(frozen=True)
class ReadinessResult:
    status: OverallStatus
    search: SearchResult
    openai: DependencyResult
    http_status: int

    def response_body(self) -> dict[str, Any]:
        body = asdict(self)
        body.pop("http_status")
        return body


def sanitize_error(error: BaseException | str, fallback: str = "operation failed") -> str:
    """Map untrusted diagnostics to a small, non-sensitive vocabulary."""
    text = str(error).lower()
    if "timeout" in text or "timed out" in text:
        return "operation timed out"
    if any(marker in text for marker in ("401", "unauthenticated", "authentication failed")):
        return "authentication failed"
    if any(marker in text for marker in ("403", "forbidden", "authorization failed")):
        return "authorization failed"
    if any(marker in text for marker in ("429", "rate limit", "throttl")):
        return "rate limited"
    return fallback


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def normalize_indexer(payload: dict[str, Any]) -> IndexerResult:
    latest = payload.get("lastResult") or {}
    raw_status = str(latest.get("status") or payload.get("status") or "unknown").lower()
    if raw_status in {"success", "reset"}:
        status = "success"
    elif raw_status in {"inprogress", "running"}:
        status = "running"
    elif raw_status in {"transientfailure", "persistentfailure", "failed", "error"}:
        status = "failed"
    else:
        status = "unknown"
    error = latest.get("errorMessage")
    return IndexerResult(
        status=status,
        started_at=_timestamp(latest.get("startTime")),
        ended_at=_timestamp(latest.get("endTime")),
        error=sanitize_error(error, "indexer run failed") if error else None,
    )


def probe_search(config: AppConfig, credential: TokenCredential, session: Any) -> SearchResult:
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="search-readiness") as executor:
        count_future = executor.submit(
            _request, config, "GET", f"/indexes/{config.search_index}/docs/$count",
            credential=credential, session=session, timeout=5,
        )
        indexer_future = executor.submit(
            _request, config, "GET", f"/indexers/{config.indexer_name}/status",
            credential=credential, session=session, timeout=5,
        )
        count = count_future.result()
        indexer = indexer_future.result()
    return SearchResult(status="available", document_count=int(count), indexer=normalize_indexer(indexer))


def probe_openai(
    config: AppConfig, client: Any, *, timeout_seconds: float = 5
) -> DependencyResult:
    client.with_options(timeout=timeout_seconds, max_retries=0).chat.completions.create(
        model=config.azure_openai_chat_deployment,
        messages=[{"role": "user", "content": "Reply OK."}],
        max_tokens=1,
        temperature=0,
    )
    return DependencyResult(status="available")


class ReadinessService:
    def __init__(
        self,
        search_probe: Callable[[], SearchResult],
        openai_probe: Callable[[], DependencyResult],
        *,
        timeout_seconds: float = 5,
        cache_seconds: float = 30,
        clock: Callable[[], float] = monotonic,
    ):
        self._search_probe = search_probe
        self._openai_probe = openai_probe
        self._timeout = timeout_seconds
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._cached: tuple[float, ReadinessResult] | None = None
        self._lock = Lock()

    def check(self) -> ReadinessResult:
        with self._lock:
            now = self._clock()
            if self._cached is not None and now - self._cached[0] < self._cache_seconds:
                return self._cached[1]
            result = self._run_probes()
            self._cached = (self._clock(), result)
            return result

    def _run_probes(self) -> ReadinessResult:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="readiness") as executor:
            search_future = executor.submit(self._search_probe)
            openai_future = executor.submit(self._openai_probe)
            done, pending = wait({search_future, openai_future}, timeout=self._timeout)
            for future in pending:
                future.cancel()
        search = self._search_result(search_future, done)
        openai = self._dependency_result(openai_future, done)
        unavailable = (
            search.status == "unavailable"
            or openai.status == "unavailable"
            or not search.document_count
        )
        if unavailable:
            status: OverallStatus = "unavailable"
            http_status = 503
        elif search.indexer.status == "failed":
            status = "degraded"
            http_status = 200
        else:
            status = "ready"
            http_status = 200
        return ReadinessResult(status, search, openai, http_status)

    @staticmethod
    def _search_result(future: Future[Any], done: set[Future[Any]]) -> SearchResult:
        if future not in done:
            return SearchResult(status="unavailable", error="probe timed out")
        try:
            result = future.result()
            if not isinstance(result, SearchResult):
                raise TypeError("invalid probe result")
            return result
        except Exception as exc:
            return SearchResult(status="unavailable", error=sanitize_error(exc))

    @staticmethod
    def _dependency_result(future: Future[Any], done: set[Future[Any]]) -> DependencyResult:
        if future not in done:
            return DependencyResult(status="unavailable", error="probe timed out")
        try:
            result = future.result()
            if not isinstance(result, DependencyResult):
                raise TypeError("invalid probe result")
            return result
        except Exception as exc:
            return DependencyResult(status="unavailable", error=sanitize_error(exc))
