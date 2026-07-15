#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: ./infra/destroy.sh <resource-group> <dev|prod> [--yes]

Deletes this deployment's Azure resource group and Entra app registrations.
The script reads infra/parameters/<env>.local.bicepparam when present, falling
back to infra/parameters/<env>.bicepparam.
EOF
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
  exit 2
fi

resource_group="$1"
environment="$2"
assume_yes="${3:-}"

if [[ "$environment" != "dev" && "$environment" != "prod" ]]; then
  usage
  exit 2
fi

if [[ -n "$assume_yes" && "$assume_yes" != "--yes" ]]; then
  usage
  exit 2
fi

for command in az sed; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required." >&2
    exit 1
  fi
done

parameter_file="infra/parameters/${environment}.bicepparam"
if [[ -f "infra/parameters/${environment}.local.bicepparam" ]]; then
  parameter_file="infra/parameters/${environment}.local.bicepparam"
fi

if [[ ! -f "$parameter_file" ]]; then
  echo "Missing parameter file: $parameter_file" >&2
  exit 2
fi

param_value() {
  local name="$1"
  sed -n "s/^param ${name} = '\(.*\)'$/\1/p" "$parameter_file" | tail -n 1
}

extract_app_id_from_uri() {
  local value="$1"
  printf '%s\n' "$value" | sed -n 's#^api://\([0-9A-Fa-f-][0-9A-Fa-f-]*\).*#\1#p'
}

is_uuid() {
  printf '%s\n' "$1" | grep -Eq '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'
}

require_uuid_param() {
  local name="$1"
  local value="$2"
  if ! is_uuid "$value" || [[ "$value" == "00000000-0000-0000-0000-000000000000" ]]; then
    echo "Parameter ${name} is not a real app or tenant ID in ${parameter_file}: ${value}" >&2
    exit 2
  fi
}

tenant_id="$(param_value tenantId)"
backend_client_id="$(param_value backendClientId)"
apim_client_id="$(extract_app_id_from_uri "$(param_value apimAudience)")"
ui_client_id="$(param_value uiUserAuthClientId)"
storage_resource_id="$(param_value storageResourceId)"
parameter_subscription_id="$(printf '%s\n' "$storage_resource_id" | sed -n 's#^/subscriptions/\([^/]*\)/.*#\1#p')"
parameter_resource_group="$(printf '%s\n' "$storage_resource_id" | sed -n 's#^.*/resourceGroups/\([^/]*\)/providers/.*#\1#p')"

require_uuid_param tenantId "$tenant_id"
require_uuid_param backendClientId "$backend_client_id"
require_uuid_param apimAudience "$apim_client_id"
require_uuid_param uiUserAuthClientId "$ui_client_id"
require_uuid_param storageResourceId "$parameter_subscription_id"

if [[ "$parameter_resource_group" != "$resource_group" ]]; then
  echo "Refusing to delete ${resource_group}: ${parameter_file} points at ${parameter_resource_group}." >&2
  exit 2
fi

current_subscription_id="$(az account show --query id --output tsv)"
current_tenant_id="$(az account show --query tenantId --output tsv)"
current_account="$(az account show --query user.name --output tsv)"

if [[ "$current_subscription_id" != "$parameter_subscription_id" ]]; then
  echo "Refusing to delete: active subscription ${current_subscription_id} does not match ${parameter_subscription_id} in ${parameter_file}." >&2
  exit 2
fi

if [[ "$current_tenant_id" != "$tenant_id" ]]; then
  echo "Refusing to delete: active tenant ${current_tenant_id} does not match ${tenant_id} in ${parameter_file}." >&2
  exit 2
fi

cat <<EOF
Azure RAG teardown target
  Account:        ${current_account}
  Subscription:   ${current_subscription_id}
  Tenant:         ${current_tenant_id}
  Resource group: ${resource_group}
  Parameter file: ${parameter_file}

Entra app registrations:
  backend API:    ${backend_client_id}
  APIM API:       ${apim_client_id}
  UI sign-in:     ${ui_client_id}
EOF

if [[ "$assume_yes" != "--yes" ]]; then
  printf '\nType the resource group name to destroy it: '
  read -r typed_resource_group
  if [[ "$typed_resource_group" != "$resource_group" ]]; then
    echo "Confirmation did not match. Nothing deleted." >&2
    exit 1
  fi
fi

delete_app() {
  local label="$1"
  local app_id="$2"
  if az ad app show --id "$app_id" --output none 2>/dev/null; then
    echo "Deleting Entra app registration (${label}): ${app_id}"
    az ad app delete --id "$app_id" --output none
  else
    echo "Entra app registration already absent (${label}): ${app_id}"
  fi
}

delete_app "backend API" "$backend_client_id"
delete_app "APIM API" "$apim_client_id"
delete_app "UI sign-in" "$ui_client_id"

if [[ "$(az group exists --name "$resource_group")" == "true" ]]; then
  echo "Deleting resource group: ${resource_group}"
  az group delete --name "$resource_group" --yes --no-wait
  echo "Waiting for resource group deletion to finish..."
  az group wait --name "$resource_group" --deleted
else
  echo "Resource group already absent: ${resource_group}"
fi

echo "Verifying teardown..."
if [[ "$(az group exists --name "$resource_group")" == "true" ]]; then
  echo "Resource group still exists after delete: ${resource_group}" >&2
  exit 1
fi

for app_id in "$backend_client_id" "$apim_client_id" "$ui_client_id"; do
  if az ad app show --id "$app_id" --output none 2>/dev/null; then
    echo "Entra app registration still exists after delete: ${app_id}" >&2
    exit 1
  fi
done

echo "Deleted Azure RAG resources for ${resource_group}."
