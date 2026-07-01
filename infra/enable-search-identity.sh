#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <subscription-id> <search-resource-group> <search-service-name>" >&2
  exit 2
fi

subscription_id="$1"
search_resource_group="$2"
search_service_name="$3"
resource_url="https://management.azure.com/subscriptions/${subscription_id}/resourceGroups/${search_resource_group}/providers/Microsoft.Search/searchServices/${search_service_name}?api-version=2025-05-01"

# PATCH only the identity envelope. Re-running preserves all other Search settings.
az rest --method patch \
  --url "$resource_url" \
  --headers 'Content-Type=application/json' \
  --body '{"identity":{"type":"SystemAssigned"}}' \
  --output none

principal_id="$(az rest --method get --url "$resource_url" --query identity.principalId --output tsv)"
if [[ -z "$principal_id" || "$principal_id" == "null" ]]; then
  echo "Search system identity was not returned after PATCH." >&2
  exit 1
fi

echo "Search system identity ready: ${principal_id}"
