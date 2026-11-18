"""Offline Azure Managed Redis evidence from installed tools; never a deployment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.integration
SOURCE: Final[Path] = (
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/managed-redis"
)
TIMEOUT_SECONDS: Final[int] = 300
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/redis"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.redis.azure.net"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
MESSAGES: Final[dict[str, str]] = {
    "name": (
        "name must use 2-32 lowercase letters, digits or single hyphens; "
        "start with a letter and end alphanumeric."
    ),
    "principal": (
        "principalId must be the object (principal) ID GUID of the existing app "
        "identity."
    ),
    "sku": (
        "sku must be an Azure Managed Redis SKU, for example Balanced_B0 or "
        "MemoryOptimized_M10."
    ),
    "prod_sku": (
        "Production rejects the dev/test sizes Balanced_B0 and Balanced_B1; "
        "choose Balanced_B3 or larger."
    ),
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.redis.azure.net zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a privatelink.redis.azure.net "
        "private DNS zone ARM ID."
    ),
    "public_stage": (
        "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
    ),
    "prod_workspace": (
        "Staging and production require logAnalyticsWorkspaceId: an existing "
        "Log Analytics workspace for diagnostics."
    ),
    "workspace": "logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID.",
}
# Platform defaults that the sources must never restate.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "minimumTlsVersion",
    "clientProtocol",
    "highAvailability",
    "evictionPolicy",
    "persistence",
    "zones",
)
_PRIVATE = (SUBNET, ZONE)
_Case = tuple[str, str | None]
_StageCase = tuple[str, str, str | None]
# None omits the workspace; an empty string is a malformed ID, not "absent".
_WorkspaceCase = tuple[str, str | None, str | None]
_NetworkCase = tuple[str, tuple[str, str] | None, str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
NAME_CASES: Final[tuple[_Case, ...]] = (
    ("sample-dev", None),
    ("a1", None),
    ("a" * 33, "name"),
    ("Sample", "name"),
    ("1sample", "name"),
    ("sample-", "name"),
    ("sample--dev", "name"),
)
PRINCIPAL_CASES: Final[tuple[_Case, ...]] = (
    (PRINCIPAL, None),
    ("A1B2C3D4-0000-4000-8000-00000000000F", None),
    ("not-a-guid", "principal"),
    ("zzzzzzzz-0000-0000-0000-000000000000", "principal"),
    ("00000000000000000000000000000000", "principal"),
    (
        f"{NETWORK_GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/app",
        "principal",
    ),
)
SKU_CASES: Final[tuple[_StageCase, ...]] = (
    ("dev", "Balanced_B0", None),
    ("test", "Balanced_B1", None),
    ("prod", "Balanced_B3", None),
    ("prod", "MemoryOptimized_M10", None),
    ("prod", "Balanced_B0", "prod_sku"),
    ("prod", "Balanced_B1", "prod_sku"),
    ("dev", "Premium_P1", "sku"),
    ("dev", "Balanced_B", "sku"),
    ("dev", "balanced_b0", "sku"),
    ("dev", "Balanced_B0x", "sku"),
)
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    ("dev", (NETWORK_GROUP, ZONE), "network"),
    ("dev", (f"{SUBNET}/extra", ZONE), "network"),
    ("dev", (SUBNET.removesuffix("redis"), ZONE), "network"),
    (
        "dev",
        (SUBNET, ZONE.replace("redis.azure.net", "redis.cache.windows.net")),
        "network",
    ),
    (
        "dev",
        (SUBNET, f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"),
        "network",
    ),
)
_PublicCase = tuple[str, tuple[str, str] | None, bool, str | None]
PUBLIC_CASES: Final[tuple[_PublicCase, ...]] = (
    ("dev", None, False, None),
    ("test", None, True, None),
    ("prod", _PRIVATE, False, None),
    ("prod", _PRIVATE, True, "public_stage"),
    ("staging", _PRIVATE, True, "public_stage"),
    ("dev", _PRIVATE, True, "public_stage"),
)
WORKSPACE_CASES: Final[tuple[_WorkspaceCase, ...]] = (
    ("dev", None, None),
    ("test", WORKSPACE, None),
    ("staging", WORKSPACE, None),
    ("prod", WORKSPACE, None),
    ("prod", None, "prod_workspace"),
    ("staging", None, "prod_workspace"),
    ("dev", "", "workspace"),
    ("prod", "", "workspace"),
    ("prod", NETWORK_GROUP, "workspace"),
    ("dev", "example", "workspace"),
    ("dev", f"{WORKSPACE}/extra", "workspace"),
    ("dev", WORKSPACE.removesuffix("example"), "workspace"),
    ("dev", WORKSPACE.replace("OperationalInsights", "Insights"), "workspace"),
)


def _executable(name: str) -> str:
    fallback = Path.home() / ".azure/bin/bicep.exe"
    found = shutil.which(name) or (
        str(fallback) if name == "bicep" and fallback.is_file() else None
    )
    if found is None:
        pytest.skip(f"{name} is not installed; nothing is downloaded or installed")
    return found


def _run(name: str, workdir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    offline = {
        "ARM_ENABLE_PREFLIGHT": "false",
        "ARM_SKIP_PROVIDER_REGISTRATION": "true",
        "CHECKPOINT_DISABLE": "1",
        "TF_DATA_DIR": str(workdir / ".terraform"),
        "TF_IN_AUTOMATION": "1",
    }
    command = [_executable(name), *arguments]
    return subprocess.run(  # noqa: S603 - installed tools on synthetic offline inputs
        command,
        cwd=workdir,
        env=os.environ | offline,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def _ok(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return result.stdout


def _bicep_network(network: tuple[str, str] | None) -> str:
    if network is None:
        return "null"
    return f"{{ subnetId: '{network[0]}', privateDnsZoneId: '{network[1]}' }}"


def _terraform_network(network: tuple[str, str] | None) -> dict[str, str] | None:
    if network is None:
        return None
    return {"subnet_id": network[0], "private_dns_zone_id": network[1]}


def _bicep_string(value: str | None) -> str:
    return "null" if value is None else f"'{value}'"


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *((f"requireName('{value}')", error) for value, error in NAME_CASES),
        *(
            (f"requirePrincipalId('{value}')", error)
            for value, error in PRINCIPAL_CASES
        ),
        *(
            (f"requireSku('{stage}', '{sku}')", error)
            for stage, sku, error in SKU_CASES
        ),
        *(
            (f"requirePrivateEndpoint('{stage}', {_bicep_network(network)})", error)
            for stage, network, error in NETWORK_CASES
        ),
        *(
            (
                (
                    f"requirePublicAccess('{stage}', "
                    f"{str(network is not None).lower()}, {str(allow).lower()})"
                ),
                error,
            )
            for stage, network, allow, error in PUBLIC_CASES
        ),
        *(
            (f"requireWorkspace('{stage}', {_bicep_string(workspace)})", error)
            for stage, workspace, error in WORKSPACE_CASES
        ),
    ]


def _terraform_cases() -> list[tuple[Mapping[str, object], str | None]]:
    # Guarded stages add the other required inputs so only one guard fails.
    private = _terraform_network(_PRIVATE)
    diagnostics = {"log_analytics_workspace_id": WORKSPACE}
    guarded = ("staging", "prod")
    return [
        *(({"name": value}, error and "name") for value, error in NAME_CASES),
        *(({"principal_id": v}, e and "principal_id") for v, e in PRINCIPAL_CASES),
        *(
            (
                {"stage": stage, "sku": sku}
                | (
                    {"private_endpoint": private} | diagnostics
                    if stage in guarded
                    else {}
                ),
                error and "sku",
            )
            for stage, sku, error in SKU_CASES
        ),
        *(
            (
                {"stage": stage, "private_endpoint": _terraform_network(network)}
                | ({"sku": "Balanced_B3"} | diagnostics if stage in guarded else {}),
                error and "private_endpoint",
            )
            for stage, network, error in NETWORK_CASES
        ),
        *(
            (
                {
                    "stage": stage,
                    "private_endpoint": _terraform_network(network),
                    "allow_public_network_access": allow,
                }
                | ({"sku": "Balanced_B3"} | diagnostics if stage in guarded else {}),
                error and "allow_public_network_access",
            )
            for stage, network, allow, error in PUBLIC_CASES
        ),
        *(
            (
                {"stage": stage, "log_analytics_workspace_id": workspace}
                | (
                    {"sku": "Balanced_B3", "private_endpoint": private}
                    if stage in guarded
                    else {}
                ),
                error and "log_analytics_workspace_id",
            )
            for stage, workspace, error in WORKSPACE_CASES
        ),
        ({"stage": "production"}, "stage"),
        ({"location": " "}, "location"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    target = tmp_path / "consumer/managed-redis"
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns(".terraform"))

    def digests(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".terraform" not in path.parts
        }

    assert digests(target) == digests(SOURCE)
    return target


def test_sources_are_self_contained_and_never_expose_keys(relocated: Path) -> None:
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").rglob("*.tf"))
    )
    assert not list(relocated.rglob("*.tfstate*"))
    assert "module " not in bicep
    assert 'module "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    for forbidden in ("listKeys", "listSecrets"):
        assert forbidden not in bicep
    for forbidden in ("azapi_resource_action", 'response_export_values = ["*"]'):
        assert forbidden not in terraform
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    # Entra ID is the only data-plane credential in both flavours, stated explicitly.
    assert "accessKeysAuthentication: 'Disabled'" in bicep
    assert 'accessKeysAuthentication = "Disabled"' in terraform
    resource_types = re.compile(r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)""")
    declared = set(resource_types.findall(bicep))
    assert len(declared) == 7
    assert declared == set(resource_types.findall(terraform))
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    for message in MESSAGES.values():
        assert message in bicep, message
        assert message in variables, message


def _assert_diagnostics(resources: Mapping[str, Mapping[str, object]]) -> None:
    """Metrics come from the cluster and connection logs from the database."""
    metrics = resources["clusterDiagnostics"]
    logs = resources["databaseDiagnostics"]
    assert metrics["type"] == logs["type"] == "Microsoft.Insights/diagnosticSettings"
    assert metrics["dependsOn"] == ["cluster"]
    assert logs["dependsOn"] == ["database"]
    assert str(metrics["scope"]).startswith(
        "[format('Microsoft.Cache/redisEnterprise/{0}'"
    )
    assert "/databases/{1}'" in str(logs["scope"])
    for setting, entries, category in (
        (metrics, "metrics", "AllMetrics"),
        (logs, "logs", "ConnectionEvents"),
    ):
        assert setting["condition"] == (
            "[not(equals(variables('workspaceId'), null()))]"
        )
        assert setting["properties"] == {
            "workspaceId": "[variables('workspaceId')]",
            entries: [{"category": category, "enabled": True}],
        }


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    for source in sorted([*folder.rglob("*.bicep"), *folder.rglob("*.bicepparam")]):
        rendered = _ok(_run("bicep", folder, "format", str(source), "--stdout"))
        assert rendered == source.read_text(encoding="utf-8"), source.name
    lint = _run("bicep", folder, "lint", "main.bicep", "--no-restore")
    assert _ok(lint) == ""
    assert lint.stderr == ""
    template = json.loads(
        _ok(_run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))
    )
    resources = template["resources"]
    by_type = {resource["type"]: resource for resource in resources.values()}
    # Two diagnostic settings share one type; every other type appears once.
    assert len(resources) == 8
    assert len(by_type) == 7
    cluster = by_type["Microsoft.Cache/redisEnterprise"]
    assert set(cluster) & {"zones", "identity"} == set()
    assert set(cluster["properties"]) == {"publicNetworkAccess"}
    assert by_type["Microsoft.Cache/redisEnterprise/databases"]["properties"] == {
        "clusteringPolicy": "EnterpriseCluster",
        "accessKeysAuthentication": "Disabled",
    }
    access = by_type[
        "Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments"
    ]
    assert access["properties"]["accessPolicyName"] == "default"
    endpoint = by_type["Microsoft.Network/privateEndpoints"]
    connection = endpoint["properties"]["privateLinkServiceConnections"][0]
    assert connection["properties"]["groupIds"] == ["redisEnterprise"]
    lock = by_type["Microsoft.Authorization/locks"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert "scope" in lock
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    for optional in (
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Network/privateEndpoints/privateDnsZoneGroups",
    ):
        assert "condition" in by_type[optional]
    _assert_diagnostics(resources)
    assert set(template["outputs"]) == {"redisResourceId", "hostName", "port"}
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "principalId"):
        assert "defaultValue" not in parameters[required]
    assert parameters["sku"]["defaultValue"] == "Balanced_B0"
    assert parameters["privateEndpoint"]["nullable"] is True
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace = parameters["logAnalyticsWorkspaceId"]
    assert workspace["nullable"] is True
    assert workspace["minLength"] == 1
    assert "defaultValue" not in workspace
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    guarded = {
        name
        for name, value in template["variables"].items()
        if "__bicep.require" in str(value)
    }
    assert guarded == {
        "checkedName",
        "checkedSku",
        "objectId",
        "network",
        "publicAccess",
        "workspaceId",
    }
    for example in ("tests/dev.bicepparam", "tests/prod.bicepparam"):
        _ok(_run("bicep", folder, "build-params", example, "--no-restore", "--stdout"))


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        ("'Balanced_B3'", "'Balanced_B1'", "prod_sku"),
        ("'Balanced_B3'", "'Balanced_B0'", "prod_sku"),
        (r"\(stage, \{.*?\}\)", "(stage, null)", "prod_network"),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, null)",
            "prod_workspace",
        ),
        ("/workspaces/example'", "/workspaces/'", "workspace"),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    folder = relocated / "bicep/tests"
    example = (folder / "prod.bicepparam").read_text(encoding="utf-8")
    unsafe_text, replaced = re.subn(
        pattern, replacement, example, count=1, flags=re.DOTALL
    )
    assert replaced == 1
    unsafe = folder / "unsafe.bicepparam"
    unsafe.write_text(unsafe_text, encoding="utf-8")
    result = _run(
        "bicep", folder, "build-params", unsafe.name, "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert MESSAGES[error] in result.stderr, result.stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    folder = relocated / "bicep"
    header = (
        "using none\n"
        "import { requireName, requirePrincipalId, requireSku, requirePrivateEndpoint,"
        " requirePublicAccess, requireWorkspace } from './main.bicep'\n"
    )
    cases = _bicep_cases()
    accepted = folder / "accepted.bicepparam"
    accepted.write_text(
        header
        + "".join(
            f"param case{index} = {expression}\n"
            for index, (expression, error) in enumerate(cases)
            if error is None
        ),
        encoding="utf-8",
    )
    _ok(
        _run("bicep", folder, "build-params", accepted.name, "--no-restore", "--stdout")
    )
    rejected = [
        (index, expression, MESSAGES[error])
        for index, (expression, error) in enumerate(cases)
        if error is not None
    ]
    fixture = folder / "rejected.bicepparam"
    fixture.write_text(
        header
        + "".join(f"param case{i} = {expression}\n" for i, expression, _ in rejected),
        encoding="utf-8",
    )
    result = _run(
        "bicep", folder, "build-params", fixture.name, "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert result.stderr.count("Error BCP") == len(rejected), result.stderr
    for index, _, message in rejected:
        expected = f'Failed to evaluate parameter "case{index}": {message}'
        assert expected in result.stderr, expected


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    _ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    # The unchanged variables.tf alone proves input validation, not AzAPI schemas.
    shutil.copyfile(SOURCE / "terraform/variables.tf", tmp_path / "variables.tf")
    baseline = {
        "resource_group_id": NETWORK_GROUP,
        "location": "westeurope",
        "name": "sample-dev",
        "stage": "dev",
        "principal_id": PRINCIPAL,
    }
    (tmp_path / "inputs.auto.tfvars.json").write_text(
        json.dumps(baseline), encoding="utf-8"
    )
    cases = _terraform_cases()
    blocks = []
    for index, (overrides, failure) in enumerate(cases):
        # JSON scalars, objects and null are valid HCL expressions.
        assignments = "".join(
            f"    {key} = {json.dumps(value)}\n" for key, value in overrides.items()
        )
        expected = f"  expect_failures = [var.{failure}]\n" if failure else ""
        blocks.append(
            f'run "case{index}" {{\n  command = plan\n'
            f"  variables {{\n{assignments}  }}\n{expected}}}\n"
        )
    (tmp_path / "contract.tftest.hcl").write_text("".join(blocks), encoding="utf-8")
    _ok(_run("terraform", tmp_path, "validate", "-json"))
    output = _ok(_run("terraform", tmp_path, "test", "-no-color"))
    assert f"Success! {len(cases)} passed, 0 failed." in output, output
    assert not list(tmp_path.glob("*.tfstate*"))


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    mirror = os.environ.get("CONTAINER_APPS_AZAPI_MIRROR")
    if not mirror:
        pytest.skip(
            "Full AzAPI validation needs reviewed Azure/azapi 2.13.0 in "
            "CONTAINER_APPS_AZAPI_MIRROR; no provider install attempted."
        )
    plugins = Path(mirror).resolve(strict=True)
    assert plugins.is_dir()
    folder = relocated / "terraform"
    # -plugin-dir limits init to the operator-provisioned local mirror.
    _ok(
        _run(
            "terraform",
            folder,
            "init",
            "-backend=false",
            "-input=false",
            f"-plugin-dir={plugins}",
        )
    )
    _ok(_run("terraform", folder, "validate", "-json"))
    _ok(_run("terraform", folder, "test", "-no-color"))
    assert not list(folder.glob("*.tfstate*"))
