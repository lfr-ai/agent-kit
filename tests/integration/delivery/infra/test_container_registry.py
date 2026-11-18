"""Offline Azure Container Registry evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/container-registry"
)
# The pinned AzAPI provider starts slowly; one mocked test run can take minutes.
TIMEOUT_SECONDS: Final[int] = 900
NAME_LENGTH: Final[tuple[int, int]] = (5, 50)
PRINCIPAL_LENGTH: Final[int] = 36
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
PUSHER: Final[str] = "11111111-1111-1111-1111-111111111111"
ACR_PULL_ROLE: Final[str] = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
ACR_PUSH_ROLE: Final[str] = "8311e382-0749-4cb8-b61a-304f252e45ec"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/"
    "subnets/registry"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
MESSAGES: Final[dict[str, str]] = {
    "sku": "Staging, production and privateEndpoint require sku Premium.",
    "sku_public": (
        "Basic and Standard need allowPublicNetworkAccess without allowedIpRanges; "
        "private access and IP rules require sku Premium."
    ),
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.azurecr.io zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a privatelink.azurecr.io "
        "private DNS zone ARM ID."
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
# Platform defaults for registries@2025-11-01 that must never be restated. The
# admin user and anonymous pull are the exception: both are disabled explicitly.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "zoneRedundancy",
    "networkRuleBypassOptions",
    "roleAssignmentMode",
    "dataEndpointEnabled",
)
_PRIVATE = (SUBNET, ZONE)
_RANGES = ["203.0.113.0/24"]
_GUARDED_STAGES = ("staging", "prod")
# stage, sku, has private endpoint, allow public access, has IP ranges, error
_SkuCase = tuple[str, str, bool, bool, bool, str | None]
_WorkspaceCase = tuple[str, str | None, str | None]
_NetworkCase = tuple[str, tuple[str, str] | None, str | None]
_PublicCase = tuple[str, tuple[str, str] | None, bool, list[str], str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
SKU_CASES: Final[tuple[_SkuCase, ...]] = (
    ("dev", "Basic", False, True, False, None),
    ("test", "Standard", False, True, False, None),
    ("dev", "Premium", False, False, False, None),
    ("dev", "Premium", False, True, True, None),
    ("test", "Premium", True, False, False, None),
    ("staging", "Premium", True, False, False, None),
    ("prod", "Premium", True, False, False, None),
    ("prod", "Standard", True, False, False, "sku"),
    ("staging", "Standard", True, False, False, "sku"),
    ("prod", "Basic", True, False, False, "sku"),
    ("dev", "Basic", True, False, False, "sku"),
    ("test", "Standard", True, False, False, "sku"),
    ("dev", "Basic", False, False, False, "sku_public"),
    ("test", "Standard", False, True, True, "sku_public"),
)
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    ("dev", (SUBNET, ZONE.replace("azurecr", "AzureCR")), "network"),
    ("dev", (SUBNET, ZONE.replace("azurecr.io", "vaultcore.azure.net")), "network"),
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
# Bicep uses native decorators and types; Terraform uses validation blocks.
NATIVE_TERRAFORM_CASES: Final[tuple[tuple[dict[str, object], str | None], ...]] = (
    ({"name": "a" * NAME_LENGTH[0]}, None),
    ({"name": "a" * NAME_LENGTH[1]}, None),
    ({"name": "a" * (NAME_LENGTH[0] - 1)}, "name"),
    ({"name": "a" * (NAME_LENGTH[1] + 1)}, "name"),
    ({"pull_principal_id": "not-a-guid"}, "pull_principal_id"),
    ({"push_principal_id": PUSHER}, None),
    ({"push_principal_id": None}, None),
    ({"push_principal_id": "not-a-guid"}, "push_principal_id"),
    ({"sku": "Classic"}, "sku"),
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


def _bicep_sku(case: _SkuCase) -> str:
    stage, sku, private, allow, ranges, _ = case
    flags = ", ".join(str(flag).lower() for flag in (private, allow, ranges))
    return f"requireSku('{stage}', '{sku}', {flags})"


def _bicep_string(value: str | None) -> str:
    return "null" if value is None else f"'{value}'"


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *((_bicep_sku(case), case[-1]) for case in SKU_CASES),
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
    # Other inputs are added so only one guard fails; Premium allows private access.
    private = {"private_endpoint": iac.terraform_network(_PRIVATE)}
    premium = {"sku": "Premium"}
    diagnostics = {"log_analytics_workspace_id": WORKSPACE}
    return [
        *(
            (
                {
                    "stage": stage,
                    "sku": sku,
                    "allow_public_network_access": allow,
                    "allowed_ip_ranges": _RANGES if ranges else [],
                }
                | (private if has_private else {})
                | (diagnostics if stage in _GUARDED_STAGES else {}),
                error and "sku",
            )
            for stage, sku, has_private, allow, ranges, error in SKU_CASES
        ),
        *(
            (
                {"stage": stage, "private_endpoint": iac.terraform_network(network)}
                | premium
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
                | premium
                | (diagnostics if stage in _GUARDED_STAGES else {}),
                _public_variable(error),
            )
            for stage, network, allow, ranges, error in PUBLIC_CASES
        ),
        *(
            (
                {"stage": stage, "log_analytics_workspace_id": workspace}
                | premium
                | (private if stage in _GUARDED_STAGES else {}),
                error and "log_analytics_workspace_id",
            )
            for stage, workspace, error in WORKSPACE_CASES
        ),
        # The baseline is Basic, which needs the explicit public opt-in.
        *(
            ({"allow_public_network_access": True} | values, error)
            for values, error in NATIVE_TERRAFORM_CASES
        ),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/container-registry")


def test_sources_are_self_contained_and_never_expose_credentials(
    relocated: Path,
) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for forbidden in ("listCredentials", "/tokens@", "/scopeMaps@"):
        assert forbidden not in bicep + terraform, forbidden
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    # Entra ID roles are the only registry credential in both flavours.
    for credential in ("adminUserEnabled", "anonymousPullEnabled"):
        assert f"{credential}: false" in bicep, credential
        assert re.search(rf"\b{credential}\s+= false\n", terraform), credential
    # Retention keeps its default period; only the status is set.
    assert "retentionPolicy: { status: 'enabled' }" in bicep
    assert 'retentionPolicy = { status = "enabled" }' in terraform
    declared = iac.shared_resource_types(bicep, terraform)
    assert len(declared) == 6
    assert "Microsoft.ContainerRegistry/registries@2025-11-01" in declared


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _assert_roles(
    resources: Mapping[str, Mapping[str, object]], variables: Mapping[str, object]
) -> None:
    """AcrPull always goes to the app; AcrPush only to a supplied CI identity."""
    pull, push = resources["pull"], resources["push"]
    assert "condition" not in pull
    assert push["condition"] == "[not(equals(parameters('pushPrincipalId'), null()))]"
    assert (variables["acrPullRoleId"], variables["acrPushRoleId"]) == (
        ACR_PULL_ROLE,
        ACR_PUSH_ROLE,
    )
    for assignment, role in ((pull, "acrPullRoleId"), (push, "acrPushRoleId")):
        assert assignment["type"] == "Microsoft.Authorization/roleAssignments"
        properties = _mapping(assignment["properties"])
        assert f"variables('{role}')" in str(properties["roleDefinitionId"])
        assert properties["principalType"] == "ServicePrincipal"


def _assert_inputs(
    parameters: Mapping[str, Mapping[str, object]], variables: Mapping[str, object]
) -> None:
    """Parameters match the Terraform variables; guards stay in the template."""
    for required in ("location", "name", "stage", "pullPrincipalId"):
        assert "defaultValue" not in parameters[required]
    # The same limits as the Terraform validation blocks.
    assert (parameters["name"]["minLength"], parameters["name"]["maxLength"]) == (
        NAME_LENGTH
    )
    for principal in ("pullPrincipalId", "pushPrincipalId"):
        assert parameters[principal]["minLength"] == PRINCIPAL_LENGTH
        assert parameters[principal]["maxLength"] == PRINCIPAL_LENGTH
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["pushPrincipalId"]["nullable"] is True
    assert parameters["sku"]["defaultValue"] == "Basic"
    assert parameters["privateEndpoint"]["nullable"] is True
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(variables) == {
        "network",
        "checkedSku",
        "ipRanges",
        "workspaceId",
    }


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    template = json.loads(iac.build_bicep(folder, _run))
    resources = template["resources"]
    by_type = {resource["type"]: resource for resource in resources.values()}
    # Two role assignments share one type; every other type appears once.
    assert len(resources) == 7
    assert len(by_type) == 6
    registry = by_type["Microsoft.ContainerRegistry/registries"]
    assert registry["sku"] == {"name": "[variables('checkedSku')]"}
    assert set(template["definitions"]["Sku"]["allowedValues"]) == {
        "Basic",
        "Standard",
        "Premium",
    }
    # Public access is disabled unless dev or test opts in; Premium then denies all
    # but the allow list. Production also enables untagged-manifest retention.
    properties = registry["properties"]
    assert properties.startswith(
        "[union(createObject('adminUserEnabled', false(), "
        "'anonymousPullEnabled', false()), "
    )
    assert "createObject('publicNetworkAccess', 'Disabled')" in properties
    assert (
        "createObject('networkRuleSet', createObject('defaultAction', 'Deny', 'ipRules'"
    ) in properties
    assert (
        "if(equals(parameters('stage'), 'prod'), createObject('policies', "
        "createObject('retentionPolicy', createObject('status', 'enabled')))"
    ) in properties
    _assert_roles(resources, template["variables"])
    endpoint = by_type["Microsoft.Network/privateEndpoints"]
    connection = endpoint["properties"]["privateLinkServiceConnections"][0]
    assert connection["properties"]["groupIds"] == ["registry"]
    diagnostics = by_type["Microsoft.Insights/diagnosticSettings"]
    assert diagnostics["condition"] == (
        "[not(equals(variables('workspaceId'), null()))]"
    )
    assert diagnostics["properties"] == {
        "workspaceId": "[variables('workspaceId')]",
        "logs": [
            {"category": "ContainerRegistryLoginEvents", "enabled": True},
            {"category": "ContainerRegistryRepositoryEvents", "enabled": True},
        ],
    }
    lock = by_type["Microsoft.Authorization/locks"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert set(template["outputs"]) == {"registryResourceId", "loginServer"}
    _assert_inputs(template["parameters"], template["variables"])
    iac.build_examples(folder, _run)


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"requireSku\(stage, 'Premium'", "requireSku(stage, 'Standard'", "sku"),
        (r"\(stage, \{.*?\}\)", "(stage, null)", "prod_network"),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, null)",
            "prod_workspace",
        ),
        (r"privatelink\.azurecr\.io'", "privatelink.vaultcore.azure.net'", "network"),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    example = relocated / "bicep/tests/prod.bicepparam"
    stderr = iac.rejected_example(example, _run, pattern, replacement, flags=re.DOTALL)
    assert MESSAGES[error] in stderr, stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    imports = (
        "requireSku",
        "requirePrivateEndpoint",
        "requirePublicAccess",
        "requireWorkspace",
    )
    iac.assert_bicep_guards(
        relocated / "bicep", _run, imports, _bicep_cases(), MESSAGES
    )


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": NETWORK_GROUP,
        "location": "westeurope",
        "name": "sampledevacr",
        "stage": "dev",
        "pull_principal_id": PRINCIPAL,
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run)
    iac.mock_plans(folder, _run)
