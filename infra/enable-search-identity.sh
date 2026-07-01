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

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to preserve the existing Search identity envelope." >&2
  exit 1
fi

current_identity="$(az rest --method get --url "$resource_url" --query identity --output json)"
user_assigned_identities="$(jq -ce '.userAssignedIdentities // {}' <<<"$current_identity")"
has_user_assigned="$(jq -r '((.type // "") | contains("UserAssigned")) or ((.userAssignedIdentities // {}) | length > 0)' <<<"$current_identity")"

if [[ "$has_user_assigned" == "true" ]]; then
  patch_body="$(jq -cn --argjson identities "$user_assigned_identities" \
    '{identity:{type:"SystemAssigned, UserAssigned",userAssignedIdentities:$identities}}')"
else
  patch_body='{"identity":{"type":"SystemAssigned"}}'
fi

# PATCH only the identity envelope. Preserve any user-assigned identity map.
az rest --method patch \
  --url "$resource_url" \
  --headers 'Content-Type=application/json' \
  --body "$patch_body" \
  --output none

principal_id="$(az rest --method get --url "$resource_url" --query identity.principalId --output tsv)"
if [[ -z "$principal_id" || "$principal_id" == "null" ]]; then
  echo "Search system identity was not returned after PATCH." >&2
  exit 1
fi

echo "Search system identity is ready."
