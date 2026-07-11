#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 || $# -gt 6 ]]; then
  echo "Usage: $0 <deployment-resource-group> <dev|prod> <search-resource-group> <search-service-name> [api-image] [ui-image]" >&2
  exit 2
fi

resource_group="$1"
environment="$2"
search_resource_group="$3"
search_service_name="$4"
api_image="${5:-}"
ui_image="${6:-}"
parameter_file="infra/parameters/${environment}.bicepparam"
[[ -f "infra/parameters/${environment}.local.bicepparam" ]] && parameter_file="infra/parameters/${environment}.local.bicepparam"

if [[ ! -f "$parameter_file" ]]; then
  echo "Unknown environment: $environment" >&2
  exit 2
fi

subscription_id="$(az account show --query id --output tsv)"
./infra/enable-search-identity.sh "$subscription_id" "$search_resource_group" "$search_service_name"
az bicep build --file infra/main.bicep
deployment_parameters=(
  "searchResourceGroupName=$search_resource_group"
  "searchServiceName=$search_service_name"
)
[[ -n "$api_image" ]] && deployment_parameters+=("apiImage=$api_image")
[[ -n "$ui_image" ]] && deployment_parameters+=("uiImage=$ui_image")
az deployment group create \
  --name "azure-rag-${environment}" \
  --resource-group "$resource_group" \
  --template-file infra/main.bicep \
  --parameters "$parameter_file" \
  "${deployment_parameters[@]}"
