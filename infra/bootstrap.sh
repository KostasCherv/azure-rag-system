#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 <dev> <deployment-location> [--what-if]" >&2
  exit 2
fi

environment="$1"
deployment_location="$2"
mode="${3:-deploy}"
parameter_file="infra/parameters/bootstrap-${environment}.bicepparam"
[[ -f "infra/parameters/bootstrap-${environment}.local.bicepparam" ]] && parameter_file="infra/parameters/bootstrap-${environment}.local.bicepparam"

if [[ "$environment" != "dev" ]]; then
  echo "Unknown bootstrap environment: $environment" >&2
  exit 2
fi

if [[ ! -f "$parameter_file" ]]; then
  echo "Missing parameter file: $parameter_file" >&2
  exit 2
fi

az bicep build --file infra/bootstrap.bicep

if [[ "$mode" == "--what-if" ]]; then
  az deployment sub what-if \
    --location "$deployment_location" \
    --template-file infra/bootstrap.bicep \
    --parameters "$parameter_file"
elif [[ "$mode" == "deploy" ]]; then
  az deployment sub create \
    --location "$deployment_location" \
    --template-file infra/bootstrap.bicep \
    --parameters "$parameter_file"
else
  echo "Unknown mode: $mode" >&2
  exit 2
fi
