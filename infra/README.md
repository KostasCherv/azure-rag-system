# Secure Azure deployment

## Greenfield bootstrap

For an empty subscription, start with the subscription-scope bootstrap template. It creates the Azure prerequisites that `main.bicep` intentionally treats as existing dependencies:

- deployment resource group
- Azure Container Registry
- Azure Storage account and Blob container
- Azure AI Search service with system-assigned identity
- Azure OpenAI account plus chat and embedding model deployments
- optional setup-operator RBAC for running `scripts/setup_azure_rag.py`
- optional setup-operator RBAC for Search, Blob, and Azure OpenAI setup operations

Edit `infra/parameters/bootstrap-dev.bicepparam`, especially `resourceGroupName`, `namePrefix`, model names/versions if needed, and `setupPrincipalId` if the current user or automation identity should run the setup script. Then preview and deploy:

```bash
./infra/bootstrap.sh dev switzerlandnorth --what-if
./infra/bootstrap.sh dev switzerlandnorth
```

The bootstrap outputs the ACR login server, ACR name, OpenAI endpoint, Search endpoint, Storage URL, Storage resource ID, and deployment names. Copy those values into `infra/parameters/dev.bicepparam` before deploying `main.bicep`, including `containerRegistryLoginServer`, `containerRegistryName`, and `containerRegistryResourceGroupName`. When those registry parameters are present, the runtime template grants the API and UI Container App identities `AcrPull` and configures image pulls through managed identity.

The bootstrap does not create Microsoft Entra application registrations because those are tenant objects. Use `./infra/setup-entra-apps.sh dev <display-name-prefix>` before runtime deployment, then `./infra/configure-ui-auth.sh dev <deployment-resource-group>` after runtime deployment. The second script uses the deployment outputs to add the UI redirect URI, federated credential, and managed-identity app role assignments.

The production deployment creates two Azure Container Apps environments: a public environment for the Next.js UI and a VNet-injected internal environment for FastAPI. It also creates a serverless Cosmos DB account with local/key authentication disabled and a `rag/sessions` container partitioned by `/userId`. Discussion documents expire 90 days after their last successful update. The API managed identity receives Cosmos DB Built-in Data Contributor at the account scope.

API Management Standard v2 uses outbound VNet integration and private DNS to reach the internal API. The API ingress is reachable through the internal environment load balancer but has no public path. APIM validates the UI's Entra token, applies shared caller limits to `/agui`, and replaces the inbound credential with its managed-identity token for the backend audience. Session routes accept `X-RAG-User-ID` only across this UI-service boundary; the Next.js server derives it from the Easy Auth principal rather than browser input. `/ready` requires authentication but is not charged against the expensive-query quota; `/health` is only used inside the Container Apps environment.

For constrained development subscriptions, set `useSingleContainerAppsEnvironment=true` to deploy API and UI into one public Container Apps environment. The direct API FQDN exists in that mode, but Container Apps auth still pins accepted callers to APIM's managed identity.

## Prerequisites

- An Azure subscription, deployment resource group, and permission to create role assignments on the existing Azure OpenAI, AI Search, and Storage resources.
- Azure CLI with a current Bicep CLI (`az bicep upgrade`).
- An Azure Container Registry or another registry that the Container Apps environments can pull from. Public image references work directly. For private ACR image references, set `containerRegistryLoginServer`, `containerRegistryName`, and `containerRegistryResourceGroupName` so the template can configure managed-identity pulls.
- Existing Azure OpenAI, Azure AI Search, and Storage resources. Their names, resource groups, endpoints, deployments, index, container, and storage resource ID are parameters. The deployment operator also needs permission to update the Search identity.
- Two Entra application/API definitions created by `setup-entra-apps.sh` or manually: the APIM-facing audience/scope used by the UI and the backend audience accepted by Container Apps auth.
- A third Entra app registration for interactive end-user sign-in on the public UI Container App. This is separate from the APIM-facing app used by the UI managed identity.

The UI uses its system-assigned identity through `DefaultAzureCredential`. Configure the APIM API permission/application relationship in Entra so that this identity can obtain a token for `APIM_SCOPE`. Supply the expected client application ID as `uiClientId`; the policy also pins the deployed UI service principal object ID (`oid`). Configure the APIM managed identity to obtain a token for `backendAudience`. Container Apps auth pins the APIM principal object ID.

## End-user sign-in app registration

Create a web app registration for human users of the public UI. Do not create a client secret.

1. Add a redirect URI of `https://<ui-fqdn>/.auth/login/aad/callback`, where `<ui-fqdn>` is the deployed UI Container App hostname from the `uiUrl` output.
2. Add a federated identity credential on that app registration for the UI Container App's system-assigned managed identity. Use the UI app's Entra object ID (`uiPrincipalId` output) as the subject and `api://AzureADTokenExchange` as the audience so Easy Auth can authenticate without a secret.
3. Pass the app registration's application (client) ID as `uiUserAuthClientId` in the parameter file.

The UI Container App enables Easy Auth with `RedirectToLoginPage`, Azure AD as the identity provider, and token store enabled. The UI container sets `REQUIRE_USER_AUTH=true`, and the Next.js server rejects `/api/copilotkit` requests that do not include the `x-ms-client-principal` header injected by Easy Auth.

The `configure-ui-auth.sh` script performs these post-deploy updates automatically when the signed-in identity has the required Microsoft Graph permissions.

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

Copy `infra/parameters/dev.bicepparam` to `infra/parameters/dev.local.bicepparam` (gitignored) and fill in every `replace-*`/zero UUID placeholder there — the scripts prefer `*.local.bicepparam` when present, so real tenant, subscription, and app IDs stay out of the repository. Then run:

```bash
az bicep build --file infra/main.bicep
az deployment group what-if \
  --resource-group DEPLOYMENT_RESOURCE_GROUP \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam \
  searchResourceGroupName=SEARCH_RESOURCE_GROUP \
  searchServiceName=SEARCH_SERVICE_NAME
pytest tests/test_infra_static.py -q
./infra/deploy.sh DEPLOYMENT_RESOURCE_GROUP dev SEARCH_RESOURCE_GROUP SEARCH_SERVICE_NAME
```

`deploy.sh` first calls `enable-search-identity.sh`, which reads the current identity envelope and sends an idempotent management-plane PATCH containing only the identity. For a service with user-assigned identities it uses `SystemAssigned, UserAssigned`, preserves every identity resource-ID key, and normalizes each request value to `{}` so GET-only `clientId`/`principalId` fields are never replayed. It then verifies that Azure returns a system principal ID before Bicep starts, without printing identities. Bicep treats Search as an existing resource and never PUTs it, so the deployment does not need Search SKU, scale, networking, encryption, or semantic-search settings. The script requires `jq`. If you invoke Bicep directly, run the identity script first:

```bash
./infra/enable-search-identity.sh SUBSCRIPTION_ID SEARCH_RESOURCE_GROUP SEARCH_SERVICE_NAME
```

Use a lowercase `namePrefix` of at most 28 characters, containing only letters, digits, and internal hyphens and beginning with a letter. The stable Bicep decorators enforce length; Bicep does not currently expose a stable regex decorator, so the remaining naming rules are documented and also enforced by Azure resource validation.

Do not run deployment or what-if with the example placeholders. Role assignments can take several minutes to propagate after ARM reports success; retry smoke tests after propagation rather than adding keys or broad roles.

The Search resource group and service name passed to `deploy.sh` are authoritative: the script uses them for the identity PATCH and passes the same values as explicit Bicep parameter overrides. This prevents the parameter file from directing RBAC at a different Search service than the one mutated during predeployment.

## Network and DNS notes

The API environment uses a dedicated delegated `/23` subnet. APIM Standard v2 uses a separate delegated `/24` subnet for outbound VNet integration. The template creates an Azure Private DNS zone named after the internal Container Apps environment's default domain, links it to the VNet, and maps `*` to the environment static IP. APIM therefore resolves the backend FQDN privately. The UI stays public in a separate Container Apps environment. Adjust CIDRs only to non-overlapping ranges with the same or larger subnet sizes, and connect custom/on-premises DNS forwarders to Azure DNS if they resolve this VNet.

When `useSingleContainerAppsEnvironment=true`, the internal API environment and private DNS zone are skipped. APIM routes to the authenticated API app over its public FQDN.

The predeploy PATCH enables the existing Search service's system identity without mirroring or replacing any other Search properties. Search receives only Cognitive Services OpenAI User and Storage Blob Data Reader. The API receives Cognitive Services OpenAI User, Search Index Data Reader, Storage Blob Data Contributor, Search Service Contributor, and Cosmos DB Built-in Data Contributor on the newly created account. Search Service Contributor is required because runtime readiness reads `GET /indexers/{name}/status`, which is a Search service management operation rather than an index-document read.

The setup script creates or updates the index, data source, skillset, and indexer, starts the indexer, and uploads source blobs. Run it as an operator or automation identity that independently has Search Service Contributor management permission on the Search service and Storage Blob Data Contributor on the source storage account. Those setup-operator grants are prerequisites and are not created by this runtime template; do not use an admin key as a substitute.

## Smoke checklist

1. Confirm the deployment outputs a public `uiUrl`, public APIM gateway URL, and private API FQDN.
2. Confirm direct public access to the API FQDN fails and the UI loads over HTTPS.
3. From the UI, call readiness and verify APIM returns 200 after RBAC propagation.
4. Call `/rag/ready` without a token and with the wrong audience; both must return 401.
5. Call with a valid audience but a different application/service principal; it must return 403.
6. Verify `/rag/agui` works through APIM and receives a 429 with `Retry-After` after 30 calls in 60 seconds for one caller key.
7. Verify repeated `/rag/ready` calls do not consume the AG-UI quota.
8. Inspect API, Search, Storage, and OpenAI role assignments and confirm no owner/general contributor or key-based access was introduced.
9. Create discussions as two Entra users and verify neither user can list or open the other's session IDs; verify rename/delete and a two-tab ETag conflict.

Cosmos serverless charges for consumed request units and stored data rather than provisioned throughput. Rollback can restore earlier Container App revisions without deleting the account; retained session documents remain available until their inactivity TTL expires or the user deletes them.
