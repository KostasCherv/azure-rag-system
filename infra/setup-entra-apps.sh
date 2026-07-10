#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <dev|prod> <display-name-prefix>" >&2
  exit 2
fi

environment="$1"
display_prefix="$2"
parameter_file="infra/parameters/${environment}.bicepparam"
[[ -f "infra/parameters/${environment}.local.bicepparam" ]] && parameter_file="infra/parameters/${environment}.local.bicepparam"

if [[ ! -f "$parameter_file" ]]; then
  echo "Missing parameter file: $parameter_file" >&2
  exit 2
fi

for command in az jq uuidgen perl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required." >&2
    exit 1
  fi
done

tenant_id="$(az account show --query tenantId --output tsv)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

json_escape() {
  jq -Rn --arg value "$1" '$value'
}

set_bicep_param() {
  local name="$1"
  local value="$2"
  if grep -qE "^param ${name} =" "$parameter_file"; then
    PARAM_NAME="$name" PARAM_VALUE="$value" perl -0pi -e 's/^param \Q$ENV{PARAM_NAME}\E = '\''.*'\''$/param $ENV{PARAM_NAME} = '\''$ENV{PARAM_VALUE}'\''/m' "$parameter_file"
  else
    printf "param %s = '%s'\n" "$name" "$value" >> "$parameter_file"
  fi
}

create_app_if_missing() {
  local display_name="$1"
  local existing
  existing="$(az ad app list --display-name "$display_name" --query '[0]' --output json)"
  if [[ -z "$existing" || "$existing" == "null" ]]; then
    az ad app create \
      --display-name "$display_name" \
      --sign-in-audience AzureADMyOrg \
      --output json
  else
    printf '%s\n' "$existing"
  fi
}

ensure_service_principal() {
  local app_id="$1"
  if ! az ad sp show --id "$app_id" --output none 2>/dev/null; then
    az ad sp create --id "$app_id" --output none
  fi
}

ensure_api_app() {
  local display_name="$1"
  local description="$2"
  local app app_id object_id current role_id roles_file body_file

  app="$(create_app_if_missing "$display_name")"
  app_id="$(jq -r '.appId' <<<"$app")"
  object_id="$(jq -r '.id' <<<"$app")"
  ensure_service_principal "$app_id"

  current="$(az ad app show --id "$app_id" --output json)"
  role_id="$(jq -r '.appRoles[]? | select(.value == "access_as_application") | .id' <<<"$current" | head -n 1)"
  if [[ -z "$role_id" || "$role_id" == "null" ]]; then
    role_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
  fi

  roles_file="${tmp_dir}/${app_id}-roles.json"
  jq \
    --arg role_id "$role_id" \
    --arg description "$description" \
    '(.appRoles // [] | map(select(.value != "access_as_application"))) + [{
      allowedMemberTypes: ["Application"],
      description: $description,
      displayName: "Access application",
      id: $role_id,
      isEnabled: true,
      value: "access_as_application"
    }]' <<<"$current" > "$roles_file"

  body_file="${tmp_dir}/${app_id}-patch.json"
  jq -n \
    --arg identifier_uri "api://${app_id}" \
    --slurpfile app_roles "$roles_file" \
    '{
      identifierUris: [$identifier_uri],
      api: { requestedAccessTokenVersion: 2 },
      appRoles: $app_roles[0]
    }' > "$body_file"

  az rest \
    --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${object_id}" \
    --headers "Content-Type=application/json" \
    --body @"$body_file" \
    --output none

  jq -n \
    --arg appId "$app_id" \
    --arg objectId "$object_id" \
    --arg audience "api://${app_id}" \
    --arg scope "api://${app_id}/.default" \
    --arg roleId "$role_id" \
    '{appId:$appId, objectId:$objectId, audience:$audience, scope:$scope, appRoleId:$roleId}'
}

ensure_ui_sign_in_app() {
  local display_name="$1"
  local app app_id object_id body_file
  app="$(create_app_if_missing "$display_name")"
  app_id="$(jq -r '.appId' <<<"$app")"
  object_id="$(jq -r '.id' <<<"$app")"
  ensure_service_principal "$app_id"

  body_file="${tmp_dir}/${app_id}-ui-patch.json"
  jq -n '{
    web: {
      implicitGrantSettings: {
        enableIdTokenIssuance: true
      }
    }
  }' > "$body_file"

  az rest \
    --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${object_id}" \
    --headers "Content-Type=application/json" \
    --body @"$body_file" \
    --output none

  jq -n --arg appId "$app_id" --arg objectId "$object_id" '{appId:$appId, objectId:$objectId}'
}

backend="$(ensure_api_app "${display_prefix}-backend-api" "Allows APIM managed identity to call the private FastAPI backend.")"
apim="$(ensure_api_app "${display_prefix}-apim-api" "Allows the UI managed identity to call API Management.")"
ui="$(ensure_ui_sign_in_app "${display_prefix}-ui-signin")"

backend_app_id="$(jq -r '.appId' <<<"$backend")"
apim_app_id="$(jq -r '.appId' <<<"$apim")"
ui_app_id="$(jq -r '.appId' <<<"$ui")"

set_bicep_param tenantId "$tenant_id"
set_bicep_param backendAudience "api://${backend_app_id}"
set_bicep_param backendClientId "$backend_app_id"
set_bicep_param apimAudience "api://${apim_app_id}"
set_bicep_param apimScope "api://${apim_app_id}/.default"
# The APIM policy primarily pins the deployed UI managed identity object ID. This
# client ID remains as a secondary accepted azp/appid value for non-managed clients.
set_bicep_param uiClientId "$ui_app_id"
set_bicep_param uiUserAuthClientId "$ui_app_id"

cat <<EOF
Created or updated Entra applications and patched ${parameter_file}.

Backend API app:
  appId: ${backend_app_id}
  audience: api://${backend_app_id}

APIM-facing API app:
  appId: ${apim_app_id}
  scope: api://${apim_app_id}/.default

UI sign-in app:
  appId: ${ui_app_id}

Next:
  1. Deploy the runtime with ./infra/deploy.sh.
  2. Run ./infra/configure-ui-auth.sh ${environment} <deployment-resource-group>.
EOF
