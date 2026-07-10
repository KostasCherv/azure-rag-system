# Scope and Roadmap

## Current Scope and Limitations

- APIM authenticates the deployed UI workload identity/application. Per-user authorization and tenant/document ACL enforcement are not implemented.
- Bicep provisions the application network, Container Apps, APIM, identities, policies, and RBAC. Search, OpenAI/model deployments, Storage, Entra app registrations, and the deployment resource group remain prerequisites.
- Indexing is manually triggered and has no recurring schedule.
- The index schema is specialized for extracted text; there is no layout-aware PDF, image, table, or OCR processing.
- Retrieval has no tenant, user, ACL, or metadata filters.
- `/agui` is the only chat endpoint and is hosted by Agent Framework AG-UI streaming; the agent decides when to call `search_docs`.
- Client disconnect cancellation of upstream generation is not implemented yet.
- The liveness endpoint is process-only; `/ready` performs cached downstream readiness probes.
- APIM rate-limits and quotas `/agui`; application-level retry policy, circuit breaker, response cache, evaluation harness, and telemetry remain outstanding.
- The project uses the preview Azure AI Search API version configured in `AppConfig`; preview contracts can change.

## Production Roadmap

### Delivered

- APIM and Entra workload authentication protect `/agui` and `/ready`; APIM applies a shared 30-request/minute rate limit and 500-request/day quota to AG-UI traffic.
- Managed identities replace application API keys for OpenAI, Search, and Storage. Search-integrated vectorization, skillsets, and Blob ingestion are also keyless.
- `/health` provides process liveness, while cached `/ready` probes Search document count, OpenAI availability, and the latest indexer result with correct 200/503 semantics.
- The UI reports live readiness and indexer status, removes stale connection state, and gates chat until dependencies are ready.
- Bicep and deployment scripts define the split public/private Container Apps topology, APIM Standard v2 integration, private DNS, Easy Auth, identities, and RBAC.
- Backend, UI, APIM-policy, deployment-script, and generated-infrastructure behavior have local automated coverage.

### Next

| Priority | Addition | Exit criterion |
|---|---|---|
| P0 | Live Azure deployment and automated smoke suite | Prove VNet integration, private DNS, Easy Auth, RBAC propagation, managed-identity calls, readiness, and APIM throttling in the target subscription |
| P0 | Per-user authorization and request-size limits | Authorization and quotas are attributable to a user or tenant rather than only the UI workload |
| P0 | Private endpoints for Search, OpenAI, Storage, and the image registry | Every dependency is reachable only through approved private network paths, including managed-identity image pulls |
| P1 | Scheduled ingestion, deletion handling, dead-letter workflow, and alerting | Content stays synchronized automatically and failed documents produce actionable alerts |
| P1 | Application Insights and OpenTelemetry | Dashboards expose retrieval/generation latency, token use, dependency failures, empty results, and readiness history |
| P1 | Resilience controls | Retries, backoff, circuit breaking, and concurrency limits handle Azure throttling without cascading failures |
| P1 | Document ACL and tenant filters | Search enforces tenant/user access constraints before chunks reach the model |
| P1 | Evaluation datasets and CI gates | CI tracks retrieval recall, groundedness, citation correctness, latency, and cost against explicit thresholds |
| P1 | Client cancellation | Disconnects cancel upstream Agent Framework / OpenAI generation |
| P2 | Layout-aware document ingestion | PDFs, scans, forms, tables, and images are processed through Document Intelligence or Content Understanding |
| P2 | Richer source metadata | Responses expose semantic captions/answers and useful document/page locations |
| P2 | Conversation persistence and feedback | Multi-turn state, audit history, and user feedback survive individual requests |
| P2 | Caching and duplicate-content detection | Repeated embedding, retrieval, and generation work is measurably reduced |

## Design Notes

- Azure AI Search performs both index-time and query-time vectorization with the same embedding deployment, avoiding embedding logic in the application.
- Hybrid retrieval combines lexical matching with vector similarity, then applies semantic reranking before generation.
- Index projections create one searchable document per chunk and skip indexing the unsplit parent document.
- The answer prompt includes numbered chunks, prior conversation turns from the current thread, and citation markers such as `[1]` and `[2]` for knowledge-base facts.
- The CopilotKit runtime is a server-side boundary between the browser and the AG-UI agent endpoint; streaming is owned by Agent Framework on `/agui`, not by custom token loops in this repo.
