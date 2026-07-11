# Development

Local setup, project structure, Search pipeline setup, app startup, and verification commands.

## Project Structure

```text
azure_rag/
  config.py           Environment configuration and derived resource names
  search_pipeline.py  Blob upload and Azure AI Search object management
  rag.py              Hybrid retrieval, prompting, and answer generation
  api.py              FastAPI routes and request/response models
  sessions.py         Per-user Cosmos DB discussion storage and APIs
  agent.py            Agent Framework agent + search_docs tool
sample_docs/          Sample Markdown/PDF knowledge base
scripts/
  setup_azure_rag.py  Pipeline setup entry point
tests/                Backend unit tests
ui/
  src/app/            Next.js UI, provider, and CopilotKit API route
  src/lib/            Agent URL configuration and tests
main.py               Alternate setup entry point
```

## Install

Backend dependencies are locked in `uv.lock`:

```bash
uv sync
```

UI dependencies are pinned in `ui/package-lock.json`:

```bash
cd ui
npm ci
cd ..
```

## Create or Update the Search Pipeline

Run from the repository root:

```bash
uv run python scripts/setup_azure_rag.py
```

Equivalent entry point:

```bash
uv run python main.py
```

The command is designed to be rerunnable. It:

1. Uploads `sample_docs/*.md` and `sample_docs/*.pdf` to the configured Blob container.
2. Creates or updates the vector and semantic index.
3. Creates or updates the Blob data source.
4. Creates or updates the split-and-embed skillset.
5. Creates or updates the indexer.
6. Runs the indexer and polls for up to three minutes.

Resource names are derived from `AZURE_SEARCH_INDEX`:

| Object | Name pattern |
|---|---|
| Index | `<AZURE_SEARCH_INDEX>` |
| Semantic configuration | `<AZURE_SEARCH_INDEX>-semantic` |
| Data source | `<AZURE_SEARCH_INDEX>-blob-datasource` |
| Skillset | `<AZURE_SEARCH_INDEX>-skillset` |
| Indexer | `<AZURE_SEARCH_INDEX>-indexer` |

## Run the Application

Start the API in terminal 1:

```bash
uv run uvicorn azure_rag.api:app --reload
```

Start the UI in terminal 2:

```bash
cd ui
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). FastAPI documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The UI defaults to `http://127.0.0.1:8000/agui`. To use another API URL, create `ui/.env.local`:

```env
AGENT_URL=https://your-api.example.com/agui
APIM_SCOPE=api://your-apim-app-id/.default
# Optional when readiness is not AGENT_URL with terminal /agui replaced by /ready:
READY_URL=https://your-api.example.com/ready
```

Discussion persistence additionally requires `AZURE_COSMOS_ENDPOINT`, `AZURE_COSMOS_DATABASE`, and `AZURE_COSMOS_SESSIONS_CONTAINER` in the root `.env`. The local developer identity needs Cosmos DB data-plane access; keys and connection strings are not supported. Local requests use `SESSION_LOCAL_USER_ID=local-development-user` unless overridden. The container partition key is `/userId` and its default TTL is 7,776,000 seconds.

The Next.js server uses `DefaultAzureCredential` to acquire an APIM token for `APIM_SCOPE`; the scope must end in `/.default`. This supports Container Apps managed identity and the local Azure developer credential chain. `AGENT_URL`, `READY_URL`, credentials, and bearer tokens remain server-side. The browser only calls same-origin Next.js routes. The UI polls readiness every 30 seconds and enables chat only while the backend reports `ready`.

## Test and Verify

```bash
uv run pytest
cd ui
npm test
npm run lint
npm run build
```

The unit tests mock external calls. A live Azure deployment, RBAC-propagation wait, setup-script run, authenticated APIM smoke test, and private-network/DNS verification remain external checks and can incur Azure usage charges. See [`infra/README.md`](../infra/README.md) for deployment and smoke-test commands.
