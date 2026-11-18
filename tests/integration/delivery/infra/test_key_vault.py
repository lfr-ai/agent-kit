"""Offline Azure Key Vault evidence from installed tools; never a deployment."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final

import pytest
from tests.integration.delivery.infra import iac

if TYPE_CHECKING:
    from collections.abc import Mapping
    import subprocess

pytestmark = pytest.mark.integration
SOURCE: Final[Path] = (
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/key-vault"
)
# The pinned AzAPI provider starts slowly; one mocked test run can take minutes.
TIMEOUT_SECONDS: Final[int] = 900
NAME_LENGTH: Final[tuple[int, int]] = (3, 24)
PRINCIPAL_LENGTH: Final[int] = 36
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
SECRETS_USER_ROLE: Final[str] = "4633458b-17de-408a-b874-0445c86b69e6"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/vault"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.vaultcore.azure.net"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
MESSAGES: Final[dict[str, str]] = {
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.vaultcore.azure.net zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.vaultcore.azure.net private DNS zone ARM ID."
    ),
    "prod_workspace": (
        "Staging and production require logAnalyticsWorkspaceId: an existing "
        "Log Analytics workspace for audit logs."
    ),
    "public_stage": (
        "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
    ),
    "ranges_need_public": "allowedIpRanges needs allowPublicNetworkAccess.",
    "ip_range": (
        "allowedIpRanges must hold IPv4 addresses or CIDR ranges, "
        "such as 203.0.113.0/24."
    ),
    "workspace_empty": "logAnalyticsWorkspaceId must be omitted or non-empty.",
}
# Platform defaults for Microsoft.KeyVault/vaults@2026-02-01 must not be restated;
# RBAC authorization and soft delete are declared on purpose to revert drift.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "softDeleteRetentionInDays",
    "enabledForDeployment",
    "enabledForTemplateDeployment",
    "enabledForDiskEncryption",
)
_PRIVATE = (SUBNET, ZONE)
_GUARDED_STAGES = ("staging", "prod")
_WorkspaceCase = tuple[str, str | None, str | None]
_NetworkCase = tuple[str, tuple[str, str] | None, str | None]
_PublicCase = tuple[str, tuple[str, str] | None, bool, list[str], str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    ("dev", (SUBNET, ZONE.replace("vaultcore", "VaultCore")), "network"),
    ("dev", (SUBNET, ZONE.replace("vaultcore.azure.net", "azurecr.io")), "network"),
    ("dev", (SUBNET, f"{ZONE}/extra"), "network"),
    ("test", (SUBNET, ""), "network"),
    ("dev", (SUBNET.replace("/subnets/", "/subnet/"), ZONE), "network"),
    ("dev", (SUBNET.rsplit("/subnets/", 1)[0], ZONE), "network"),
)
PUBLIC_CASES: Final[tuple[_PublicCase, ...]] = (
    ("dev", None, False, [], None),
    ("test", None, True, [], None),
    ("dev", None, True, ["203.0.113.0/24", "198.51.100.7"], None),
    ("prod", _PRIVATE, True, [], "public_stage"),
    ("staging", _PRIVATE, True, [], "public_stage"),
    ("dev", _PRIVATE, True, [], "public_stage"),
    ("dev", None, False, ["203.0.113.0/24"], "ranges_need_public"),
    ("dev", None, True, ["203.0.113"], "ip_range"),
    ("test", None, True, ["203.0.113.0/"], "ip_range"),
    ("dev", None, True, ["2001:db8::/32"], "ip_range"),
)
WORKSPACE_CASES: Final[tuple[_WorkspaceCase, ...]] = (
    ("dev", None, None),
    ("test", WORKSPACE, None),
    ("staging", WORKSPACE, None),
    ("prod", WORKSPACE, None),
    ("prod", None, "prod_workspace"),
    ("staging", None, "prod_workspace"),
    ("dev", "", "workspace_empty"),
    ("prod", "", "workspace_empty"),
)
# Bicep enforces these with native decorators; Terraform with validation blocks.
NATIVE_TERRAFORM_CASES: Final[tuple[tuple[dict[str, object], str | None], ...]] = (
    ({"name": "a" * NAME_LENGTH[0]}, None),
    ({"name": "a" * NAME_LENGTH[1]}, None),
    ({"name": "a" * (NAME_LENGTH[0] - 1)}, "name"),
    ({"name": "a" * (NAME_LENGTH[1] + 1)}, "name"),
    ({"principal_id": "not-a-guid"}, "principal_id"),
    ({"stage": "production"}, "stage"),
    ({"location": " "}, "location"),
    ({"resource_group_id": "example"}, "resource_group_id"),
)


def _run(name: str, workdir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return iac.run(name, workdir, *arguments, timeout=TIMEOUT_SECONDS)


def _bicep_public(case: _PublicCase) -> str:
    stage, network, allow, ranges, _ = case
    return (
        f"requirePublicAccess('{stage}', {str(network is not None).lower()}, "
        f"{str(allow).lower()}, {ranges!r})"
    )


def _bicep_string(value: str | None) -> str:
    return "null" if value is None else f"'{value}'"


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *(
            (f"requirePrivateEndpoint('{stage}', {iac.bicep_network(network)})", error)
            for stage, network, error in NETWORK_CASES
        ),
        *((_bicep_public(case), case[-1]) for case in PUBLIC_CASES),
        *(
            (f"requireWorkspace('{stage}', {_bicep_string(workspace)})", error)
            for stage, workspace, error in WORKSPACE_CASES
        ),
    ]


def _public_variable(error: str | None) -> str | None:
    if error is None:
        return None
    if error == "public_stage":
        return "allow_public_network_access"
    return "allowed_ip_ranges"


def _terraform_cases() -> list[tuple[Mapping[str, object], str | None]]:
    # Guarded stages add the other required inputs so only one guard fails.
    private = {"private_endpoint": iac.terraform_network(_PRIVATE)}
    diagnostics = {"log_analytics_workspace_id": WORKSPACE}
    return [
        *(
            (
                {"stage": stage, "private_endpoint": iac.terraform_network(network)}
                | (diagnostics if stage in _GUARDED_STAGES else {}),
                error and "private_endpoint",
            )
            for stage, network, error in NETWORK_CASES
        ),
        *(
            (
                {
                    "stage": stage,
                    "private_endpoint": iac.terraform_network(network),
                    "allow_public_network_access": allow,
                    "allowed_ip_ranges": ranges,
                }
                | (diagnostics if stage in _GUARDED_STAGES else {}),
                _public_variable(error),
            )
            for stage, network, allow, ranges, error in PUBLIC_CASES
        ),
        *(
            (
                {"stage": stage, "log_analytics_workspace_id": workspace}
                | (private if stage in _GUARDED_STAGES else {}),
                error and "log_analytics_workspace_id",
            )
            for stage, workspace, error in WORKSPACE_CASES
        ),
        *NATIVE_TERRAFORM_CASES,
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/key-vault")


def test_sources_are_self_contained_and_never_expose_secrets(relocated: Path) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for forbidden in ("listKeys", "listSecrets", "accessPolicies", "/secrets@"):
        assert forbidden not in bicep + terraform, forbidden
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    declared = iac.shared_resource_types(bicep, terraform)
    assert len(declared) == 6
    assert "Microsoft.KeyVault/vaults@2026-02-01" in declared


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    template = json.loads(iac.build_bicep(folder, _run))
    resources = template["resources"]
    by_type = {resource["type"]: resource for resource in resources.values()}
    assert len(resources) == len(by_type) == 6
    vault = by_type["Microsoft.KeyVault/vaults"]
    assert vault["apiVersion"] == "2026-02-01"
    # Purge protection is merged in for staging and production; public access is
    # disabled unless a dev or test caller opts in to a deny-by-default allow list.
    properties = vault["properties"]
    assert properties.startswith("[union(createObject('tenantId', tenant().tenantId")
    assert "'enableRbacAuthorization', true(), 'enableSoftDelete', true()" in properties
    assert (
        "if(contains(createArray('staging', 'prod'), parameters('stage')), "
        "createObject('enablePurgeProtection', true()), createObject())"
    ) in properties
    assert (
        "if(parameters('allowPublicNetworkAccess'), createObject('networkAcls', "
        "createObject('defaultAction', 'Deny', 'ipRules'"
    ) in properties
    assert "createObject('publicNetworkAccess', 'Disabled')" in properties
    role = by_type["Microsoft.Authorization/roleAssignments"]
    assert role["properties"]["principalType"] == "ServicePrincipal"
    assert template["variables"]["secretsUserRoleId"] == SECRETS_USER_ROLE
    assert "variables('secretsUserRoleId')" in role["properties"]["roleDefinitionId"]
    endpoint = by_type["Microsoft.Network/privateEndpoints"]
    connection = endpoint["properties"]["privateLinkServiceConnections"][0]
    assert connection["properties"]["groupIds"] == ["vault"]
    diagnostics = by_type["Microsoft.Insights/diagnosticSettings"]
    assert diagnostics["condition"] == (
        "[not(equals(variables('workspaceId'), null()))]"
    )
    assert diagnostics["properties"] == {
        "workspaceId": "[variables('workspaceId')]",
        "logs": [{"category": "AuditEvent", "enabled": True}],
    }
    lock = by_type["Microsoft.Authorization/locks"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert "scope" in lock
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    for optional in (
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Network/privateEndpoints/privateDnsZoneGroups",
    ):
        assert "condition" in by_type[optional]
    assert set(template["outputs"]) == {"vaultResourceId", "vaultUri"}
    _assert_inputs(template["parameters"], template["variables"])
    iac.build_examples(folder, _run)


def _assert_inputs(
    parameters: Mapping[str, Mapping[str, object]], variables: Mapping[str, object]
) -> None:
    """Parameters match the Terraform variables; guards stay in the template."""
    for required in ("location", "name", "stage", "principalId"):
        assert "defaultValue" not in parameters[required]
    # The same limits as the Terraform validation blocks.
    assert (parameters["name"]["minLength"], parameters["name"]["maxLength"]) == (
        NAME_LENGTH
    )
    assert parameters["principalId"]["minLength"] == PRINCIPAL_LENGTH
    assert parameters["principalId"]["maxLength"] == PRINCIPAL_LENGTH
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["privateEndpoint"]["nullable"] is True
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(variables) == {"network", "ipRanges", "workspaceId"}


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"\(stage, \{.*?\}\)", "(stage, null)", "prod_network"),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, null)",
            "prod_workspace",
        ),
        ("privatelink.vaultcore.azure.net'", "privatelink.azurecr.io'", "network"),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    example = relocated / "bicep/tests/prod.bicepparam"
    stderr = iac.rejected_example(example, _run, pattern, replacement, flags=re.DOTALL)
    assert MESSAGES[error] in stderr, stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    imports = ("requirePrivateEndpoint", "requirePublicAccess", "requireWorkspace")
    iac.assert_bicep_guards(
        relocated / "bicep", _run, imports, _bicep_cases(), MESSAGES
    )


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": NETWORK_GROUP,
        "location": "westeurope",
        "name": "sample-dev-kv",
        "stage": "dev",
        "principal_id": PRINCIPAL,
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run)
    iac.mock_plans(folder, _run)
