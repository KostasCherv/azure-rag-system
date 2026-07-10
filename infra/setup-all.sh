#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: $0 <dev|prod> [location] [name-prefix]" >&2
  exit 2
fi

environment="$1"
location="${2:-switzerlandnorth}"
name_prefix="${3:-rag$(date +%m%d%H%M)}"

parameter_file="infra/parameters/${environment}.bicepparam"
[[ -f "infra/parameters/${environment}.local.bicepparam" ]] && parameter_file="infra/parameters/${environment}.local.bicepparam"
bootstrap_parameter_file="infra/parameters/bootstrap-${environment}.bicepparam"
[[ -f "infra/parameters/bootstrap-${environment}.local.bicepparam" ]] && bootstrap_parameter_file="infra/parameters/bootstrap-${environment}.local.bicepparam"

if [[ ! -f "$parameter_file" ]]; then
  echo "Missing parameter file: $parameter_file" >&2
  exit 2
fi

if [[ ! -f "$bootstrap_parameter_file" ]]; then
  echo "Missing parameter file: $bootstrap_parameter_file" >&2
  exit 2
fi

for command in az jq docker perl sed uv; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required." >&2
    exit 1
  fi
done

if [[ ! "$name_prefix" =~ ^[a-z][a-z0-9]{2,9}$ ]]; then
  echo "name-prefix must be 3-10 lowercase letters/digits, start with a letter, and contain no hyphen." >&2
  exit 2
fi

subscription_id="$(az account show --query id --output tsv)"
tenant_id="$(az account show --query tenantId --output tsv)"
account_user="$(az account show --query user.name --output tsv)"
setup_principal_id="$(az ad signed-in-user show --query id --output tsv)"

resource_group="${AZURE_RAG_RESOURCE_GROUP:-rg-${name_prefix}-${environment}}"
display_prefix="${AZURE_RAG_DISPLAY_PREFIX:-${name_prefix}-${environment}}"
publisher_name="${PUBLISHER_NAME:-Azure RAG Demo}"
publisher_email="${PUBLISHER_EMAIL:-${account_user}}"
image_tag="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
search_index="${AZURE_SEARCH_INDEX_NAME:-${name_prefix}-${environment}-index}"
storage_container="${AZURE_STORAGE_CONTAINER_NAME:-sample-docs}"
bootstrap_deployment_name="azure-rag-bootstrap-${environment}"

set_bicep_param() {
  local name="$1"
  local value="$2"
  if grep -qE "^param ${name} =" "$parameter_file"; then
    PARAM_NAME="$name" PARAM_VALUE="$value" perl -0pi -e 's/^param \Q$ENV{PARAM_NAME}\E = '\''.*'\''$/param $ENV{PARAM_NAME} = '\''$ENV{PARAM_VALUE}'\''/m' "$parameter_file"
  else
    printf "param %s = '%s'\n" "$name" "$value" >> "$parameter_file"
  fi
}

set_bicep_param_literal() {
  local name="$1"
  local value="$2"
  if grep -qE "^param ${name} =" "$parameter_file"; then
    PARAM_NAME="$name" PARAM_VALUE="$value" perl -0pi -e 's/^param \Q$ENV{PARAM_NAME}\E = .*/param $ENV{PARAM_NAME} = $ENV{PARAM_VALUE}/m' "$parameter_file"
  else
    printf "param %s = %s\n" "$name" "$value" >> "$parameter_file"
  fi
}

output_value() {
  local name="$1"
  jq -r --arg name "$name" '.[$name].value // empty' <<<"$bootstrap_outputs"
}

echo "Using subscription ${subscription_id} in tenant ${tenant_id}."
echo "Resource group: ${resource_group}"
echo "Name prefix: ${name_prefix}"
echo "Image tag: ${image_tag}"

echo "Registering Azure resource providers..."
for namespace in \
  Microsoft.App \
  Microsoft.ApiManagement \
  Microsoft.CognitiveServices \
  Microsoft.ContainerRegistry \
  Microsoft.Insights \
  Microsoft.ManagedIdentity \
  Microsoft.Network \
  Microsoft.OperationalInsights \
  Microsoft.Search \
  Microsoft.Storage \
  Microsoft.Web; do
  az provider register --namespace "$namespace" --wait --output none
done

echo "Bootstrapping Azure prerequisite resources..."
az bicep build --file infra/bootstrap.bicep
az deployment sub create \
  --name "$bootstrap_deployment_name" \
  --location "$location" \
  --template-file infra/bootstrap.bicep \
  --parameters "$bootstrap_parameter_file" \
  location="$location" \
  resourceGroupName="$resource_group" \
  namePrefix="$name_prefix" \
  storageContainer="$storage_container" \
  searchIndex="$search_index" \
  setupPrincipalId="$setup_principal_id" \
  setupPrincipalType="User" \
  chatDeploymentSkuName="${CHAT_DEPLOYMENT_SKU_NAME:-GlobalStandard}" \
  embeddingDeploymentSkuName="${EMBEDDING_DEPLOYMENT_SKU_NAME:-Standard}" \
  --output none

bootstrap_outputs="$(az deployment sub show \
  --name "$bootstrap_deployment_name" \
  --query properties.outputs \
  --output json)"

acr_name="$(output_value containerRegistryName)"
acr_login_server="$(output_value containerRegistryLoginServer)"
openai_endpoint="$(output_value azureOpenAIEndpoint)"
openai_name="$(output_value azureOpenAIResourceName)"
chat_deployment="$(output_value azureOpenAIChatDeployment)"
embedding_deployment="$(output_value azureOpenAIEmbeddingDeployment)"
search_endpoint="$(output_value searchEndpoint)"
search_name="$(output_value searchServiceName)"
storage_url="$(output_value storageAccountUrl)"
storage_name="$(output_value storageAccountName)"
storage_resource_id="$(output_value storageResourceId)"

if [[ -z "$acr_name" || -z "$acr_login_server" || -z "$openai_endpoint" || -z "$search_name" || -z "$storage_name" ]]; then
  echo "Bootstrap outputs are incomplete." >&2
  exit 1
fi

api_image="${acr_login_server}/azure-rag-api:${image_tag}"
ui_image="${acr_login_server}/azure-rag-ui:${image_tag}"

echo "Creating Entra app registrations..."
./infra/setup-entra-apps.sh "$environment" "$display_prefix"

echo "Patching runtime parameters from bootstrap outputs..."
set_bicep_param location "$location"
set_bicep_param publicContainerAppsLocation "${PUBLIC_CONTAINER_APPS_LOCATION:-swedencentral}"
set_bicep_param namePrefix "${name_prefix}-${environment}"
set_bicep_param apiImage "$api_image"
set_bicep_param uiImage "$ui_image"
set_bicep_param_literal useSingleContainerAppsEnvironment "${USE_SINGLE_CONTAINER_APPS_ENVIRONMENT:-true}"
set_bicep_param containerRegistryLoginServer "$acr_login_server"
set_bicep_param containerRegistryName "$acr_name"
set_bicep_param containerRegistryResourceGroupName "$resource_group"
set_bicep_param publisherName "$publisher_name"
set_bicep_param publisherEmail "$publisher_email"
set_bicep_param azureOpenAIEndpoint "$openai_endpoint"
set_bicep_param azureOpenAIResourceName "$openai_name"
set_bicep_param azureOpenAIResourceGroupName "$resource_group"
set_bicep_param azureOpenAIChatDeployment "$chat_deployment"
set_bicep_param azureOpenAIEmbeddingDeployment "$embedding_deployment"
set_bicep_param searchEndpoint "$search_endpoint"
set_bicep_param searchServiceName "$search_name"
set_bicep_param searchResourceGroupName "$resource_group"
set_bicep_param searchIndex "$search_index"
set_bicep_param storageAccountUrl "$storage_url"
set_bicep_param storageAccountName "$storage_name"
set_bicep_param storageResourceGroupName "$resource_group"
set_bicep_param storageContainer "$storage_container"
set_bicep_param storageResourceId "$storage_resource_id"

echo "Building and pushing linux/amd64 images to ACR..."
az acr login --name "$acr_name" --output none
docker buildx build --platform linux/amd64 -t "$api_image" --push .
docker buildx build --platform linux/amd64 -t "$ui_image" --push ./ui

echo "Deploying runtime infrastructure..."
az bicep build --file infra/main.bicep
./infra/deploy.sh "$resource_group" "$environment" "$resource_group" "$search_name"

echo "Finishing UI authentication and managed-identity app role assignments..."
./infra/configure-ui-auth.sh "$environment" "$resource_group"

echo "Running Search pipeline setup..."
export AZURE_OPENAI_ENDPOINT="$openai_endpoint"
export AZURE_OPENAI_CHAT_DEPLOYMENT="$chat_deployment"
export AZURE_OPENAI_EMBEDDING_DEPLOYMENT="$embedding_deployment"
export AZURE_OPENAI_EMBEDDING_MODEL="${AZURE_OPENAI_EMBEDDING_MODEL:-text-embedding-3-small}"
export AZURE_SEARCH_ENDPOINT="$search_endpoint"
export AZURE_SEARCH_INDEX="$search_index"
export AZURE_STORAGE_ACCOUNT_URL="$storage_url"
export AZURE_STORAGE_CONTAINER="$storage_container"
export AZURE_STORAGE_RESOURCE_ID="$storage_resource_id"
export AZURE_OPENAI_API_KEY=''
export AZURE_SEARCH_API_KEY=''
export AZURE_STORAGE_CONNECTION_STRING=''
export PYTHON_DOTENV_DISABLED=1
uv run python scripts/setup_azure_rag.py

ui_url="$(az deployment group show \
  --resource-group "$resource_group" \
  --name "azure-rag-${environment}" \
  --query properties.outputs.uiUrl.value \
  --output tsv)"

cat <<EOF
Done.

UI URL:
  ${ui_url}

Resource group:
  ${resource_group}

Parameter file patched:
  ${parameter_file}
EOF
