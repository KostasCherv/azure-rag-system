#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <dev|prod> <deployment-resource-group> [deployment-name]" >&2
  exit 2
fi

environment="$1"
resource_group="$2"
deployment_name="${3:-azure-rag-${environment}}"
parameter_file="infra/parameters/${environment}.bicepparam"
[[ -f "infra/parameters/${environment}.local.bicepparam" ]] && parameter_file="infra/parameters/${environment}.local.bicepparam"

if [[ ! -f "$parameter_file" ]]; then
  echo "Missing parameter file: $parameter_file" >&2
  exit 2
fi

for command in az jq; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required." >&2
    exit 1
  fi
done

read_bicep_param() {
  local name="$1"
  sed -nE "s/^param ${name} = '([^']*)'/\\1/p" "$parameter_file" | head -n 1
}

tenant_id="$(az account show --query tenantId --output tsv)"
ui_signin_app_id="$(read_bicep_param uiUserAuthClientId)"
apim_app_id="$(read_bicep_param apimAudience | sed 's#^api://##')"
backend_app_id="$(read_bicep_param backendClientId)"

if [[ -z "$ui_signin_app_id" || -z "$apim_app_id" || -z "$backend_app_id" ]]; then
  echo "The parameter file is missing uiUserAuthClientId, apimAudience, or backendClientId." >&2
  exit 1
fi

outputs="$(az deployment group show \
  --resource-group "$resource_group" \
  --name "$deployment_name" \
  --query properties.outputs \
  --output json)"

ui_url="$(jq -r '.uiUrl.value // empty' <<<"$outputs")"
ui_principal_id="$(jq -r '.uiPrincipalId.value // empty' <<<"$outputs")"
apim_principal_id="$(jq -r '.apimPrincipalId.value // empty' <<<"$outputs")"

if [[ -z "$ui_url" || -z "$ui_principal_id" || -z "$apim_principal_id" ]]; then
  echo "Deployment outputs must include uiUrl, uiPrincipalId, and apimPrincipalId." >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

ui_app_object_id="$(az ad app show --id "$ui_signin_app_id" --query id --output tsv)"
redirect_uri="${ui_url%/}/.auth/login/aad/callback"
current_ui_app="$(az ad app show --id "$ui_signin_app_id" --output json)"
redirects_file="${tmp_dir}/redirects.json"
patch_file="${tmp_dir}/ui-app-patch.json"

jq --arg redirect_uri "$redirect_uri" \
  '(.web.redirectUris // []) | if index($redirect_uri) then . else . + [$redirect_uri] end' \
  <<<"$current_ui_app" > "$redirects_file"

jq -n --slurpfile redirect_uris "$redirects_file" '{
  web: {
    redirectUris: $redirect_uris[0],
    implicitGrantSettings: {
      enableIdTokenIssuance: true
    }
  }
}' > "$patch_file"

az rest \
  --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/applications/${ui_app_object_id}" \
  --headers "Content-Type=application/json" \
  --body @"$patch_file" \
  --output none

fic_file="${tmp_dir}/ui-fic.json"
fic_name="container-app-ui"
jq -n \
  --arg name "$fic_name" \
  --arg issuer "https://login.microsoftonline.com/${tenant_id}/v2.0" \
  --arg subject "$ui_principal_id" \
  '{
    name: $name,
    issuer: $issuer,
    subject: $subject,
    description: "Trust the deployed UI Container App managed identity.",
    audiences: ["api://AzureADTokenExchange"]
  }' > "$fic_file"

if az ad app federated-credential list --id "$ui_signin_app_id" --query "[?name=='${fic_name}'] | [0].name" --output tsv | grep -qx "$fic_name"; then
  az ad app federated-credential update \
    --id "$ui_signin_app_id" \
    --federated-credential-id "$fic_name" \
    --parameters "$fic_file" \
    --output none
else
  az ad app federated-credential create \
    --id "$ui_signin_app_id" \
    --parameters "$fic_file" \
    --output none
fi

assign_app_role() {
  local principal_id="$1"
  local resource_app_id="$2"
  local label="$3"
  local resource_sp_id role_id assignments existing assignment_file

  resource_sp_id="$(az ad sp show --id "$resource_app_id" --query id --output tsv)"
  role_id="$(az ad app show --id "$resource_app_id" --query "appRoles[?value=='access_as_application'].id | [0]" --output tsv)"
  if [[ -z "$resource_sp_id" || -z "$role_id" ]]; then
    echo "Missing service principal or app role for ${label}." >&2
    exit 1
  fi

  assignments="$(az rest \
    --method GET \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${principal_id}/appRoleAssignments" \
    --output json)"
  existing="$(jq -r --arg resource_sp_id "$resource_sp_id" --arg role_id "$role_id" \
    '.value[]? | select(.resourceId == $resource_sp_id and .appRoleId == $role_id) | .id' \
    <<<"$assignments" | head -n 1)"
  if [[ -n "$existing" && "$existing" != "null" ]]; then
    return
  fi

  assignment_file="${tmp_dir}/${label}-assignment.json"
  jq -n \
    --arg principal_id "$principal_id" \
    --arg resource_sp_id "$resource_sp_id" \
    --arg role_id "$role_id" \
    '{principalId:$principal_id, resourceId:$resource_sp_id, appRoleId:$role_id}' \
    > "$assignment_file"

  az rest \
    --method POST \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${principal_id}/appRoleAssignments" \
    --headers "Content-Type=application/json" \
    --body @"$assignment_file" \
    --output none
}

assign_app_role "$ui_principal_id" "$apim_app_id" "ui-to-apim"
assign_app_role "$apim_principal_id" "$backend_app_id" "apim-to-backend"

cat <<EOF
Configured UI authentication for ${ui_url}.

Updated:
  redirect URI: ${redirect_uri}
  federated credential subject: ${ui_principal_id}
  UI managed identity app role assignment to APIM-facing API
  APIM managed identity app role assignment to backend API
EOF
