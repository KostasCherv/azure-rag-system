# Secure Azure deployment

This deployment creates two Azure Container Apps environments: a public environment for the Next.js UI and a VNet-injected internal environment for FastAPI. API Management Standard v2 uses outbound VNet integration and private DNS to reach the internal API. The API ingress is reachable through the internal environment load balancer but has no public path. APIM validates the UI's Entra token, applies shared caller limits to `/query` and `/agui`, and replaces the inbound credential with its managed-identity token for the backend audience. `/ready` requires authentication but is not charged against the expensive-query quota; `/health` is only used inside the Container Apps environment.

## Prerequisites

- An Azure subscription, deployment resource group, and permission to create role assignments on the existing Azure OpenAI, AI Search, and Storage resources.
- Azure CLI with a current Bicep CLI (`az bicep upgrade`).
- An Azure Container Registry or another registry that the Container Apps environments can pull from. Public image references work directly; private registries require registry identity configuration, which this template intentionally does not infer.
- Existing Azure OpenAI, Azure AI Search, and Storage resources. Their names, resource groups, endpoints, deployments, index, container, and storage resource ID are parameters. The deployment operator also needs permission to update the Search identity.
- Two Entra application/API definitions created outside Bicep: the APIM-facing audience/scope used by the UI and the backend audience accepted by Container Apps auth. Microsoft Graph tenant objects are deliberately not created by this deployment.

The UI uses its system-assigned identity through `DefaultAzureCredential`. Configure the APIM API permission/application relationship in Entra so that this identity can obtain a token for `APIM_SCOPE`. Supply the expected client application ID as `uiClientId`; the policy also pins the deployed UI service principal object ID (`oid`). Configure the APIM managed identity to obtain a token for `backendAudience`. Container Apps auth pins the APIM principal object ID.

## Build and push images

Replace `REGISTRY`, `TAG`, and the image values in the selected parameter file:

```bash
az acr login --name REGISTRY
docker build -t REGISTRY.azurecr.io/azure-rag-api:TAG .
docker build -t REGISTRY.azurecr.io/azure-rag-ui:TAG ./ui
docker push REGISTRY.azurecr.io/azure-rag-api:TAG
docker push REGISTRY.azurecr.io/azure-rag-ui:TAG
```

No credentials or `.env` files are copied into either image. Both containers run as non-root users. The UI uses Next.js standalone output; the API starts Uvicorn on `0.0.0.0` and honors `PORT`.

## Validate and deploy

Edit every `replace-*`/zero UUID placeholder in `infra/parameters/dev.bicepparam` or `prod.bicepparam`, then run:

```bash
az bicep build --file infra/main.bicep
pytest tests/test_infra_static.py -q
./infra/deploy.sh DEPLOYMENT_RESOURCE_GROUP dev SEARCH_RESOURCE_GROUP SEARCH_SERVICE_NAME
```

`deploy.sh` first calls `enable-search-identity.sh`, which sends an idempotent management-plane PATCH containing only `{"identity":{"type":"SystemAssigned"}}`, then verifies that Azure returns a principal ID before Bicep starts. Bicep treats Search as an existing resource and never PUTs it, so the deployment does not need Search SKU, scale, networking, encryption, or semantic-search settings. If you invoke Bicep directly, run the identity script first:

```bash
./infra/enable-search-identity.sh SUBSCRIPTION_ID SEARCH_RESOURCE_GROUP SEARCH_SERVICE_NAME
```

Use a lowercase `namePrefix` of at most 28 characters, containing only letters, digits, and internal hyphens and beginning with a letter. The stable Bicep decorators enforce length; Bicep does not currently expose a stable regex decorator, so the remaining naming rules are documented and also enforced by Azure resource validation.

Do not run deployment or what-if with the example placeholders. Role assignments can take several minutes to propagate after ARM reports success; retry smoke tests after propagation rather than adding keys or broad roles.

## Network and DNS notes

The API environment uses a dedicated delegated `/23` subnet. APIM Standard v2 uses a separate delegated `/24` subnet for outbound VNet integration. The template creates an Azure Private DNS zone named after the internal Container Apps environment's default domain, links it to the VNet, and maps `*` to the environment static IP. APIM therefore resolves the backend FQDN privately. The UI stays public in a separate Container Apps environment. Adjust CIDRs only to non-overlapping ranges with the same or larger subnet sizes, and connect custom/on-premises DNS forwarders to Azure DNS if they resolve this VNet.

The predeploy PATCH enables the existing Search service's system identity without mirroring or replacing any other Search properties. Search receives only Cognitive Services OpenAI User and Storage Blob Data Reader. The API receives Cognitive Services OpenAI User, Search Index Data Reader, Storage Blob Data Contributor, and Search Service Contributor. The last role is required because runtime readiness reads `GET /indexers/{name}/status`, which is a Search service management operation rather than an index-document read.

The setup script creates or updates the index, data source, skillset, and indexer, starts the indexer, and uploads source blobs. Run it as an operator or automation identity that independently has Search Service Contributor management permission on the Search service and Storage Blob Data Contributor on the source storage account. Those setup-operator grants are prerequisites and are not created by this runtime template; do not use an admin key as a substitute.

## Smoke checklist

1. Confirm the deployment outputs a public `uiUrl`, public APIM gateway URL, and private API FQDN.
2. Confirm direct public access to the API FQDN fails and the UI loads over HTTPS.
3. From the UI, call readiness and verify APIM returns 200 after RBAC propagation.
4. Call `/rag/ready` without a token and with the wrong audience; both must return 401.
5. Call with a valid audience but a different application/service principal; it must return 403.
6. Verify `/rag/query` and `/rag/agui` work through APIM and receive a 429 with `Retry-After` after 30 calls in 60 seconds for one caller key.
7. Verify repeated `/rag/ready` calls do not consume the query quota.
8. Inspect API, Search, Storage, and OpenAI role assignments and confirm no owner/general contributor or key-based access was introduced.
