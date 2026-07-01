# Azure AI Search RAG Demo

Azure-native RAG demo using:

- Azure Blob Storage for source documents
- Azure AI Search data source, skillset, indexer, vector index, semantic ranking, and hybrid search
- Azure OpenAI embedding deployment through Azure AI Search integrated vectorization
- Azure OpenAI chat deployment for final grounded answers
- FastAPI for the query API

## Required `.env`

```env
AZURE_OPENAI_ENDPOINT=https://kostas-demo-rag-resource.openai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_CHAT_DEPLOYMENT=Llama-3.3-70B-Instruct
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

AZURE_SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
AZURE_SEARCH_API_KEY=...
AZURE_SEARCH_INDEX=kostas-demo-rag-index

AZURE_STORAGE_CONNECTION_STRING=...
AZURE_STORAGE_CONTAINER=sample-docs
```

Your Azure OpenAI endpoint may be either the resource URL or the `/openai/v1`
URL. The app normalizes it for both OpenAI chat calls and Azure AI Search
integrated vectorization.

## Setup Azure AI Search Pipeline

This uploads `sample_docs/*.md` to your Blob container, creates/updates the
Azure AI Search index, creates a Blob data source, creates a skillset with text
splitting and Azure OpenAI embeddings, creates an indexer, and runs it.

```bash
uv run python scripts/setup_azure_rag.py
```

Equivalent:

```bash
uv run python main.py
```

## Run API

```bash
uv run uvicorn azure_rag.api:app --reload
```

Query:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the Premium support response time?","top":5}'
```

FastAPI docs are available at:

```text
http://127.0.0.1:8000/docs
```

## Production Extensions

- Use managed identity/RBAC instead of API keys and storage connection strings.
- Put Azure AI Search behind private endpoints and restrict network access.
- Add Azure AI Search semantic answers/captions to the API response.
- Add Azure AI Document Intelligence or Content Understanding for PDFs, scans,
  tables, forms, and layout-aware chunking.
- Add Blob indexer schedule and monitoring for indexing failures.
- Add Application Insights tracing for retrieval latency, answer latency,
  source count, and empty retrieval rates.
- Add evaluation datasets for groundedness, citation quality, and retrieval
  recall.
- Add user auth, rate limiting, tenant filters, and document-level ACL filters.
- Split dev/prod infrastructure through Bicep or Terraform.
