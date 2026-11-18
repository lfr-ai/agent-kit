"""Native offline and relocated-source evidence, never an Azure deployment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Final
import uuid
import zipfile

import pytest

pytestmark = pytest.mark.integration
ROOT: Final[Path] = (
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/container-apps"
)
DIGEST: Final[str] = "a" * 64
IMAGE: Final[str] = f"example.azurecr.io/sample@sha256:{DIGEST}"
GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
)
IDENTITY: Final[str] = (
    f"{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
)
SUBNET: Final[str] = (
    f"{GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
)
# Subnet IDs are positional: names equal to the "subnets" segment must not confuse them.
SUBNET_IN_SUBNETS_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/subnets"
    "/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
)
MISPLACED_SUBNETS_SEGMENT: Final[str] = (
    f"{GROUP}/providers/Microsoft.Network/virtualNetworks/subnets/apps/extra"
)
ZONE: Final[str] = (
    f"{GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.westeurope.azurecontainerapps.io"
)
PRIVATE_ENDPOINT: Final[dict[str, str]] = {
    "subnet_id": (
        f"{GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
    ),
    "private_dns_zone_id": ZONE,
}
AVAILABILITY: Final[dict[str, object]] = {
    "min_replicas": 0,
    "max_replicas": 3,
    "zone_redundant": False,
    "deletion_protection": False,
    # Null means no VNet integration; an empty string is a malformed subnet ID.
    "infrastructure_subnet_id": None,
}
PRODUCTION_AVAILABILITY: Final[dict[str, object]] = {
    **AVAILABILITY,
    "min_replicas": 2,
    "zone_redundant": True,
    "deletion_protection": True,
    "infrastructure_subnet_id": SUBNET,
}
SECRET_REFERENCE: Final[dict[str, str]] = {
    "name": "token",
    "environment_variable": "TOKEN",
    "key_vault_url": "https://example.vault.azure.net/secrets/token",
}
# Synthetic identifier shaped like the application-insights output.
CONNECTION_STRING: Final[str] = (
    "InstrumentationKey=00000000-0000-0000-0000-000000000000;"
    "IngestionEndpoint=https://westeurope-5.in.applicationinsights.azure.com/"
)
OTLP_ENDPOINT: Final[str] = "https://cloud.langfuse.com/api/public/otel"
OTLP_HEADERS: Final[dict[str, str]] = {
    "name": "otlp-headers",
    "environment_variable": "OTEL_EXPORTER_OTLP_HEADERS",
    "key_vault_url": "https://example.vault.azure.net/secrets/otlp-headers",
}
TELEMETRY_VARIABLES: Final[tuple[str, ...]] = (
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AZURE_CLIENT_ID",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
)
# DefaultAzureCredential reads these before the managed identity, so they stay reserved.
CREDENTIAL_OVERRIDE_VARIABLES: Final[tuple[str, ...]] = (
    "AZURE_CLIENT_SECRET",
    "AZURE_CLIENT_CERTIFICATE_PATH",
    "AZURE_FEDERATED_TOKEN_FILE",
)
RESERVED_VARIABLES: Final[tuple[str, ...]] = (
    *TELEMETRY_VARIABLES,
    *CREDENTIAL_OVERRIDE_VARIABLES,
)
# Synthetic Entra identifiers, not a real app registration or tenant.
CLIENT_ID: Final[str] = "22222222-2222-2222-2222-222222222222"
TENANT_ID: Final[str] = "33333333-3333-3333-3333-333333333333"
BICEP_AUTH: Final[dict[str, str]] = {
    "clientId": f"'{CLIENT_ID}'",
    "tenantId": f"'{TENANT_ID}'",
}
AUTHENTICATION: Final[dict[str, str]] = {
    "client_id": CLIENT_ID,
    "tenant_id": TENANT_ID,
}
INPUTS: Final[dict[str, object]] = {
    "resource_group_id": GROUP,
    "location": "westeurope",
    "app_name": "sample-dev",
    "environment_name": "sample-dev-env",
    "stage": "dev",
    "container_image": IMAGE,
    "availability": AVAILABILITY,
}
WORKSPACE: Final[str] = (
    "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/observability"
    "/providers/Microsoft.OperationalInsights/workspaces/shared-logs"
)
# Omission (null) is the only absent form; an empty string is a malformed ID.
WORKSPACE_ID_CASES: Final[tuple[tuple[str, str, bool], ...]] = (
    ("empty", "", False),
    ("caller_owned", WORKSPACE, True),
    ("name_only", "shared-logs", False),
    ("wrong_resource_type", IDENTITY, False),
    ("missing_name", WORKSPACE.rsplit("/", 1)[0] + "/", False),
    ("child_resource", WORKSPACE + "/tables/ContainerAppConsoleLogs", False),
    ("empty_group", WORKSPACE.replace("/observability/", "//"), False),
    ("trailing_space", WORKSPACE + " ", False),
    ("embedded_space", WORKSPACE.replace("shared-logs", "shared logs"), False),
    ("embedded_tab", WORKSPACE.replace("shared-logs", "shared\tlogs"), False),
    ("unicode_space", WORKSPACE.replace("observability", "obser\u00a0vability"), False),
)
_SECRET_URL_CASES = (
    ("https://example.vault.azure.net/secrets/token", True),
    (f"https://example.vault.azure.net/secrets/token/{'b' * 32}", True),
    ("plaintext", False),
    ("http://example.vault.azure.net/secrets/token", False),
    ("https://example.vault.azure.net.invalid/secrets/token", False),
    ("https://nested.example.vault.azure.net/secrets/token", False),
    ("https://.vault.azure.net/secrets/token", False),
    ("https://example.vault.azure.net/secrets/token/not-a-version", False),
    ("https://example.vault.azure.net/secrets/token?version=latest", False),
)

BICEP_ENDPOINT: Final[str] = (
    f"{{ subnetId: '{PRIVATE_ENDPOINT['subnet_id']}', privateDnsZoneId: '{ZONE}' }}"
)
HUB: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/hub"
    "/providers/Microsoft.Network/virtualNetworks/hub"
)
INFRASTRUCTURE_VNET: Final[str] = SUBNET.rsplit("/subnets/", 1)[0]
# Consumption workload profile pairs: cpu in 0.25 steps with twice as many GiB.
RESOURCE_CASES: Final[tuple[tuple[str, str, bool], ...]] = (
    ("0.25", "0.5Gi", True),
    ("0.5", "1Gi", True),
    ("1.25", "2.5Gi", True),
    ("4", "8Gi", True),
    ("1", "1Gi", False),
    ("1.0", "2Gi", False),
    ("4.25", "8.5Gi", False),
    ("0.3", "0.6Gi", False),
)
LINKED_NETWORK_CASES: Final[tuple[tuple[str, bool, bool], ...]] = (
    ("[]", False, True),
    (f"['{HUB}']", True, True),
    (f"['{HUB}']", False, False),
    (f"['{HUB}', '{HUB.upper()}']", True, False),
    (f"['{INFRASTRUCTURE_VNET.upper()}']", True, False),
    (f"['{SUBNET}']", True, False),
    ("['hub']", True, False),
)
PUBLIC_ACCESS_CASES: Final[tuple[tuple[str | None, bool, str, bool], ...]] = (
    (None, True, "null", True),
    ("Disabled", True, "null", True),
    ("Enabled", False, "null", True),
    ("Enabled", True, "null", False),
    ("Enabled", False, BICEP_ENDPOINT, False),
)
CUSTOM_DOMAIN_CASES: Final[tuple[tuple[str, bool, str, str | None, bool], ...]] = (
    ("null", True, BICEP_ENDPOINT, "Disabled", True),
    ("{ hostName: 'app.example.com' }", False, "null", None, True),
    (
        "{ hostName: 'app.example.com', bindCertificate: true }",
        False,
        "null",
        "Enabled",
        True,
    ),
    ("{ hostName: 'example.com' }", False, "null", None, False),
    ("{ hostName: 'App.example.com' }", False, "null", None, False),
    ("{ hostName: 'https://app.example.com' }", False, "null", None, False),
    ("{ hostName: 'app.example.com' }", True, "null", None, False),
    ("{ hostName: 'app.example.com' }", False, BICEP_ENDPOINT, None, False),
    ("{ hostName: 'app.example.com' }", False, "null", "Disabled", False),
)


def bicep_string(value: str | None) -> str:
    """Render an optional string as a Bicep literal: null or a quoted string."""
    return "null" if value is None else f"'{value}'"


def tool(name: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    candidate = Path.home() / ".azure/bin/bicep.exe"
    if name == "bicep" and candidate.is_file():
        return str(candidate)
    pytest.skip(f"Missing installed {name}; no downloads or installers attempted")


def invoke(
    name: str, cwd: Path, *args: str, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed tools, synthetic offline inputs
        [tool(name), *args],
        cwd=cwd,
        env={
            **os.environ,
            "CHECKPOINT_DISABLE": "1",
            "TF_IN_AUTOMATION": "1",
            "TF_DATA_DIR": str(cwd / ".terraform"),
            "ARM_ENABLE_PREFLIGHT": "false",
            "ARM_SKIP_PROVIDER_REGISTRATION": "true",
        },
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def passed(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Package only this composition and verify its complete byte-for-byte closure."""
    archive = tmp_path / "foundation.zip"
    files = [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and ".terraform" not in path.parts
    ]
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in files:
            bundle.write(path, path.relative_to(ROOT).as_posix())
    destination = tmp_path / "unrelated-consumer"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    for path in files:
        copied = destination / path.relative_to(ROOT)
        assert (
            hashlib.sha256(copied.read_bytes()).digest()
            == hashlib.sha256(path.read_bytes()).digest()
        )
    return destination


def test_packaged_sources_are_self_contained(relocated: Path) -> None:
    assert (relocated / "README.md").is_file()
    assert not list(relocated.rglob("*.tfstate*"))
    assert not list(relocated.rglob("azure.yaml"))
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (relocated / "terraform").glob("*.tf")
    )
    assert re.findall(r"module \w+ '([^']+)'", bicep) == ["./internal-dns.bicep"]
    # Types and guards are compile-time imports; only internal-dns is a nested deployment.
    assert set(re.findall(r"from '([^']+)'", bicep)) == {
        "./auth.bicep",
        "./environment.bicep",
        "./app.bicep",
    }
    bicep = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "bicep").glob("*.bicep"))
    )
    assert 'module "' not in terraform
    assert 'source  = "Azure/azapi"' in terraform
    assert 'version = "= 2.13.0"' in terraform
    assert "listKeys(" not in bicep
    assert "listSecrets(" not in bicep
    assert "azapi_resource_action" not in terraform
    assert "passwordSecretRef" not in bicep + terraform
    # Browser sign-in uses ID tokens only; no client secret setting is ever wired.
    assert "clientSecretSettingName" not in bicep + terraform
    assert 'response_export_values = ["*"]' not in terraform
    bicep_types = set(re.findall(r"resource \w+ '([^']+@[^']+)'", bicep))
    terraform_types = set(re.findall(r'type\s*=\s*"([^"]+@[^"]+)"', terraform))
    assert bicep_types == terraform_types


def test_bicep_native_format_lint_compile_and_policy(relocated: Path) -> None:
    directory = relocated / "bicep"
    for path in [*directory.rglob("*.bicep"), *directory.rglob("*.bicepparam")]:
        formatted = passed(invoke("bicep", directory, "format", str(path), "--stdout"))
        assert formatted == path.read_text(encoding="utf-8")
    result = invoke("bicep", directory, "lint", "main.bicep", "--no-restore")
    passed(result)
    assert not result.stderr, result.stderr
    compiled = json.loads(
        passed(
            invoke(
                "bicep", directory, "build", "main.bicep", "--no-restore", "--stdout"
            )
        )
    )
    resources = list(compiled["resources"].values())
    types = [resource["type"] for resource in resources]
    assert types.count("Microsoft.App/containerApps") == 1
    assert types.count("Microsoft.App/managedEnvironments") == 1
    assert types.count("Microsoft.OperationalInsights/workspaces") == 1
    assert types.count("Microsoft.Authorization/locks") == 4
    for resource in resources:
        if resource["type"] == "Microsoft.Authorization/locks":
            assert "scope" in resource
            assert "condition" in resource
            assert resource["properties"]["level"] == "CanNotDelete"
    assert set(compiled["outputs"]) == {
        "appResourceId",
        "environmentResourceId",
        "workspaceResourceId",
        "managedIdentityResourceId",
        "url",
        "environmentDefaultDomain",
        "privateEndpointResourceId",
        "authCallbackUrl",
        "customDomainCnameTarget",
        "customDomainTxtRecordName",
        "customDomainVerificationId",
    }
    app = next(r for r in resources if r["type"] == "Microsoft.App/containerApps")
    configuration = app["properties"]["configuration"]
    assert configuration["ingress"]["allowInsecure"] is False
    assert configuration["ingress"]["external"] is True
    assert app["identity"]["type"] == "UserAssigned"
    probes = app["properties"]["template"]["containers"][0]["probes"]
    assert [(p["type"], p["httpGet"]["path"]) for p in probes] == [
        ("Startup", "/health/live"),
        ("Liveness", "/health/live"),
        ("Readiness", "/health/ready"),
    ]
    workspace = next(
        r for r in resources if r["type"] == "Microsoft.OperationalInsights/workspaces"
    )
    assert workspace["properties"]["features"]["disableLocalAuth"] is True
    internal_dns = compiled["resources"]["internalDns"]
    assert internal_dns["condition"] == "[variables('internal')]"
    # The VNet is the subnet ID's first nine segments, never a name-based split.
    assert internal_dns["properties"]["parameters"]["networkId"] == {
        "value": (
            "[join(take(split(variables('settings').infrastructureSubnetId, '/'), 9)"
            ", '/')]"
        )
    }
    assert "defaultValue" not in compiled["parameters"]["availability"]
    assert "defaultValue" not in compiled["parameters"]["containerImage"]
    assert "requireTelemetry" in compiled["variables"]["telemetry"]
    env = app["properties"]["template"]["containers"][0]["env"]
    for name in TELEMETRY_VARIABLES:
        assert f"'{name}'" in env, name
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in env
    assert "'http/protobuf'" in env
    assert "reference(variables('checkedIdentityId'), '2024-11-30').clientId" in env
    passed(
        invoke(
            "bicep",
            directory,
            "build-params",
            "tests/dev.bicepparam",
            "--no-restore",
            "--stdout",
        )
    )


def test_bicep_sizing_linked_networks_and_custom_domain(relocated: Path) -> None:
    directory = relocated / "bicep"
    compiled = json.loads(
        passed(
            invoke(
                "bicep", directory, "build", "main.bicep", "--no-restore", "--stdout"
            )
        )
    )
    app = compiled["resources"]["app"]
    assert app["properties"]["template"]["containers"][0]["resources"] == (
        "[variables('resources')]"
    )
    assert compiled["resources"]["workspace"]["properties"]["retentionInDays"] == (
        "[parameters('logRetentionDays')]"
    )
    parameters = compiled["parameters"]
    assert parameters["cpu"]["defaultValue"] == "0.5"
    assert parameters["memory"]["defaultValue"] == "1Gi"
    assert parameters["logRetentionDays"]["defaultValue"] == 30
    assert parameters["logRetentionDays"]["minValue"] == 30
    assert parameters["logRetentionDays"]["maxValue"] == 730
    assert parameters["linkedVirtualNetworkIds"]["defaultValue"] == []
    assert parameters["customDomain"]["nullable"] is True
    certificate = compiled["resources"]["certificate"]
    assert (
        certificate["type"] == "Microsoft.App/managedEnvironments/managedCertificates"
    )
    assert certificate["condition"] == "[not(equals(variables('domain'), null()))]"
    assert certificate["properties"]["domainControlValidation"] == "CNAME"
    # The app refers to the certificate by ID only; the certificate waits for the app.
    assert "app" in certificate["dependsOn"]
    assert "certificate" not in app.get("dependsOn", [])
    internal_links = compiled["resources"]["internalDns"]["properties"]
    assert internal_links["parameters"]["linkedNetworkIds"] == {
        "value": "[variables('linkedNetworks')]"
    }
    # Bicep guid() is UUIDv5 under a fixed namespace, which Terraform uuidv5 matches.
    hub = HUB.lower()
    probe = directory / "guid.bicepparam"
    probe.write_text(f"using none\nparam checked = guid('{hub}')\n", encoding="utf-8")
    output = json.loads(
        passed(
            invoke(
                "bicep",
                directory,
                "build-params",
                probe.name,
                "--no-restore",
                "--stdout",
            )
        )
    )
    namespace = uuid.UUID("11fb06fb-712d-4ddd-98c7-e71bbd588830")
    assert json.loads(output["parametersJson"])["parameters"]["checked"]["value"] == (
        str(uuid.uuid5(namespace, hub))
    )
    terraform = (relocated / "terraform/main.tf").read_text(encoding="utf-8")
    assert f'guid_namespace = "{namespace}"' in terraform
    dns = (directory / "internal-dns.bicep").read_text(encoding="utf-8")
    assert "name: '${name}-${guid(toLower(id))}'" in dns
    assert "'foundation-protection'" in dns
    assert "deletion-protection" not in dns + terraform


@pytest.fixture
def workspace_template(relocated: Path) -> dict:
    return json.loads(
        passed(
            invoke(
                "bicep",
                relocated / "bicep",
                "build",
                "main.bicep",
                "--no-restore",
                "--stdout",
            )
        )
    )


def test_bicep_optional_inputs_and_named_probe_settings(
    workspace_template: dict,
) -> None:
    compiled = workspace_template
    parameters = compiled["parameters"]
    # Absent is null: optional strings have no '' default and reject an empty string.
    for name in (
        "existingLogAnalyticsWorkspaceResourceId",
        "existingIdentityResourceId",
        "registryServer",
        "applicationInsightsConnectionString",
        "otlpEndpoint",
    ):
        assert "defaultValue" not in parameters[name], name
        assert parameters[name]["nullable"] is True, name
        assert parameters[name]["minLength"] == 1, name
    access = parameters["publicNetworkAccess"]
    assert "defaultValue" not in access
    assert access["nullable"] is True
    assert access["allowedValues"] == ["Enabled", "Disabled"]
    for name in (
        "privateEndpointResourceId",
        "authCallbackUrl",
        "customDomainTxtRecordName",
        "customDomainVerificationId",
    ):
        assert compiled["outputs"][name]["nullable"] is True, name
    # Probe timings are one named policy, not literals repeated per probe.
    assert compiled["variables"]["probeSettings"] == {
        "startup": {"periodSeconds": 10, "timeoutSeconds": 2, "failureThreshold": 30},
        "liveness": {
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
            "timeoutSeconds": 2,
            "failureThreshold": 3,
        },
        "readiness": {
            "initialDelaySeconds": 5,
            "periodSeconds": 5,
            "timeoutSeconds": 2,
            "failureThreshold": 3,
        },
    }
    probes = compiled["resources"]["app"]["properties"]["template"]["containers"][0][
        "probes"
    ]
    timings = [
        value
        for probe in probes
        for key, value in probe.items()
        if key.endswith(("Seconds", "Threshold"))
    ]
    assert len(timings) == 11
    assert all(value.startswith("[variables('probeSettings').") for value in timings)


def _inline_bicep_variables(compiled: dict, expression: str) -> str:
    """Expand compiled aliases without interpreting ARM functions."""
    return re.sub(
        r"variables\('([^']+)'\)",
        lambda match: (
            _inline_bicep_variables(compiled, compiled["variables"][match[1]])
            .removeprefix("[")
            .removesuffix("]")
        ),
        expression,
    )


def _workspace_guard(compiled: dict) -> tuple[str, str, str]:
    assert "existingLogAnalyticsWorkspaceResourceId" in compiled["parameters"], (
        "Container Apps must expose optional existingLogAnalyticsWorkspaceResourceId"
    )
    # Discover the wired guard rather than prescribing a new helper or variable name.
    expression = _inline_bicep_variables(
        compiled, compiled["outputs"]["workspaceResourceId"]["value"]
    )
    match = re.search(
        r"(__bicep\.(\w+))\(parameters\('existingLogAnalyticsWorkspaceResourceId'\)\)",
        expression,
    )
    assert match, "The effective workspace output must use the validated caller ID"
    member = compiled["functions"][0]["members"][match[2]]
    origin = member["metadata"]["__bicep_imported_from!"]
    return (
        match[0],
        origin.get("originalSymbolName", match[2]),
        origin["sourceTemplate"],
    )


def test_bicep_workspace_reuse_owns_only_the_dedicated_workspace(
    workspace_template: dict,
) -> None:
    compiled = workspace_template
    parameter = "existingLogAnalyticsWorkspaceResourceId"
    checked, _, _ = _workspace_guard(compiled)
    assert "defaultValue" not in compiled["parameters"][parameter]
    assert compiled["parameters"][parameter]["nullable"] is True
    resources = compiled["resources"]
    owned = _inline_bicep_variables(compiled, resources["workspace"]["condition"])
    # The emitted condition, not resource presence in the template, controls ownership.
    assert owned == f"[equals({checked}, null())]", (
        "Only an omitted (null) caller workspace ID may create a dedicated workspace"
    )
    lock = _inline_bicep_variables(compiled, resources["workspaceLock"]["condition"])
    protection = _inline_bicep_variables(
        compiled, resources["environmentLock"]["condition"]
    )[1:-1]
    assert lock in {
        f"[and({protection}, {owned[1:-1]})]",
        f"[and({owned[1:-1]}, {protection})]",
    }, "Deletion protection must never lock a caller-owned workspace"
    effective = _inline_bicep_variables(
        compiled, compiled["outputs"]["workspaceResourceId"]["value"]
    )
    dedicated = (
        "resourceId('Microsoft.OperationalInsights/workspaces', "
        + (_inline_bicep_variables(compiled, resources["workspace"]["name"])[1:-1])
        + ")"
    )
    assert effective in {
        f"[coalesce({checked}, {dedicated})]",
        f"[if(equals({checked}, null()), {dedicated}, {checked})]",
        f"[if(not(equals({checked}, null())), {checked}, {dedicated})]",
    }, "The effective output must select the caller ID or the dedicated workspace ID"
    assert (
        _inline_bicep_variables(
            compiled, resources["diagnostics"]["properties"]["workspaceId"]
        )
        == effective
    ), "Diagnostics and the workspace output must use the same effective workspace"


@pytest.mark.parametrize(
    ("workspace_id", "accepted"),
    [
        pytest.param(None, True, id="null"),
        *[
            pytest.param(value, accepted, id=name)
            for name, value, accepted in WORKSPACE_ID_CASES
        ],
    ],
)
def test_bicep_workspace_id_guard(
    relocated: Path, workspace_template: dict, workspace_id: str | None, accepted: bool
) -> None:
    _, name, source = _workspace_guard(workspace_template)
    directory = relocated / "bicep"
    bicep_id = bicep_string(
        None if workspace_id is None else workspace_id.replace("\t", "\\t")
    )
    (directory / "workspace.bicepparam").write_text(
        f"using none\nimport {{ {name} }} from './{source}'\n"
        f"param checked = {name}({bicep_id})\n",
        encoding="utf-8",
    )
    result = invoke(
        "bicep",
        directory,
        "build-params",
        "workspace.bicepparam",
        "--no-restore",
        "--stdout",
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if accepted:
        parameters = json.loads(json.loads(result.stdout)["parametersJson"])
        assert parameters["parameters"]["checked"]["value"] == workspace_id
    else:
        assert "BCP" in result.stderr
        assert "workspace" in result.stderr.lower(), result.stderr


@pytest.mark.parametrize(
    ("expression", "accepted"),
    [
        (f"requireDigest('{IMAGE}')", True),
        ("requireDigest('example.azurecr.io/sample:latest')", False),
        (f"requireDigest('example.azurecr.io/sample@sha256:{'g' * 64}')", False),
        ("requireDigest('example.azurecr.io/sample@sha256:abc')", False),
        ("requireName('Valid--Name')", False),
        ("requireName('valid-name')", True),
        ("requireInternalEnvironment(false, null, null)", True),
        (f"requireInternalEnvironment(true, '{SUBNET}', null)", True),
        ("requireInternalEnvironment(true, null, null)", False),
        ("requireInternalEnvironment(true, '', null)", False),
        (
            (
                f"requireInternalEnvironment(true, '{SUBNET}', "
                f"{{ subnetId: '{SUBNET}', privateDnsZoneId: '{ZONE}' }})"
            ),
            False,
        ),
        ("requireIdentity(null, false)", True),
        ("requireIdentity(null, true)", False),
        # An empty string is a malformed ID, never "absent".
        ("requireIdentity('', false)", False),
        ("requireIdentity('', true)", False),
        (f"requireIdentity('{IDENTITY}', true)", True),
        (f"requireRegistry(null, '{IMAGE}')", True),
        (f"requireRegistry('', '{IMAGE}')", False),
        (f"requireRegistry('other.azurecr.io', '{IMAGE}')", False),
        (f"requireRegistry('example.azurecr.io', '{IMAGE}')", True),
        *[
            (
                (
                    "requireSecrets([{ name: 'token', environmentVariable: 'TOKEN', "
                    f"keyVaultUrl: '{url}' }}])"
                ),
                accepted,
            )
            for url, accepted in _SECRET_URL_CASES
        ],
        *[
            (
                (
                    "requireSecrets(["
                    "{ name: 'token', environmentVariable: 'TOKEN', "
                    "keyVaultUrl: 'https://example.vault.azure.net/secrets/token' }, "
                    f"{{ name: '{name}', environmentVariable: '{variable}', "
                    "keyVaultUrl: 'https://example.vault.azure.net/secrets/other' }])"
                ),
                False,
            )
            for name, variable in (
                ("token", "OTHER"),
                ("other", "TOKEN"),
                ("token", "TOKEN"),
            )
        ],
        ("requireTelemetry(null, null, ['OTEL_SERVICE_NAME'])", True),
        ("requireTelemetry('', null, [])", False),
        ("requireTelemetry(null, '', [])", False),
        (f"requireTelemetry('{CONNECTION_STRING}', null, [])", True),
        (
            f"requireTelemetry(null, '{OTLP_ENDPOINT}', ['OTEL_EXPORTER_OTLP_HEADERS'])",
            True,
        ),
        ("requireTelemetry('not-a-connection-string', null, [])", False),
        (
            "requireTelemetry(null, 'http://cloud.langfuse.com/api/public/otel', [])",
            False,
        ),
        (f"requireTelemetry(null, '{OTLP_ENDPOINT}', ['OTEL_SERVICE_NAME'])", False),
        (
            f"requireTelemetry('{CONNECTION_STRING}', null, ['AZURE_CLIENT_ID'])",
            False,
        ),
        (
            (
                "requireSecrets([{ name: 'client', environmentVariable: 'AZURE_CLIENT_ID', "
                "keyVaultUrl: 'https://example.vault.azure.net/secrets/client' }])"
            ),
            False,
        ),
        *[
            pytest.param(
                "requireSecrets([{ name: 'token', "
                f"environmentVariable: '{name.lower()}', "
                "keyVaultUrl: 'https://example.vault.azure.net/secrets/token' }])",
                False,
                id=f"case_reserved_secret_{name.lower()}",
            )
            for name in RESERVED_VARIABLES
        ],
        pytest.param(
            "requireSecrets(["
            "{ name: 'first', environmentVariable: 'APP_TOKEN', "
            "keyVaultUrl: 'https://example.vault.azure.net/secrets/first' }, "
            "{ name: 'second', environmentVariable: 'aPp_ToKeN', "
            "keyVaultUrl: 'https://example.vault.azure.net/secrets/second' }])",
            False,
            id="case_secret_secret_collision",
        ),
        pytest.param(
            "requireSecrets([{ name: 'password', "
            "environmentVariable: 'app_postgres_password', "
            "keyVaultUrl: 'https://example.vault.azure.net/secrets/password' }])",
            True,
            id="case_lowercase_credential_reference",
        ),
        pytest.param(
            f"requireTelemetry('{CONNECTION_STRING}', null, ['aZuRe_ClIeNt_Id'])",
            False,
            id="case_reserved_telemetry_secret",
        ),
        pytest.param(
            "requireEnvironment({ APP_VALUE: 'first', app_value: 'second' }, [])",
            False,
            id="case_plain_plain_collision",
        ),
        *[
            pytest.param(
                f"requireResources('{cpu}', '{memory}')",
                accepted,
                id=f"resources_{cpu}_{memory}",
            )
            for cpu, memory, accepted in RESOURCE_CASES
        ],
        *[
            pytest.param(
                f"requireLinkedNetworks({ids}, {str(internal).lower()}, '{SUBNET}')",
                accepted,
                id=f"linked_{index}",
            )
            for index, (ids, internal, accepted) in enumerate(LINKED_NETWORK_CASES)
        ],
        *[
            pytest.param(
                f"requirePublicNetworkAccess({bicep_string(value)}, "
                f"{str(internal).lower()}, {network})",
                accepted,
                id=f"public_access_{index}",
            )
            for index, (value, internal, network, accepted) in enumerate(
                PUBLIC_ACCESS_CASES
            )
        ],
        *[
            pytest.param(
                f"requireCustomDomain({domain}, {str(internal).lower()}, {network}, "
                f"{bicep_string(access)})",
                accepted,
                id=f"custom_domain_{index}",
            )
            for index, (domain, internal, network, access, accepted) in enumerate(
                CUSTOM_DOMAIN_CASES
            )
        ],
    ],
)
def test_bicep_native_input_guards(
    relocated: Path, expression: str, accepted: bool
) -> None:
    directory = relocated / "bicep"
    fixture = directory / "guard.bicepparam"
    fixture.write_text(
        "using none\n"
        "import { requireDigest, requireName, requireIdentity, requireRegistry, "
        "requireSecrets, requireTelemetry, requireEnvironment, requireResources "
        "} from './app.bicep'\n"
        "import { requireInternalEnvironment, requireLinkedNetworks, "
        "requirePublicNetworkAccess, requireCustomDomain } from './environment.bicep'\n"
        f"param checked = {expression}\n",
        encoding="utf-8",
    )
    result = invoke(
        "bicep", directory, "build-params", fixture.name, "--no-restore", "--stdout"
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if not accepted:
        assert "BCP" in result.stderr


@pytest.mark.parametrize(
    ("stage", "minimum", "maximum", "zones", "protection", "subnet", "accepted"),
    [
        ("dev", 0, 3, False, False, None, True),
        # An empty string is a malformed subnet ID, never "absent".
        ("dev", 0, 3, False, False, "", False),
        ("test", 1, 3, False, True, None, True),
        ("staging", 1, 3, False, True, None, False),
        ("staging", 2, 3, True, False, SUBNET, True),
        ("staging", 1, 3, True, False, SUBNET, False),
        ("staging", 2, 3, False, False, SUBNET, False),
        ("prod", 2, 10, True, True, SUBNET, True),
        ("prod", 2, 10, True, True, SUBNET_IN_SUBNETS_GROUP, True),
        ("prod", 0, 3, False, False, None, False),
        ("prod", 2, 10, True, False, SUBNET, False),
        ("prod", 1, 10, True, True, SUBNET, False),
        ("prod", 2, 10, True, True, None, False),
        ("dev", 4, 3, False, False, None, False),
        ("dev", 0, 0, False, False, None, False),
        ("dev", 0, 31, False, False, None, False),
        ("dev", 0, 3, True, False, None, False),
        ("dev", 0, 3, False, False, "not-a-subnet", False),
        ("dev", 0, 3, False, False, MISPLACED_SUBNETS_SEGMENT, False),
        ("production", 2, 10, True, True, SUBNET, False),
    ],
)
def test_bicep_native_availability_guards(
    relocated: Path,
    stage: str,
    minimum: int,
    maximum: int,
    zones: bool,
    protection: bool,
    subnet: str | None,
    accepted: bool,
) -> None:
    directory = relocated / "bicep"
    fixture = directory / "availability.bicepparam"
    fixture.write_text(
        "using none\nimport { requireAvailability } from './environment.bicep'\n"
        f"param checked = requireAvailability('{stage}', {{\n"
        f"  minReplicas: {minimum}\n  maxReplicas: {maximum}\n"
        f"  zoneRedundant: {str(zones).lower()}\n"
        f"  deletionProtection: {str(protection).lower()}\n"
        f"  infrastructureSubnetId: {bicep_string(subnet)}\n}})\n",
        encoding="utf-8",
    )
    result = invoke(
        "bicep", directory, "build-params", fixture.name, "--no-restore", "--stdout"
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("stage", "location", "network", "accepted"),
    [
        ("dev", "westeurope", "null", True),
        ("test", "westeurope", "null", True),
        ("staging", "westeurope", "null", False),
        ("staging", "westeurope", BICEP_ENDPOINT, True),
        ("prod", "westeurope", "null", False),
        (
            "prod",
            "West Europe",
            f"{{ subnetId: '{PRIVATE_ENDPOINT['subnet_id']}', privateDnsZoneId: '{ZONE}' }}",
            True,
        ),
        (
            "prod",
            "northeurope",
            f"{{ subnetId: '{PRIVATE_ENDPOINT['subnet_id']}', privateDnsZoneId: '{ZONE}' }}",
            False,
        ),
        (
            "dev",
            "westeurope",
            f"{{ subnetId: 'not-a-subnet', privateDnsZoneId: '{ZONE}' }}",
            False,
        ),
    ],
)
def test_bicep_native_private_endpoint_guard(
    relocated: Path, stage: str, location: str, network: str, accepted: bool
) -> None:
    directory = relocated / "bicep"
    fixture = directory / "endpoint.bicepparam"
    fixture.write_text(
        "using none\nimport { requirePrivateEndpoint } from './environment.bicep'\n"
        f"param checked = requirePrivateEndpoint('{stage}', '{location}', {network})\n",
        encoding="utf-8",
    )
    result = invoke(
        "bicep", directory, "build-params", fixture.name, "--no-restore", "--stdout"
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


def _bicep_value(directory: Path, expression: str) -> subprocess.CompletedProcess[str]:
    (directory / "authentication.bicepparam").write_text(
        "using none\n"
        "import { requireAuthentication, authProperties, callbackUrl } "
        "from './auth.bicep'\n"
        f"param checked = {expression}\n",
        encoding="utf-8",
    )
    return invoke(
        "bicep",
        directory,
        "build-params",
        "authentication.bicepparam",
        "--no-restore",
        "--stdout",
    )


def _bicep_authentication(**fields: object) -> str:
    entries = ", ".join(f"{k}: {v}" for k, v in {**BICEP_AUTH, **fields}.items())
    return f"{{ {entries} }}"


def test_bicep_authentication_is_optional(relocated: Path) -> None:
    directory = relocated / "bicep"
    compiled = json.loads(
        passed(
            invoke(
                "bicep", directory, "build", "main.bicep", "--no-restore", "--stdout"
            )
        )
    )
    auth = compiled["resources"]["authConfig"]
    assert auth["type"] == "Microsoft.App/containerApps/authConfigs"
    # No authentication input means no authConfigs resource is deployed.
    assert auth["condition"] == "[not(equals(variables('auth'), null()))]"
    assert auth["properties"] == "[__bicep.authProperties(variables('auth'))]"
    assert "'current'" in auth["name"]
    assert "defaultValue" not in compiled["parameters"]["authentication"]
    assert compiled["parameters"]["authentication"]["nullable"] is True


def test_bicep_authentication_modes(relocated: Path) -> None:
    directory = relocated / "bicep"

    def value(expression: str) -> object:
        output = json.loads(passed(_bicep_value(directory, expression)))
        return json.loads(output["parametersJson"])["parameters"]["checked"]["value"]

    issuer = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
    registration = {"clientId": CLIENT_ID, "openIdIssuer": issuer}
    # API mode: bearer tokens only, 401 without one, no secret or forward proxy.
    assert value(f"authProperties({_bicep_authentication()})") == {
        "platform": {"enabled": True},
        "globalValidation": {"unauthenticatedClientAction": "Return401"},
        "identityProviders": {
            "azureActiveDirectory": {"enabled": True, "registration": registration}
        },
    }
    sign_in = _bicep_authentication(
        signIn="true",
        allowedAudiences=f"['api://{CLIENT_ID}']",
        publicHostName="'app.example.com'",
    )
    properties = value(f"authProperties({sign_in})")
    assert isinstance(properties, dict)
    assert properties["globalValidation"] == {
        "unauthenticatedClientAction": "RedirectToLoginPage",
        "redirectToProvider": "azureactivedirectory",
    }
    assert properties["identityProviders"]["azureActiveDirectory"] == {
        "enabled": True,
        "registration": registration,
        "validation": {"allowedAudiences": [f"api://{CLIENT_ID}"]},
    }
    assert properties["httpSettings"] == {"forwardProxy": {"convention": "Standard"}}
    assert (
        value(f"callbackUrl({sign_in}, 'sample.example.azurecontainerapps.io')")
        == "https://app.example.com/.auth/login/aad/callback"
    )
    assert (
        value(
            f"callbackUrl({_bicep_authentication(signIn='true')}, "
            "'sample.example.azurecontainerapps.io')"
        )
        == "https://sample.example.azurecontainerapps.io/.auth/login/aad/callback"
    )
    for settings in ("null", _bicep_authentication()):
        assert value(f"callbackUrl({settings}, 'sample.example.io')") is None
    excluded = value(
        f"authProperties({_bicep_authentication(excludedPaths="['/health/ready']")})"
    )
    assert isinstance(excluded, dict)
    assert excluded["globalValidation"] == {
        "unauthenticatedClientAction": "Return401",
        "excludedPaths": ["/health/ready"],
    }


@pytest.mark.parametrize(
    ("fields", "accepted"),
    [
        ({}, True),
        ({"publicHostName": "'app.example.com'"}, True),
        ({"clientId": "'not-a-guid'"}, False),
        ({"tenantId": f"'{TENANT_ID[:-1]}'"}, False),
        ({"tenantId": f"'{TENANT_ID.replace('-', '')}0000'"}, False),
        ({"publicHostName": "'https://app.example.com'"}, False),
        ({"publicHostName": "'App.example.com'"}, False),
        ({"publicHostName": "'-app.example.com'"}, False),
        ({"publicHostName": f"'{'a' * 64}.example.com'"}, False),
        ({"excludedPaths": "['/health/ready']"}, True),
        ({"excludedPaths": "['health/ready']"}, False),
    ],
)
def test_bicep_authentication_guard(
    relocated: Path, fields: dict[str, str], accepted: bool
) -> None:
    result = _bicep_value(
        relocated / "bicep",
        f"requireAuthentication({_bicep_authentication(**fields)})",
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if not accepted:
        assert "authentication needs GUID" in result.stderr


def test_terraform_native_format(relocated: Path) -> None:
    passed(invoke("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


@pytest.mark.parametrize(
    ("overrides", "failure"),
    [
        ({}, None),
        ({"stage": "test"}, None),
        ({"stage": "staging", "private_endpoint": PRIVATE_ENDPOINT}, "availability"),
        (
            {
                "stage": "staging",
                "availability": {
                    **PRODUCTION_AVAILABILITY,
                    "deletion_protection": False,
                },
                "internal_environment": True,
                "linked_virtual_network_ids": [HUB],
            },
            None,
        ),
        (
            {"stage": "staging", "availability": PRODUCTION_AVAILABILITY},
            "private_endpoint",
        ),
        *[
            ({"cpu": cpu, "memory": memory}, None if accepted else "memory")
            for cpu, memory, accepted in (
                (0.25, "0.5Gi", True),
                (1.25, "2.5Gi", True),
                (4, "8Gi", True),
                (1, "1Gi", False),
            )
        ],
        ({"cpu": 0.3, "memory": "0.6Gi"}, "cpu"),
        ({"log_retention_days": 730}, None),
        ({"log_retention_days": 29}, "log_retention_days"),
        ({"log_retention_days": 30.5}, "log_retention_days"),
        ({"linked_virtual_network_ids": [HUB]}, "linked_virtual_network_ids"),
        *[
            (
                {
                    "availability": {
                        **AVAILABILITY,
                        "infrastructure_subnet_id": SUBNET,
                    },
                    "internal_environment": True,
                    "linked_virtual_network_ids": ids,
                },
                "linked_virtual_network_ids",
            )
            for ids in (
                [HUB, HUB.upper()],
                [INFRASTRUCTURE_VNET.upper()],
                [SUBNET],
            )
        ],
        (
            {
                "availability": {**AVAILABILITY, "infrastructure_subnet_id": SUBNET},
                "internal_environment": True,
                "public_network_access": "Enabled",
            },
            "public_network_access",
        ),
        (
            {"private_endpoint": PRIVATE_ENDPOINT, "public_network_access": "Enabled"},
            "public_network_access",
        ),
        ({"public_network_access": "Enabled"}, None),
        ({"public_network_access": None}, None),
        # Omission (null) is the only absent form; an empty string is rejected.
        *[
            pytest.param({name: ""}, name, id=f"empty_{name}")
            for name in (
                "existing_identity_resource_id",
                "registry_server",
                "application_insights_connection_string",
                "otlp_endpoint",
                "public_network_access",
            )
        ],
        ({"custom_domain": {"host_name": "app.example.com"}}, None),
        (
            {
                "custom_domain": {
                    "host_name": "app.example.com",
                    "bind_certificate": True,
                },
                "public_network_access": "Enabled",
            },
            None,
        ),
        *[
            ({"custom_domain": {"host_name": host}}, "custom_domain")
            for host in ("example.com", "App.example.com", "https://app.example.com")
        ],
        (
            {
                "custom_domain": {"host_name": "app.example.com"},
                "private_endpoint": PRIVATE_ENDPOINT,
            },
            "custom_domain",
        ),
        (
            {
                "custom_domain": {"host_name": "app.example.com"},
                "public_network_access": "Disabled",
            },
            "custom_domain",
        ),
        (
            {
                "stage": "prod",
                "availability": PRODUCTION_AVAILABILITY,
                "internal_environment": True,
            },
            None,
        ),
        # Reported on availability so an invalid availability cannot hide the
        # production private-endpoint check behind an unknown flag.
        ({"internal_environment": True}, "availability"),
        (
            {
                "availability": PRODUCTION_AVAILABILITY,
                "internal_environment": True,
                "private_endpoint": PRIVATE_ENDPOINT,
            },
            "private_endpoint",
        ),
        ({"container_image": "example.azurecr.io/sample:latest"}, "container_image"),
        (
            {"container_image": f"example.azurecr.io/sample@sha256:{'g' * 64}"},
            "container_image",
        ),
        (
            {"container_image": "example.azurecr.io/sample@sha256:abc"},
            "container_image",
        ),
        ({"stage": "production"}, "stage"),
        ({"stage": "prod", "private_endpoint": PRIVATE_ENDPOINT}, "availability"),
        (
            {"stage": "prod", "availability": PRODUCTION_AVAILABILITY},
            "private_endpoint",
        ),
        ({"private_endpoint": PRIVATE_ENDPOINT}, None),
        ({"authentication": AUTHENTICATION}, None),
        (
            {
                "authentication": {
                    **AUTHENTICATION,
                    "sign_in": True,
                    "allowed_audiences": [f"api://{CLIENT_ID}"],
                    "public_host_name": "app.example.com",
                }
            },
            None,
        ),
        *[
            ({"authentication": {**AUTHENTICATION, field: value}}, "authentication")
            for field, value in (
                ("client_id", "not-a-guid"),
                ("tenant_id", TENANT_ID[:-1]),
                ("public_host_name", "https://app.example.com"),
                ("public_host_name", "App.example.com"),
                ("public_host_name", "-app.example.com"),
                ("excluded_paths", ["health/ready"]),
            )
        ],
        (
            {"authentication": {**AUTHENTICATION, "excluded_paths": ["/health/ready"]}},
            None,
        ),
        (
            {"private_endpoint": {**PRIVATE_ENDPOINT, "subnet_id": "not-a-subnet"}},
            "private_endpoint",
        ),
        (
            {
                "private_endpoint": {
                    **PRIVATE_ENDPOINT,
                    "private_dns_zone_id": ZONE.replace("westeurope", "northeurope"),
                }
            },
            "private_endpoint",
        ),
        ({"app_name": "Invalid--Name"}, "app_name"),
        ({"target_port": 0}, "target_port"),
        ({"location": ""}, "location"),
        ({"availability": {**AVAILABILITY, "min_replicas": 4}}, "availability"),
        ({"availability": {**AVAILABILITY, "min_replicas": 0.5}}, "availability"),
        ({"registry_server": "example.azurecr.io"}, "registry_server"),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "registry_server": "mismatch.azurecr.io",
            },
            "registry_server",
        ),
        (
            {"existing_identity_resource_id": "not-an-identity"},
            "existing_identity_resource_id",
        ),
        *[
            (
                {
                    "existing_identity_resource_id": IDENTITY,
                    "secret_references": [{**SECRET_REFERENCE, "key_vault_url": url}],
                },
                None if accepted else "secret_references",
            )
            for url, accepted in _SECRET_URL_CASES
        ],
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "registry_server": "example.azurecr.io",
            },
            None,
        ),
        (
            {
                "stage": "prod",
                "availability": PRODUCTION_AVAILABILITY,
                "private_endpoint": PRIVATE_ENDPOINT,
            },
            None,
        ),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "secret_references": [SECRET_REFERENCE],
            },
            None,
        ),
        ({"secret_references": [SECRET_REFERENCE]}, "secret_references"),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "secret_references": [SECRET_REFERENCE, SECRET_REFERENCE],
            },
            "secret_references",
        ),
        *[
            (
                {
                    "existing_identity_resource_id": IDENTITY,
                    "secret_references": [
                        SECRET_REFERENCE,
                        {**SECRET_REFERENCE, field: value},
                    ],
                },
                "secret_references",
            )
            for field, value in (("name", "other"), ("environment_variable", "OTHER"))
        ],
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "application_insights_connection_string": CONNECTION_STRING,
            },
            None,
        ),
        (
            {"application_insights_connection_string": CONNECTION_STRING},
            "application_insights_connection_string",
        ),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "application_insights_connection_string": "not-a-connection-string",
            },
            "application_insights_connection_string",
        ),
        ({"otlp_endpoint": OTLP_ENDPOINT}, None),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "otlp_endpoint": OTLP_ENDPOINT,
                "secret_references": [OTLP_HEADERS],
            },
            None,
        ),
        ({"otlp_endpoint": OTLP_ENDPOINT.replace("https", "http")}, "otlp_endpoint"),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "secret_references": [
                    {**SECRET_REFERENCE, "environment_variable": "OTEL_SERVICE_NAME"}
                ],
            },
            "secret_references",
        ),
        (
            {
                "existing_identity_resource_id": IDENTITY,
                "otlp_endpoint": OTLP_ENDPOINT,
                "secret_references": [
                    {**SECRET_REFERENCE, "environment_variable": "OTEL_SERVICE_NAME"}
                ],
            },
            "secret_references",
        ),
        *[
            (
                {"availability": {**AVAILABILITY, field: value}},
                "availability",
            )
            for field, value in (
                ("max_replicas", 0),
                ("max_replicas", 31),
                ("zone_redundant", True),
                ("infrastructure_subnet_id", "not-a-subnet"),
                # An empty string is a malformed subnet ID, never "absent".
                ("infrastructure_subnet_id", ""),
            )
        ],
        *[
            (
                {
                    "stage": "prod",
                    "availability": {**PRODUCTION_AVAILABILITY, field: value},
                    "private_endpoint": PRIVATE_ENDPOINT,
                },
                "availability",
            )
            for field, value in [
                ("min_replicas", 1),
                ("zone_redundant", False),
                ("deletion_protection", False),
                ("infrastructure_subnet_id", None),
            ]
        ],
    ],
)
def test_terraform_native_variable_contract_without_provider(
    tmp_path: Path, overrides: dict[str, object], failure: str | None
) -> None:
    _variable_contract(tmp_path, overrides, failure)


def _variable_contract(
    tmp_path: Path,
    overrides: dict[str, object],
    failure: str | None,
    assertions: tuple[str, ...] = (),
) -> None:
    # Isolate the exact canonical declarations, NOT an alternate infrastructure copy.
    # This proves Terraform input validation, not AzAPI resource schema validation.
    shutil.copyfile(ROOT / "terraform/variables.tf", tmp_path / "variables.tf")
    (tmp_path / "inputs.auto.tfvars.json").write_text(
        json.dumps({**INPUTS, **overrides}), encoding="utf-8"
    )
    (tmp_path / "contract.tftest.hcl").write_text(
        'run "contract" {\n  command = plan\n'
        + (f"  expect_failures = [var.{failure}]\n" if failure else "")
        + "".join(
            f"  assert {{\n    condition = {condition}\n"
            '    error_message = "The optional workspace ID must retain the caller value or null default."\n'
            "  }\n"
            for condition in assertions
        )
        + "}\n",
        encoding="utf-8",
    )
    passed(invoke("terraform", tmp_path, "validate", "-json"))
    passed(invoke("terraform", tmp_path, "test", "-no-color"))
    assert not list(tmp_path.glob("*.tfstate*"))


@pytest.mark.parametrize(
    ("workspace_id", "accepted"),
    [
        pytest.param(None, True, id="omitted"),
        *[
            pytest.param(value, accepted, id=name)
            for name, value, accepted in WORKSPACE_ID_CASES
        ],
    ],
)
def test_terraform_workspace_id_contract(
    tmp_path: Path, workspace_id: str | None, accepted: bool
) -> None:
    variable = "existing_log_analytics_workspace_resource_id"
    # An explicit reference prevents undeclared tfvars warnings masquerading as success.
    (tmp_path / "outputs.tf").write_text(
        f'output "workspace_input" {{ value = var.{variable} }}\n', encoding="utf-8"
    )
    _variable_contract(
        tmp_path,
        {} if workspace_id is None else {variable: workspace_id},
        None if accepted else variable,
        (f"var.{variable} == {json.dumps(workspace_id)}",) if accepted else (),
    )


def test_terraform_workspace_count_migration_preserves_address(relocated: Path) -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (relocated / "terraform").glob("*.tf")
    )
    moves = re.findall(r"moved\s*\{\s*from\s*=\s*(\S+)\s+to\s*=\s*(\S+)\s*\}", source)
    assert ("azapi_resource.workspace", "azapi_resource.workspace[0]") in moves, (
        "Adding workspace count must explicitly move the existing dedicated workspace "
        "from azapi_resource.workspace to azapi_resource.workspace[0]"
    )


@pytest.mark.parametrize(
    ("expression", "accepted"),
    [
        ("requireEnvironment({}, [])", True),
        (
            """requireEnvironment({ APP_POSTGRES_HOST: 'db.example.invalid', APP_AUTH_SCOPES: '["read"]' }, ['APP_POSTGRES_PASSWORD'])""",
            True,
        ),
        ("requireEnvironment({ 'BAD-NAME': 'value' }, [])", False),
        ("requireEnvironment({ '1BAD': 'value' }, [])", False),
        ("requireEnvironment({ APP_VALUE: 'value' }, ['APP_VALUE'])", False),
        ("requireEnvironment({ OTEL_SERVICE_NAME: 'value' }, [])", False),
        *[
            (f"requireEnvironment({{ {name}: 'value' }}, [])", False)
            for name in (
                "APP_POSTGRES_PASSWORD",
                "APP_REDIS_URL",
                "APP_AI_API_KEY",
                "OTEL_EXPORTER_OTLP_HEADERS",
            )
        ],
        pytest.param(
            "requireEnvironment({ app_postgres_host: 'db.example.invalid' }, [])",
            True,
            id="case_lowercase_nonsecret",
        ),
        *[
            pytest.param(
                f"requireEnvironment({{ {name.lower()}: 'value' }}, [])",
                False,
                id=f"case_lowercase_credential_{name.lower()}",
            )
            for name in (
                "APP_POSTGRES_PASSWORD",
                "APP_REDIS_URL",
                "APP_AI_API_KEY",
                "OTEL_EXPORTER_OTLP_HEADERS",
            )
        ],
        *[
            pytest.param(
                f"requireEnvironment({{ {name.title()}: 'value' }}, [])",
                False,
                id=f"case_reserved_plain_{name.lower()}",
            )
            for name in RESERVED_VARIABLES
        ],
        pytest.param(
            "requireEnvironment({ app_postgres_password: 'value' }, ['APP_POSTGRES_PASSWORD'])",
            False,
            id="case_lowercase_credential_overrides_secret",
        ),
        *[
            pytest.param(
                f"requireEnvironment({{ {plain}: 'value' }}, ['{secret}'])",
                False,
                id=f"case_plain_secret_collision_{plain}",
            )
            for plain, secret in (
                ("APP_TOKEN", "aPp_ToKeN"),
                ("aPp_ToKeN", "APP_TOKEN"),
            )
        ],
    ],
)
def test_bicep_environment_map_guards(
    relocated: Path, expression: str, accepted: bool
) -> None:
    directory = relocated / "bicep"
    (directory / "environment.bicepparam").write_text(
        "using none\nimport { requireEnvironment } from './app.bicep'\n"
        f"param checked = {expression}\n",
        encoding="utf-8",
    )
    result = invoke(
        "bicep",
        directory,
        "build-params",
        "environment.bicepparam",
        "--no-restore",
        "--stdout",
    )
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    if not accepted:
        assert "environmentVariables" in result.stderr


@pytest.mark.parametrize(
    ("values", "secret_variable", "failure"),
    [
        ({}, "APP_POSTGRES_PASSWORD", None),
        (
            {"APP_POSTGRES_HOST": "db.example.invalid", "APP_AUTH_SCOPES": '["read"]'},
            "APP_POSTGRES_PASSWORD",
            None,
        ),
        ({"BAD-NAME": "value"}, "APP_POSTGRES_PASSWORD", "environment_variables"),
        ({"APP_VALUE": None}, "APP_POSTGRES_PASSWORD", "environment_variables"),
        ({"APP_VALUE": "value"}, "APP_VALUE", "environment_variables"),
        (
            {"OTEL_SERVICE_NAME": "value"},
            "APP_POSTGRES_PASSWORD",
            "environment_variables",
        ),
        ({}, "AZURE_CLIENT_ID", "secret_references"),
        *[
            ({name: "value"}, "APP_VALUE", "environment_variables")
            for name in (
                "APP_POSTGRES_PASSWORD",
                "APP_REDIS_URL",
                "APP_AI_API_KEY",
                "OTEL_EXPORTER_OTLP_HEADERS",
            )
        ],
        pytest.param(
            {"app_postgres_host": "db.example.invalid"},
            "APP_POSTGRES_PASSWORD",
            None,
            id="case_lowercase_nonsecret",
        ),
        pytest.param(
            {},
            "app_postgres_password",
            None,
            id="case_lowercase_credential_reference",
        ),
        *[
            pytest.param(
                {name.lower(): "value"},
                "APP_VALUE",
                "environment_variables",
                id=f"case_lowercase_credential_{name.lower()}",
            )
            for name in (
                "APP_POSTGRES_PASSWORD",
                "APP_REDIS_URL",
                "APP_AI_API_KEY",
                "OTEL_EXPORTER_OTLP_HEADERS",
            )
        ],
        *[
            pytest.param(
                {name.title(): "value"},
                "APP_POSTGRES_PASSWORD",
                "environment_variables",
                id=f"case_reserved_plain_{name.lower()}",
            )
            for name in RESERVED_VARIABLES
        ],
        *[
            pytest.param(
                {},
                name.lower(),
                "secret_references",
                id=f"case_reserved_secret_{name.lower()}",
            )
            for name in RESERVED_VARIABLES
        ],
        pytest.param(
            {"app_postgres_password": "value"},
            "APP_POSTGRES_PASSWORD",
            "environment_variables",
            id="case_lowercase_credential_overrides_secret",
        ),
        *[
            pytest.param(
                {plain: "value"},
                secret,
                "environment_variables",
                id=f"case_plain_secret_collision_{plain}",
            )
            for plain, secret in (
                ("APP_TOKEN", "aPp_ToKeN"),
                ("aPp_ToKeN", "APP_TOKEN"),
            )
        ],
        pytest.param(
            {"APP_VALUE": "first", "app_value": "second"},
            "APP_POSTGRES_PASSWORD",
            "environment_variables",
            id="case_plain_plain_collision",
        ),
    ],
)
def test_terraform_environment_map_guards(
    tmp_path: Path, values: dict[str, object], secret_variable: str, failure: str | None
) -> None:
    _variable_contract(
        tmp_path,
        {
            "environment_variables": values,
            "existing_identity_resource_id": IDENTITY,
            "secret_references": [
                {**SECRET_REFERENCE, "environment_variable": secret_variable}
            ],
        },
        failure,
    )


def test_terraform_case_insensitive_secret_secret_collision(tmp_path: Path) -> None:
    _variable_contract(
        tmp_path,
        {
            "existing_identity_resource_id": IDENTITY,
            "secret_references": [
                {**SECRET_REFERENCE, "name": name, "environment_variable": variable}
                for name, variable in (
                    ("first", "APP_TOKEN"),
                    ("second", "aPp_ToKeN"),
                )
            ],
        },
        "secret_references",
    )


def _init_terraform_mock_plans(directory: Path) -> None:
    mirror = os.environ.get("CONTAINER_APPS_AZAPI_MIRROR")
    if not mirror:
        pytest.skip(
            "Full AzAPI validation/mock plans need reviewed Azure/azapi 2.13.0 "
            "in CONTAINER_APPS_AZAPI_MIRROR; no provider install attempted. "
            "Variable-only native tests are not provider validation."
        )
    mirror_path = Path(mirror).resolve(strict=True)
    assert mirror_path.is_dir()
    # -plugin-dir restricts init to this explicit, operator-provisioned local mirror.
    passed(
        invoke(
            "terraform",
            directory,
            "init",
            "-backend=false",
            "-input=false",
            f"-plugin-dir={mirror_path}",
        )
    )


@pytest.mark.parametrize(
    "workspace_input",
    [
        {},
        {"existing_log_analytics_workspace_resource_id": None},
        {"existing_log_analytics_workspace_resource_id": WORKSPACE},
    ],
    ids=["omitted", "null", "caller_owned"],
)
def test_terraform_workspace_reuse_mock_plan(
    relocated: Path, workspace_input: dict[str, str | None]
) -> None:
    directory = relocated / "terraform"
    _init_terraform_mock_plans(directory)
    dedicated_id = f"{GROUP}/providers/Microsoft.OperationalInsights/workspaces/sample-dev-env-logs"
    workspace_id = workspace_input.get("existing_log_analytics_workspace_resource_id")
    inputs = {
        **INPUTS,
        "stage": "prod",
        "availability": PRODUCTION_AVAILABILITY,
        "private_endpoint": PRIVATE_ENDPOINT,
        **workspace_input,
    }
    effective_id = json.dumps(workspace_id or dedicated_id)
    protected = ["app", "environment", "identity"]
    if workspace_id is None:
        protected.append("workspace")
    expectations = (
        (
            f"length(azapi_resource.workspace) == {0 if workspace_id else 1}",
            "Only dedicated mode may own a workspace.",
        ),
        (
            (
                'join(",", sort(keys(azapi_resource.protection))) == '
                f'"{",".join(protected)}"'
            ),
            "Keep app/environment/identity locks, but never lock a caller workspace.",
        ),
        (
            (
                f"output.workspace_resource_id == {effective_id} && "
                f"azapi_resource.diagnostics.body.properties.workspaceId == {effective_id}"
            ),
            "Output and diagnostics must target the effective workspace ID.",
        ),
        (
            'azapi_resource.environment.body.properties.appLogsConfiguration.destination == "azure-monitor"',
            "Workspace reuse must keep keyless Azure Monitor logging.",
        ),
        (
            (
                'azapi_resource.environment.body.properties.publicNetworkAccess == "Disabled" && '
                "length(azapi_resource.endpoint) == 1 && "
                "azapi_resource.environment.body.properties.zoneRedundant && "
                "azapi_resource.app.body.properties.configuration.ingress.allowInsecure == false"
            ),
            "Workspace ownership must not weaken production networking or TLS.",
        ),
    )
    fixture = "tests/workspace_reuse.tftest.hcl"
    (directory / fixture).write_text(
        'mock_provider "azapi" {}\n'
        "variables {\n"
        + "".join(f"  {key} = {json.dumps(value)}\n" for key, value in inputs.items())
        + '}\nrun "workspace_ownership" {\n  command = plan\n'
        "  override_resource {\n    target = azapi_resource.workspace\n"
        "    override_during = plan\n"
        f"    values = {{ id = {json.dumps(dedicated_id)} }}\n"
        "  }\n"
        + "".join(
            f"  assert {{\n    condition = {condition}\n"
            f"    error_message = {json.dumps(message)}\n  }}\n"
            for condition, message in expectations
        )
        + "}\n",
        encoding="utf-8",
    )
    passed(
        invoke(
            "terraform",
            directory,
            "test",
            "-no-color",
            f"-filter={fixture}",
            timeout=600,
        )
    )
    assert not list(directory.glob("*.tfstate*"))


def test_terraform_full_native_validation_and_mock_plans(relocated: Path) -> None:
    directory = relocated / "terraform"
    _init_terraform_mock_plans(directory)
    passed(invoke("terraform", directory, "validate", "-json"))
    # The 38 mocked AzAPI runs take a few minutes on an idle Windows laptop.
    passed(invoke("terraform", directory, "test", "-no-color", timeout=600))
    assert not list(directory.glob("*.tfstate*"))
