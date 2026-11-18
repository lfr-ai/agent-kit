"""Offline Terraform remote-state storage evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/terraform-state"
)
# The pinned AzAPI provider starts slowly; one mocked test run can take minutes.
TIMEOUT_SECONDS: Final[int] = 900
NAME_LENGTH: Final[tuple[int, int]] = (3, 24)
PRINCIPAL_LENGTH: Final[int] = 36
RETENTION_DAYS: Final[int] = 30
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
BLOB_DATA_CONTRIBUTOR_ROLE: Final[str] = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
RESOURCE_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/state"
)
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/state"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.blob.core.windows.net"
)
MESSAGES: Final[dict[str, str]] = {
    "prod_sku": (
        "Staging and production require zone-redundant state: "
        "sku Standard_ZRS or Standard_GZRS."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.blob.core.windows.net private DNS zone ARM ID."
    ),
    "ranges_with_endpoint": (
        "allowedIpRanges is only for an account without privateEndpoint, "
        "which disables public network access."
    ),
    "ip_range": (
        "allowedIpRanges must hold IPv4 addresses or CIDR ranges, "
        "such as 203.0.113.0/24."
    ),
}
# Platform defaults for storageAccounts@2025-06-01 that must never be restated.
# allowBlobPublicAccess is pinned off explicitly instead; see the source test.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "supportsHttpsTrafficOnly",
    "allowCrossTenantReplication",
    "accessTier",
    "publicAccess",
    "bypass",
)
_StageCase = tuple[str, str, str | None]
_Network = tuple[str, str]
_NetworkCase = tuple[_Network | None, str | None]
_RangeCase = tuple[bool, list[str], str | None]
_PRIVATE = (SUBNET, ZONE)
# Shared positive/negative tables drive both the Bicep and Terraform guards.
SKU_CASES: Final[tuple[_StageCase, ...]] = (
    ("dev", "Standard_LRS", None),
    ("test", "Standard_LRS", None),
    ("staging", "Standard_ZRS", None),
    ("prod", "Standard_ZRS", None),
    ("prod", "Standard_GZRS", None),
    ("prod", "Standard_LRS", "prod_sku"),
    ("staging", "Standard_LRS", "prod_sku"),
)
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    (None, None),
    (_PRIVATE, None),
    ((SUBNET, ZONE.upper()), "network"),
    ((SUBNET, ""), "network"),
    ((SUBNET, ZONE.replace(".blob.", ".file.")), "network"),
    ((SUBNET, f"{ZONE}/extra"), "network"),
    ((SUBNET.replace("/subnets/", "/subnet/"), ZONE), "network"),
    ((SUBNET.rsplit("/subnets/", 1)[0], ZONE), "network"),
)
RANGE_CASES: Final[tuple[_RangeCase, ...]] = (
    (False, [], None),
    (True, [], None),
    (False, ["203.0.113.0/24", "198.51.100.7"], None),
    (True, ["203.0.113.0/24"], "ranges_with_endpoint"),
    (False, ["203.0.113"], "ip_range"),
    (False, ["203.0.113.0/"], "ip_range"),
    (False, ["2001:db8::/32"], "ip_range"),
)
# Bicep enforces these with native decorators and types; Terraform with validation blocks.
NATIVE_TERRAFORM_CASES: Final[tuple[tuple[dict[str, object], str | None], ...]] = (
    ({"name": "a" * NAME_LENGTH[0]}, None),
    ({"name": "a" * NAME_LENGTH[1]}, None),
    ({"name": "a" * (NAME_LENGTH[0] - 1)}, "name"),
    ({"name": "a" * (NAME_LENGTH[1] + 1)}, "name"),
    ({"principal_id": "not-a-guid"}, "principal_id"),
    ({"sku": "Standard_RAGRS"}, "sku"),
    ({"stage": "production"}, "stage"),
    ({"location": " "}, "location"),
    ({"resource_group_id": "example"}, "resource_group_id"),
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


def _bicep_network(network: _Network | None) -> str:
    if network is None:
        return "null"
    return f"{{ subnetId: '{network[0]}', privateDnsZoneId: '{network[1]}' }}"


def _terraform_network(network: _Network | None) -> dict[str, str] | None:
    if network is None:
        return None
    return {"subnet_id": network[0], "private_dns_zone_id": network[1]}


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *(
            (f"requireSku('{stage}', '{sku}')", error)
            for stage, sku, error in SKU_CASES
        ),
        *(
            (f"requirePrivateEndpoint({_bicep_network(network)})", error)
            for network, error in NETWORK_CASES
        ),
        *(
            (f"requireIpRanges({str(endpoint).lower()}, {ranges!r})", error)
            for endpoint, ranges, error in RANGE_CASES
        ),
    ]


def _terraform_cases() -> list[tuple[Mapping[str, object], str | None]]:
    return [
        *(
            ({"stage": stage, "sku": sku}, error and "sku")
            for stage, sku, error in SKU_CASES
        ),
        *(
            (
                {"private_endpoint": _terraform_network(network)},
                error and "private_endpoint",
            )
            for network, error in NETWORK_CASES
        ),
        *(
            (
                {
                    "private_endpoint": _terraform_network(
                        _PRIVATE if endpoint else None
                    ),
                    "allowed_ip_ranges": ranges,
                },
                error and "allowed_ip_ranges",
            )
            for endpoint, ranges, error in RANGE_CASES
        ),
        *NATIVE_TERRAFORM_CASES,
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    target = tmp_path / "consumer/terraform-state"
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


def test_sources_are_self_contained_and_entra_only(relocated: Path) -> None:
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").rglob("*.tf"))
    )
    assert not list(relocated.rglob("*.tfstate*"))
    assert "module " not in bicep
    assert 'module "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    assert "allowSharedKeyAccess: false" in bicep
    # Alignment-agnostic: terraform fmt pads the key to the longest sibling.
    assert re.search(r"\ballowSharedKeyAccess\s+= false\n", terraform)
    # Anonymous blob access is pinned off so a redeployment reverts drift.
    assert bicep.count("allowBlobPublicAccess: false\n") == 1
    assert len(re.findall(r"\ballowBlobPublicAccess\s+= false\n", terraform)) == 1
    assert "allowBlobPublicAccess: true" not in bicep
    assert not re.search(r"\ballowBlobPublicAccess\s+= true", terraform)
    # One named soft-delete window per flavour, used by both retention policies.
    assert bicep.count(f"var softDeleteRetentionDays = {RETENTION_DAYS}\n") == 1
    assert bicep.count("days: softDeleteRetentionDays }") == 2
    assert (
        len(
            re.findall(
                rf"\bsoft_delete_retention_days\s+= {RETENTION_DAYS}\n", terraform
            )
        )
        == 1
    )
    assert terraform.count("days = local.soft_delete_retention_days }") == 2
    assert "days: 30 }" not in bicep
    assert "days = 30 }" not in terraform
    for forbidden in ("listKeys", "listAccountSas", "listServiceSas"):
        assert forbidden not in bicep + terraform, forbidden
    for forbidden in ("azapi_resource_action", 'response_export_values = ["*"]'):
        assert forbidden not in terraform
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    resource_types = re.compile(r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)""")
    declared = set(resource_types.findall(bicep))
    assert len(declared) == 7
    assert declared == set(resource_types.findall(terraform))
    assert "Microsoft.Storage/storageAccounts@2025-06-01" in declared
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    for message in MESSAGES.values():
        assert message in bicep, message
        assert message in variables, message


def test_readme_documents_entra_backend_and_bootstrap() -> None:
    readme = (SOURCE / "README.md").read_text(encoding="utf-8")
    for required in (
        'backend "azurerm"',
        "use_azuread_auth     = true",
        'container_name       = "tfstate"',
        "terraform init -migrate-state",
    ):
        assert required in readme, required
    assert "access_key" not in readme
    assert "sas_token" not in readme


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
    assert len(resources) == len(by_type) == 7
    account = by_type["Microsoft.Storage/storageAccounts"]
    assert account["kind"] == "StorageV2"
    assert account["sku"] == {"name": "[variables('checkedSku')]"}
    # The firewall denies by default; a private endpoint disables public access instead.
    properties = account["properties"]
    for fragment in (
        "'allowSharedKeyAccess', false(), 'allowBlobPublicAccess', false()",
        "'minimumTlsVersion', 'TLS1_2'",
        (
            "if(equals(variables('network'), null()), createObject('networkAcls', "
            "createObject('defaultAction', 'Deny', 'ipRules'"
        ),
        "createObject('publicNetworkAccess', 'Disabled')",
    ):
        assert fragment in properties, fragment
    for optional in (
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Network/privateEndpoints/privateDnsZoneGroups",
    ):
        assert by_type[optional]["condition"] == (
            "[not(equals(variables('network'), null()))]"
        )
    connection = by_type["Microsoft.Network/privateEndpoints"]["properties"][
        "privateLinkServiceConnections"
    ][0]
    assert connection["properties"]["groupIds"] == ["blob"]
    assert template["variables"]["softDeleteRetentionDays"] == RETENTION_DAYS
    retention = {"enabled": True, "days": "[variables('softDeleteRetentionDays')]"}
    blob_service = by_type["Microsoft.Storage/storageAccounts/blobServices"]
    assert blob_service["properties"] == {
        "isVersioningEnabled": True,
        "deleteRetentionPolicy": retention,
        "containerDeleteRetentionPolicy": retention,
    }
    container = by_type["Microsoft.Storage/storageAccounts/blobServices/containers"]
    assert container["name"].endswith("'tfstate')]")
    assert "properties" not in container
    # The CI identity gets data access on the state container only.
    role = by_type["Microsoft.Authorization/roleAssignments"]
    assert "condition" not in role
    assert role["scope"].startswith(
        "[format('Microsoft.Storage/storageAccounts/{0}/blobServices/{1}"
        "/containers/{2}'"
    )
    assert role["properties"]["principalType"] == "ServicePrincipal"
    assert template["variables"]["blobDataContributorRoleId"] == (
        BLOB_DATA_CONTRIBUTOR_ROLE
    )
    role_definition = role["properties"]["roleDefinitionId"]
    assert "variables('blobDataContributorRoleId')" in role_definition
    lock = by_type["Microsoft.Authorization/locks"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert lock["scope"] == (
        "[format('Microsoft.Storage/storageAccounts/{0}', parameters('name'))]"
    )
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert set(template["outputs"]) == {
        "storageAccountResourceId",
        "storageAccountName",
        "containerName",
    }
    _assert_inputs(template["parameters"], template["variables"])
    assert set(template["definitions"]["Sku"]["allowedValues"]) == {
        "Standard_LRS",
        "Standard_ZRS",
        "Standard_GZRS",
    }
    for example in ("tests/dev.bicepparam", "tests/prod.bicepparam"):
        _ok(_run("bicep", folder, "build-params", example, "--no-restore", "--stdout"))


def _assert_inputs(
    parameters: Mapping[str, Mapping[str, object]], variables: Mapping[str, object]
) -> None:
    """Parameters match the Terraform variables; the guard stays in the template."""
    for required in ("location", "name", "stage", "principalId"):
        assert "defaultValue" not in parameters[required]
    # The same limits as the Terraform validation blocks.
    assert (parameters["name"]["minLength"], parameters["name"]["maxLength"]) == (
        NAME_LENGTH
    )
    assert parameters["principalId"]["minLength"] == PRINCIPAL_LENGTH
    assert parameters["principalId"]["maxLength"] == PRINCIPAL_LENGTH
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["sku"]["defaultValue"] == "Standard_ZRS"
    assert parameters["privateEndpoint"]["nullable"] is True
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    # A direct deployment fails ARM validation too.
    guarded = {
        name for name, value in variables.items() if "__bicep.require" in str(value)
    }
    assert guarded == {"checkedSku", "network", "ipRanges"}


def test_bicep_production_example_rejects_locally_redundant_state(
    relocated: Path,
) -> None:
    folder = relocated / "bicep/tests"
    example = (folder / "prod.bicepparam").read_text(encoding="utf-8")
    unsafe_text = example.replace("'Standard_GZRS'", "'Standard_LRS'")
    assert unsafe_text != example
    unsafe = folder / "unsafe.bicepparam"
    unsafe.write_text(unsafe_text, encoding="utf-8")
    result = _run(
        "bicep", folder, "build-params", unsafe.name, "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert MESSAGES["prod_sku"] in result.stderr, result.stderr


def test_bicep_guard_accepts_and_rejects_shared_cases(relocated: Path) -> None:
    folder = relocated / "bicep"
    header = (
        "using none\n"
        "import { requireIpRanges, requirePrivateEndpoint, requireSku } "
        "from './main.bicep'\n"
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
        "resource_group_id": RESOURCE_GROUP,
        "location": "westeurope",
        "name": "sampledevtfstate",
        "stage": "dev",
        "principal_id": PRINCIPAL,
    }
    (tmp_path / "inputs.auto.tfvars.json").write_text(
        json.dumps(baseline), encoding="utf-8"
    )
    cases = _terraform_cases()
    blocks = []
    for index, (overrides, failure) in enumerate(cases):
        # JSON scalars are valid HCL expressions.
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
