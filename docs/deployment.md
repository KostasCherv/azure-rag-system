# Deployment

Use this runbook for greenfield bootstrap, existing-resource deployment, Azure parameters, authentication, and RBAC. Commands assume they are run from the repository root.

## Deployment Prerequisites

Follow these steps before running the production-style deployment.

### GitHub Actions production deployment

`.github/workflows/ci-cd.yml` validates only the affected API, UI, and infrastructure components on pull requests. A successful push to `main` publishes changed images with the commit SHA as the immutable tag and automatically deploys them through the protected `production` GitHub environment. Documentation-only changes do not redeploy the runtime.

Create a GitHub environment named `production` and add these environment variables:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | Client ID of the CI deployment app or managed identity |
| `AZURE_TENANT_ID` | Production Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Production Azure subscription ID |
| `AZURE_RESOURCE_GROUP` | Resource group containing the runtime deployment |
| `AZURE_SEARCH_RESOURCE_GROUP` | Resource group containing Azure AI Search |
| `AZURE_SEARCH_SERVICE_NAME` | Existing Search service name |
| `AZURE_ACR_NAME` | Azure Container Registry resource name |
| `AZURE_ACR_LOGIN_SERVER` | Registry login server, such as `example.azurecr.io` |
| `AZURE_API_CONTAINER_APP` | Production API Container App name |
| `AZURE_UI_CONTAINER_APP` | Production UI Container App name |

Configure a federated identity credential with issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, and subject `repo:<owner>/<repository>:environment:production`. Do not create a client secret. Grant the deployment identity `AcrPush` and `Container Registry Tasks Contributor` on ACR, permission to update the two Container Apps and the deployment resource group, permission to update the Search service identity, and permission to create the role assignments declared by Bicep on the referenced OpenAI, Search, Storage, and ACR scopes. Scope these grants to the listed resources instead of the subscription whenever possible.

Replace every placeholder in `infra/parameters/prod.bicepparam` before enabling deployment. The workflow overrides `apiImage` and `uiImage` with newly built or currently deployed images, so an infrastructure-only release cannot roll the applications back to the example tags in the parameter file.

Protect `main`, require pull requests, and make the `CI gate` check mandatory. The production job has its own concurrency group and cancels an older in-progress release when a newer valid commit arrives. Add required reviewers to the `production` environment only if deployments should pause for manual approval.

For the shortest path in a new development subscription, use the end-to-end wrapper after reviewing the prerequisites below:

```bash
./infra/setup-all.sh dev switzerlandnorth <name-prefix>
```

The wrapper bootstraps Azure resources, creates Entra apps, builds and pushes images, deploys the runtime, finishes UI auth, and runs the Search pipeline setup. By default, dev uses one public Container Apps environment because some subscriptions allow only one environment; direct API access is still protected by Container Apps auth and APIM remains the intended UI path. Set `USE_SINGLE_CONTAINER_APPS_ENVIRONMENT=false` only when your subscription supports the two-environment private API topology.

The remaining sections describe each step and the permissions that can still block automation.

1. Install local tools.

   ```bash
   az version
   az bicep version
   jq --version
   uv --version
   node --version
   npm --version
   docker --version
   ```

   Required versions and tools:

   | Tool | Purpose |
   |---|---|
   | Python 3.12+ and `uv` | Backend setup, tests, and Search pipeline setup |
   | Node.js compatible with Next.js 16 and `npm` | UI build and tests |
   | Azure CLI with Bicep CLI | Azure deployment |
   | `jq` | Safe Search identity patching in `infra/deploy.sh` |
   | Docker | API/UI image build |

2. Sign in to the target Azure tenant and subscription.

   ```bash
   az login
   az account set --subscription <subscription-id>
   az account show --query '{subscription:id, tenant:tenantId, user:user.name}' --output table
   ```

   The deploying identity needs permission to create resource groups, managed identities, role assignments, APIM, Container Apps, ACR, Storage, Azure AI Search, and Azure OpenAI resources. For existing-resource deployment, it also needs permission to enable the Search system identity and assign the documented RBAC roles.

3. Confirm Azure quota and regional availability.

   The bootstrap uses `switzerlandnorth` by default. Confirm the region supports:

   - Azure OpenAI account creation.
   - The configured chat model, default `gpt-5.1` version `2025-11-13`.
   - The configured embedding model, default `text-embedding-3-small` version `1`.
   - Azure AI Search with semantic ranking.
   - API Management Standard v2.
   - Azure Container Apps.
   - At least one Container Apps managed environment. The production two-environment topology requires quota for two environments; the dev wrapper defaults to a one-environment fallback.

   If a model/version is unavailable, edit `infra/parameters/bootstrap-dev.bicepparam` before deploying.

4. Choose one dependency path.

   For an empty subscription, bootstrap the Azure dependencies:

   ```bash
   ./infra/bootstrap.sh dev switzerlandnorth --what-if
   ./infra/bootstrap.sh dev switzerlandnorth
   ```

   For an existing Azure environment, skip bootstrap and collect these values manually:

   | Value | Used in |
   |---|---|
   | Azure OpenAI endpoint/resource name/resource group | `infra/parameters/dev.bicepparam` |
   | Chat and embedding deployment names | `infra/parameters/dev.bicepparam` |
   | Azure AI Search endpoint/service name/resource group | `infra/parameters/dev.bicepparam` and `infra/deploy.sh` |
   | Search index name | `.env` and `infra/parameters/dev.bicepparam` |
   | Storage account URL/name/resource group/resource ID | `.env` and `infra/parameters/dev.bicepparam` |
   | Blob container name | `.env` and `infra/parameters/dev.bicepparam` |
   | ACR login server/name/resource group, if private | `infra/parameters/dev.bicepparam` |

5. Create Microsoft Entra app registrations.

   Bicep does not create these tenant objects, but the repo includes an Azure CLI/Microsoft Graph helper:

   ```bash
   ./infra/setup-entra-apps.sh dev <display-name-prefix>
   ```

   The script creates or updates:

   | App registration | Purpose | Parameter |
   |---|---|---|
   | Backend API app | Audience accepted by FastAPI Container Apps auth | `backendAudience`, `backendClientId` |
   | APIM-facing API app | Scope requested by the UI managed identity and validated by APIM | `apimAudience`, `apimScope`, `uiClientId` |
   | End-user UI sign-in app | Browser login through Container Apps Easy Auth | `uiUserAuthClientId` |

   It also patches `infra/parameters/dev.bicepparam` with the created app IDs, audiences, and scopes. The signed-in identity still needs tenant permission to create app registrations and service principals.

6. Build and push container images.

   Use the ACR login server from bootstrap or your existing registry:

   ```bash
   az acr login --name <acr-name>
   docker build -t <acr-login-server>/azure-rag-api:<tag> .
   docker build -t <acr-login-server>/azure-rag-ui:<tag> ./ui
   docker push <acr-login-server>/azure-rag-api:<tag>
   docker push <acr-login-server>/azure-rag-ui:<tag>
   ```

7. Fill deployment parameters.

   Edit `infra/parameters/dev.bicepparam` and replace every placeholder:

   - `tenantId`
   - `apiImage`, `uiImage`
   - `containerRegistryLoginServer`, `containerRegistryName`, `containerRegistryResourceGroupName` for private ACR images
   - Entra audience/client/scope parameters
   - OpenAI, Search, and Storage parameters
   - APIM publisher name/email

   Then preview the runtime deployment:

   ```bash
   az deployment group what-if \
     --resource-group <deployment-resource-group> \
     --template-file infra/main.bicep \
     --parameters infra/parameters/dev.bicepparam \
     searchResourceGroupName=<search-resource-group> \
     searchServiceName=<search-service-name>
   ```

8. Configure local `.env` for Search pipeline setup.

   Copy `.env.example` to `.env`, then use the same OpenAI/Search/Storage values from the parameter file. No API keys or storage connection strings are required.

9. Run validation before live deployment.

   ```bash
   az bicep build --file infra/bootstrap.bicep
   az bicep build --file infra/main.bicep
   uv run pytest
   cd ui && npm test && npm run lint && npm run build
   ```

10. Deploy the runtime and initialize the Search pipeline.

    ```bash
    ./infra/deploy.sh <deployment-resource-group> dev <search-resource-group> <search-service-name>
    ./infra/configure-ui-auth.sh dev <deployment-resource-group>
    uv run python scripts/setup_azure_rag.py
    ```

    `configure-ui-auth.sh` reads the runtime deployment outputs, adds the UI redirect URI, creates or updates the UI app federated credential for the Container App managed identity, and assigns app roles from the APIM-facing/backend API apps to the UI/APIM managed identities.

    Role assignments can take several minutes to propagate. If readiness fails immediately after deployment, wait and retry before adding broader permissions.

## What Still Requires a Human/Admin

The scripts automate the mechanics, but they cannot bypass tenant and subscription governance:

- Someone must authenticate with `az login` or provide an automation identity.
- The identity must be allowed to create app registrations, service principals, federated credentials, and app role assignments.
- If the tenant requires admin consent or blocks user-created apps, an Entra administrator must approve or run the scripts.
- Azure OpenAI model access, quota, and regional availability must already be allowed for the subscription.
- Billing, budgets, and subscription/provider readiness may require an owner or billing admin.

## Configuration

Copy `.env.example` to `.env` and provide the resource endpoints, deployment names, and Azure resource ID. No API keys or storage connection strings are required:

```env
AZURE_OPENAI_ENDPOINT=https://<openai-resource>.openai.azure.com/openai/v1
AZURE_OPENAI_CHAT_DEPLOYMENT=Llama-3.3-70B-Instruct
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_OPENAI_EMBEDDING_MODEL=text-embedding-3-small

AZURE_SEARCH_ENDPOINT=https://rag-system.search.windows.net
AZURE_SEARCH_INDEX=<search-index>

AZURE_STORAGE_ACCOUNT_URL=https://<storage-account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=sample-docs
AZURE_STORAGE_RESOURCE_ID=/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account>
```

`AZURE_OPENAI_ENDPOINT` accepts either the Azure OpenAI resource URL or its `/openai/v1` URL. The application derives the correct URL for chat calls and Azure AI Search integrated vectorization.

`AZURE_STORAGE_ACCOUNT_URL` is used by the runtime upload API with Microsoft Entra authentication. `AZURE_STORAGE_RESOURCE_ID` is written to the Search Blob data source as a `ResourceId=...;` connection string; it identifies the account without containing a storage secret.

Keep `.env` out of source control. The checked-in `.env.example` contains resource names and placeholders only.

## Authentication

The application and setup command use `DefaultAzureCredential`. In Azure, configure a system-assigned or user-assigned managed identity on the application host. For local development, sign in with a supported developer credential such as Azure CLI (`az login`); `DefaultAzureCredential` selects the available identity automatically.

In deployed environments, the public UI Container App can require interactive Microsoft Entra sign-in through Container Apps Easy Auth. When `REQUIRE_USER_AUTH=true`, unauthenticated browser traffic is redirected to Entra, and the Next.js server rejects `/api/copilotkit` and `/api/status` requests that do not include the `x-ms-client-principal` header injected by Easy Auth. Local development keeps `REQUIRE_USER_AUTH=false` in `ui/.env.local`. Sign-out uses the Easy Auth `/.auth/logout` endpoint; the post-logout redirect URI (`/.auth/logout/complete`) is registered on the sign-in app by `configure-ui-auth.sh`.

Azure OpenAI calls use the v1 endpoint and a bearer-token provider for `https://cognitiveservices.azure.com/.default`. Azure AI Search data-plane and management REST calls request `https://search.azure.com/.default`. Blob uploads pass the same token credential directly to `BlobServiceClient`.

Azure AI Search itself uses its system-assigned managed identity for two indexing-time dependencies: reading the Blob data source and calling Azure OpenAI for vectorization and the embedding skill. The vectorizer and skillset deliberately omit both `apiKey` and `authIdentity`; omission selects the Search service's system-assigned identity.

## RBAC

Assign only the roles needed by each identity:

| Identity | Resource scope | Required role | Purpose |
|---|---|---|---|
| Application/setup managed identity | Azure AI Search service | `Search Index Data Reader` | Run retrieval queries against the index |
| Runtime API managed identity | Azure AI Search service | `Search Service Contributor` | Read indexer status for `/ready` |
| Setup managed identity | Azure AI Search service | `Search Service Contributor` | Create and update indexes, data sources, skillsets, and indexers |
| Runtime API managed identity | Storage account or source container | `Storage Blob Data Contributor` | Upload, list, and delete caller-owned documents |
| Azure AI Search system-assigned identity | Storage account or source container | `Storage Blob Data Reader` | Read source documents during indexing |
| Application/setup managed identity | Azure OpenAI resource | `Cognitive Services OpenAI User` | Generate grounded chat answers |
| Azure AI Search system-assigned identity | Azure OpenAI resource | `Cognitive Services OpenAI User` | Run query-time vectorization and index-time embedding |

If the runtime and setup command use separate managed identities, do not grant the runtime identity the setup-only contributor roles. Role assignments can take several minutes to propagate.
