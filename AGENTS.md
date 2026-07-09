# AGENTS.md

Project-specific guidance for AI coding agents working in this repository.

## Decision Defaults

- Default to production-like outcomes: security, reliability, observability, operability.
- Prefer Azure-native managed services unless the user asks otherwise.
- Use Ponytail style: minimum robust code, reuse first, stdlib/platform first, small focused diffs.

## Non-Trivial Decision Gate

Treat a request as non-trivial when at least one applies:
- Architectural or cross-service change.
- Azure resource/service selection or topology change.
- Security, reliability, scalability, or operability impact.
- Meaningful cost impact.
- Shared contracts/protocols are affected (for example AG-UI, API boundaries, indexing/query behavior).

For trivial tasks (small bugfixes, typo/docs-only edits, straightforward refactors), implement directly without option table overhead.

## Option Comparison Contract (Non-Trivial Only)

Use this table shape:

| Option | Azure fit | Complexity | Cost impact | Reliability/Operability | Pros | Cons | Recommendation |
|---|---|---|---|---|---|---|---|

Rules:
- Present exactly 2-3 options.
- Include a default recommendation in the table (`Recommended: Option X`).
- Provide 2-3 short arguments for why the recommended option is best for this repository.
- After the comparison, proceed with implementation unless the user asks to choose first.

## Production Checklist (Non-Trivial Only)

Before implementing, cover:
- Auth/security boundary impact.
- Failure modes (timeouts, retries, fallback/explicit failure behavior).
- Observability (logs, traces, metrics as appropriate).
- Cost impact (runtime and service usage implications).
- Rollout/rollback approach.

## Azure vs Ponytail Tie-Breaker

When Azure-first and minimum-code conflict:
- Prefer local/platform-minimal approaches for internal, low-risk, single-service concerns.
- Prefer Azure managed services when requirements involve security boundaries, shared state, durability, scale-out, or cross-service integration.

## Goal

Build and maintain an Azure-native RAG system:
- Backend: FastAPI + Microsoft Agent Framework (AG-UI streaming)
- Retrieval: Azure AI Search (hybrid + semantic)
- Generation: Azure OpenAI
- UI: Next.js + CopilotKit

## Repository Map

- `azure_rag/`
  - `api.py`: FastAPI app (`/health`, `/ready`, `/agui`)
  - `agent.py`: Agent Framework agent definition and `search_docs` tool wiring
  - `rag.py`: Retrieval and grounded response orchestration
  - `readiness.py`: dependency probes and readiness caching
  - `telemetry.py`: OpenTelemetry/Application Insights setup
  - `search_pipeline.py`: Azure AI Search indexing resources lifecycle
  - `config.py`: env-driven configuration
- `scripts/setup_azure_rag.py`: creates/updates search pipeline and runs indexer
- `tests/`: backend tests (pytest)
- `ui/`: Next.js app and CopilotKit runtime bridge
- `infra/`: Bicep and APIM policy for deployed topology

## Workflow

- Python: `uv` with Python >= 3.12
- Backend install: `uv sync`
- Backend run: `uv run uvicorn azure_rag.api:app --reload`
- Backend tests: `uv run pytest`
- UI install: `cd ui && npm ci`
- UI dev: `cd ui && npm run dev`
- UI checks: `cd ui && npm test && npm run lint && npm run build`

Run targeted tests for changed areas first, then broaden if needed.

## Project Guardrails

- Preserve managed identity/keyless assumptions; do not add API-key auth for Azure OpenAI/Search/Storage unless requested.
- Keep AG-UI contract stable (`/agui` via Agent Framework bridge for CopilotKit).
- Preserve readiness semantics (`/ready` reflects Search/OpenAI health and index availability).
- Keep retrieval citation-friendly and source-traceable.
- Keep production topology assumptions (API private behind APIM; avoid direct public API assumptions).

## Environment and Secrets

- Use `.env.example` as the committed source of expected configuration keys.
- Never commit secrets or tokens to the repository.
- Treat `.env` as local-only and mutable by developers.

## Change Strategy

- Favor minimal diffs and compatibility with existing tests.
- If touching `azure_rag/agent.py`, `azure_rag/rag.py`, or `ui/src/app/page.tsx`, verify end-to-end behavior assumptions (streaming, readiness gating, citations UI).
- Update `README.md` when behavior, setup, or architecture expectations materially change.
