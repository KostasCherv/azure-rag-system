#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 <deployment-resource-group> <dev|prod> <search-resource-group> <search-service-name>" >&2
  exit 2
fi

resource_group="$1"
environment="$2"
search_resource_group="$3"
search_service_name="$4"
parameter_file="infra/parameters/${environment}.bicepparam"

if [[ ! -f "$parameter_file" ]]; then
  echo "Unknown environment: $environment" >&2
  exit 2
fi

subscription_id="$(az account show --query id --output tsv)"
./infra/enable-search-identity.sh "$subscription_id" "$search_resource_group" "$search_service_name"
az bicep build --file infra/main.bicep
az deployment group create \
  --resource-group "$resource_group" \
  --template-file infra/main.bicep \
  --parameters "$parameter_file"
