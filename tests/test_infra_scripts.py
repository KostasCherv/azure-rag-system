import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def fake_az(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "az.log"
    executable = tmp_path / "az"
    executable.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$AZ_LOG"
if [[ "$*" == "account show --query id --output tsv" ]]; then
  printf '%s\\n' '00000000-0000-0000-0000-000000000000'
elif [[ "$*" == *"--method get"* && "$*" == *"--query identity --output json"* ]]; then
  printf '%s\\n' "$CURRENT_IDENTITY_JSON"
elif [[ "$*" == *"--method patch"* ]]; then
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--body" ]]; then printf '%s' "$2" > "$PATCH_BODY_FILE"; break; fi
    shift
  done
elif [[ "$*" == *"--method get"* && "$*" == *"--query identity.principalId --output tsv"* ]]; then
  printf '%s\\n' "$SYSTEM_PRINCIPAL_ID"
fi
"""
    )
    executable.chmod(0o755)
    return executable, log


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("", {"identity": {"type": "SystemAssigned"}}),
        ({}, {"identity": {"type": "SystemAssigned"}}),
        ({"type": "SystemAssigned", "principalId": "system-object"}, {"identity": {"type": "SystemAssigned"}}),
        (
            {"type": "UserAssigned", "userAssignedIdentities": {"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uami": {}}},
            {"identity": {"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uami": {}}}},
        ),
        (
            {"type": "SystemAssigned, UserAssigned", "principalId": "system-object", "userAssignedIdentities": {"/uami": {"clientId": "client", "principalId": "principal"}}},
            {"identity": {"type": "SystemAssigned, UserAssigned", "userAssignedIdentities": {"/uami": {}}}},
        ),
    ],
)
def test_enable_search_identity_preserves_identity_modes(tmp_path: Path, current: dict | str, expected: dict) -> None:
    _, log = fake_az(tmp_path)
    patch_body = tmp_path / "patch.json"
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "AZ_LOG": str(log),
        "CURRENT_IDENTITY_JSON": current if isinstance(current, str) else json.dumps(current),
        "PATCH_BODY_FILE": str(patch_body),
        "SYSTEM_PRINCIPAL_ID": "new-system-principal",
    }
    result = subprocess.run(
        [str(ROOT / "infra/enable-search-identity.sh"), "sub", "search-rg", "search-name"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(patch_body.read_text()) == expected
    assert "new-system-principal" not in result.stdout
    assert "/uami" not in result.stdout


def test_deploy_overrides_bicep_search_target_with_predeploy_target(tmp_path: Path) -> None:
    _, log = fake_az(tmp_path)
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "AZ_LOG": str(log),
        "CURRENT_IDENTITY_JSON": "{}",
        "PATCH_BODY_FILE": str(tmp_path / "patch.json"),
        "SYSTEM_PRINCIPAL_ID": "system-principal",
    }
    subprocess.run(
        [str(ROOT / "infra/deploy.sh"), "deployment-rg", "dev", "canonical-search-rg", "canonical-search"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    commands = log.read_text().splitlines()
    deployment = next(command for command in commands if command.startswith("deployment group create"))
    assert "--name azure-rag-dev" in deployment
    assert "searchResourceGroupName=canonical-search-rg" in deployment
    assert "searchServiceName=canonical-search" in deployment


def test_deploy_accepts_immutable_image_overrides(tmp_path: Path) -> None:
    _, log = fake_az(tmp_path)
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "AZ_LOG": str(log),
        "CURRENT_IDENTITY_JSON": "{}",
        "PATCH_BODY_FILE": str(tmp_path / "patch.json"),
        "SYSTEM_PRINCIPAL_ID": "system-principal",
    }
    subprocess.run(
        [
            str(ROOT / "infra/deploy.sh"),
            "deployment-rg",
            "dev",
            "search-rg",
            "search",
            "registry/azure-rag-api:commit",
            "registry/azure-rag-ui:commit",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    deployment = next(
        command for command in log.read_text().splitlines() if command.startswith("deployment group create")
    )
    assert "apiImage=registry/azure-rag-api:commit" in deployment
    assert "uiImage=registry/azure-rag-ui:commit" in deployment
