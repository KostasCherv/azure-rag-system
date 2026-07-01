import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
INFRA = ROOT / "infra"


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_container_images_are_production_oriented() -> None:
    api = read("Dockerfile")
    ui = read("ui/Dockerfile")
    assert "USER app" in api
    assert 'CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]' in api
    assert "FROM node:22-alpine AS runner" in ui
    assert "USER nextjs" in ui
    assert 'CMD ["node", "server.js"]' in ui
    assert "output: \"standalone\"" in read("ui/next.config.ts")


def test_private_backend_and_public_ui_are_separate() -> None:
    apps = read("infra/modules/container-apps.bicep")
    network = read("infra/modules/network.bicep")
    assert "internal: true" in apps
    assert "internal: false" in apps
    assert "external: true" in apps
    assert "Microsoft.App/managedEnvironments" in apps
    assert "Microsoft.Network/privateDnsZones" in read("infra/modules/private-dns.bicep")
    assert "Microsoft.Network/virtualNetworks/subnets" in network


def test_required_app_settings_and_identities_are_declared() -> None:
    apps = read("infra/modules/container-apps.bicep")
    for setting in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_INDEX",
        "AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_STORAGE_CONTAINER",
        "AZURE_STORAGE_RESOURCE_ID",
        "AGENT_URL",
        "READY_URL",
        "APIM_SCOPE",
    ):
        assert setting in apps
    all_bicep = "\n".join(path.read_text() for path in INFRA.rglob("*.bicep"))
    assert all_bicep.count("type: 'SystemAssigned'") == 3
    search_identity_script = read("infra/enable-search-identity.sh")
    assert '"identity":{"type":"SystemAssigned"}' in search_identity_script
    assert "SystemAssigned, UserAssigned" in search_identity_script
    assert "allowedPrincipals" in apps
    assert "backendAudience" in apps
    assert "openIdIssuer" in apps


def test_rbac_is_least_privilege_and_complete() -> None:
    rbac = "\n".join(path.read_text() for path in (INFRA / "modules").glob("rbac-*.bicep"))
    required_role_ids = {
        "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",  # Cognitive Services OpenAI User
        "1407120a-92aa-4202-b7e9-c0e197c71c8f",  # Search Index Data Reader
        "7ca78c08-252a-4471-8644-bb5ff32d4ba0",  # Search Service Contributor
        "ba92f5b4-2d11-453d-a403-e96b0029c9fe",  # Storage Blob Data Contributor
        "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",  # Storage Blob Data Reader
    }
    assert required_role_ids <= set(rbac.split("'"))
    assert "Owner" not in rbac
    assert "Contributor'" not in rbac


def test_apim_policy_authenticates_and_limits_expensive_routes() -> None:
    policy = read("infra/policies/api-policy.xml")
    assert "validate-azure-ad-token" in policy
    assert "authentication-managed-identity" in policy
    assert "<authenticate-managed-identity" not in policy
    assert "rate-limit-by-key" in policy and 'calls="30"' in policy and 'renewal-period="60"' in policy
    assert "quota-by-key" in policy and 'calls="500"' in policy and 'renewal-period="86400"' in policy
    assert "oid" in policy and "appid" in policy and "azp" in policy
    assert policy.count('retry-after-header-name="Retry-After"') == 1
    quota_line = next(line for line in policy.splitlines() if "<quota-by-key" in line)
    assert "retry-after-header-name" not in quota_line
    assert "context.Operation.Id == &quot;query&quot; || context.Operation.Id == &quot;agui&quot;" in policy
    assert "backendAudience" in policy
    assert "api-key" not in policy.lower()


def test_routes_and_standard_v2_apim_are_deployed() -> None:
    apim = read("infra/modules/apim.bicep")
    service = read("infra/modules/apim-service.bicep")
    for route in ("query", "agui", "ready"):
        assert f"name: '{route}'" in apim
    assert "StandardV2" in service
    assert "virtualNetworkType: 'External'" in service
    assert "Microsoft.ApiManagement/service/apis/policies" in apim


def test_templates_have_no_secret_or_api_key_parameters() -> None:
    bicep = "\n".join(path.read_text() for path in INFRA.rglob("*.bicep"))
    forbidden = ("param clientSecret", "param apiKey", "listKeys(", "secretRef:", "value: *")
    assert not any(value.lower() in bicep.lower() for value in forbidden)


def test_docs_explain_runtime_and_setup_search_management_permissions() -> None:
    docs = read("infra/README.md")
    assert "Search Service Contributor" in docs
    assert "setup script" in docs.lower()
    assert "management permission" in docs.lower()


def test_search_is_existing_and_compiled_template_does_not_put_search() -> None:
    main = read("infra/main.bicep")
    assert "resource existingSearch 'Microsoft.Search/searchServices@" in main
    assert "existing =" in main
    assert "search-identity.bicep" not in main

    built = subprocess.run(
        ["az", "bicep", "build", "--file", str(INFRA / "main.bicep"), "--stdout"],
        check=True,
        capture_output=True,
        text=True,
    )
    template = json.loads(built.stdout)

    def resource_types(value: object) -> list[str]:
        if isinstance(value, dict):
            found = [value["type"]] if isinstance(value.get("type"), str) else []
            return found + [item for child in value.values() for item in resource_types(child)]
        if isinstance(value, list):
            return [item for child in value for item in resource_types(child)]
        return []

    assert "Microsoft.Search/searchServices" not in resource_types(template)


def test_search_identity_predeploy_uses_scoped_patch_and_verifies_principal() -> None:
    script = read("infra/enable-search-identity.sh")
    assert "az rest --method patch" in script
    assert "identity" in script and "SystemAssigned" in script
    assert "--method put" not in script.lower()
    assert '--body "$patch_body"' in script
    assert "userAssignedIdentities" in script
    assert '"properties"' not in script
    assert "identity.principalId" in script
    assert "exit 1" in script
    deploy = read("infra/deploy.sh")
    assert deploy.index("./infra/enable-search-identity.sh") < deploy.index("az bicep build")


def test_name_prefix_is_bounded_and_validated_for_container_apps() -> None:
    main = read("infra/main.bicep")
    assert "@maxLength(28)" in main
    assert "Lowercase letters, digits, and internal hyphens only" in main
    # Bicep has no stable regex decorator; assertions are still experimental.
    assert "assert namePrefix" not in main


def test_root_readme_describes_deployed_security_and_remaining_prerequisites() -> None:
    docs = read("README.md")
    assert "API Management Standard v2" in docs
    assert "30 calls per 60 seconds" in docs
    assert "500 calls per day" in docs
    assert "Bicep" in docs
    assert "end-user authentication and authorization are intentionally absent" not in docs
    assert "There is no rate limiting" not in docs
    assert "underlying Azure infrastructure is manually provisioned" not in docs
    assert "app registrations" in docs.lower()
    assert "live Azure deployment" in docs
