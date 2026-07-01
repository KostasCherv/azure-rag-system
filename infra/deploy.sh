#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <resource-group> <dev|prod>" >&2
  exit 2
fi

resource_group="$1"
environment="$2"
parameter_file="infra/parameters/${environment}.bicepparam"

if [[ ! -f "$parameter_file" ]]; then
  echo "Unknown environment: $environment" >&2
  exit 2
fi

az bicep build --file infra/main.bicep
az deployment group create \
  --resource-group "$resource_group" \
  --template-file infra/main.bicep \
  --parameters "$parameter_file"
