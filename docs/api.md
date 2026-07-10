# API Reference

FastAPI routes exposed by the backend service.

## Routes

### `GET /health`

Returns the stable, unauthenticated process-liveness response `{"status":"ok"}`. This endpoint makes no Azure calls.

```bash
curl http://127.0.0.1:8000/health
```

### `GET /ready`

Checks Azure AI Search and Azure OpenAI using managed identity. The response includes the index document count and normalized latest indexer result. Independent probes have a five-second aggregate deadline, and results are cached for 30 seconds.

It returns HTTP 200 with `ready` when dependencies work and documents are present, HTTP 200 with `degraded` for a failed historical indexer run, or HTTP 503 with `unavailable` when a dependency fails/times out or the index is empty.

```json
{
  "status": "ready",
  "search": {
    "status": "available",
    "document_count": 42,
    "indexer": {
      "status": "success",
      "started_at": "2026-01-01T00:00:00Z",
      "ended_at": "2026-01-01T00:01:00Z",
      "error": null
    },
    "error": null
  },
  "openai": {"status": "available", "error": null}
}
```

### `POST /agui`

Served by Microsoft Agent Framework's AG-UI bridge (`agent-framework-ag-ui`). The agent streams model tokens over AG-UI events and calls a `search_docs` tool that wraps Azure AI Search retrieval. CopilotKit consumes those deltas out of the box.

```bash
curl -N -X POST http://127.0.0.1:8000/agui \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "threadId": "demo-thread",
    "runId": "demo-run",
    "state": {},
    "messages": [{
      "id": "msg-1",
      "role": "user",
      "content": "What maintenance does the product manual recommend?"
    }],
    "tools": [],
    "context": [],
    "forwardedProps": {}
  }'
```
