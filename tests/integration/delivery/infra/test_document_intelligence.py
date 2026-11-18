"""Offline Document Intelligence evidence from installed tools; never a deployment."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final
import uuid

import pytest
from tests.integration.delivery.infra import iac

if TYPE_CHECKING:
    from collections.abc import Mapping
    import subprocess

pytestmark = pytest.mark.integration
SOURCE: Final[Path] = (
    Path(__file__).resolve().parents[4]
    / "packages/delivery/infra/document-intelligence"
)
TIMEOUT_SECONDS: Final[int] = 300
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/docs"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.cognitiveservices.azure.com"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
COGNITIVE_SERVICES_USER: Final[str] = "a97b65f3-24c7-4388-baec-2e87135dc908"
# ARM guid() is UUIDv5 over its '-'-joined arguments in this namespace.
ARM_GUID_NAMESPACE: Final[uuid.UUID] = uuid.UUID("11fb06fb-712d-4ddd-98c7-e71bbd588830")
ACCOUNT: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
    "/providers/Microsoft.CognitiveServices/accounts/sample-docs-dev"
)
MESSAGES: Final[dict[str, str]] = {
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.cognitiveservices.azure.com zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.cognitiveservices.azure.com private DNS zone ARM ID."
    ),
    "prod_workspace": (
        "Staging and production require logAnalyticsWorkspaceId: an existing "
        "Log Analytics workspace for diagnostics."
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
# Platform defaults that the sources must never restate; networkAcls is set only
# for the explicit public opt-in.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "restrictOutboundNetworkAccess",
    "dynamicThrottlingEnabled",
    "apiProperties",
    "encryption",
    "userOwnedStorage",
)
_Network = tuple[str, str]
_NetworkCase = tuple[str, _Network | None, str | None]
_WorkspaceCase = tuple[str, str | None, str | None]
_PublicCase = tuple[str, _Network | None, bool, list[str], str | None]
_PRIVATE = (SUBNET, ZONE)
_GUARDED_STAGES = ("staging", "prod")
# Shared positive/negative tables drive both the Bicep and Terraform guards.
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", (SUBNET, ZONE.upper()), "network"),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    ("dev", (SUBNET, ""), "network"),
    ("dev", (SUBNET, ZONE.replace("cognitiveservices", "openai")), "network"),
    ("dev", (SUBNET, f"{ZONE}/extra"), "network"),
    ("dev", (SUBNET, ZONE.replace("/privatelink.", "/example.")), "network"),
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
    # Guarded stages add the other required input so only one guard fails.
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
        ({"name": "a1"}, None),
        ({"name": "a"}, "name"),
        ({"name": "a" * 65}, "name"),
        ({"stage": "production"}, "stage"),
        ({"location": " "}, "location"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/document-intelligence")


def test_sources_are_self_contained_and_never_expose_keys(relocated: Path) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for forbidden in ("listKeys", "listSecrets"):
        assert forbidden not in bicep
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    assert len(iac.shared_resource_types(bicep, terraform)) == 6
    assert COGNITIVE_SERVICES_USER in bicep
    assert COGNITIVE_SERVICES_USER in terraform


def _assert_network_and_protection(
    resources: Mapping[str, Mapping[str, object]],
) -> None:
    """Private endpoint, diagnostics and lock stay optional and resource-scoped."""
    endpoint = resources["endpoint"]
    assert endpoint["properties"] == {
        "subnet": {"id": "[variables('network').subnetId]"},
        "privateLinkServiceConnections": [
            {
                "name": "[parameters('name')]",
                "properties": {
                    "privateLinkServiceId": (
                        "[resourceId('Microsoft.CognitiveServices/accounts', "
                        "parameters('name'))]"
                    ),
                    "groupIds": ["account"],
                },
            }
        ],
    }
    for optional in ("endpoint", "dnsZoneGroup"):
        assert resources[optional]["condition"] == (
            "[not(equals(variables('network'), null()))]"
        )
    diagnostics = resources["diagnostics"]
    assert diagnostics["condition"] == (
        "[not(equals(variables('workspaceId'), null()))]"
    )
    assert diagnostics["properties"] == {
        "workspaceId": "[variables('workspaceId')]",
        "logs": [{"categoryGroup": "allLogs", "enabled": True}],
        "metrics": [{"category": "AllMetrics", "enabled": True}],
    }
    lock = resources["protection"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert "scope" in lock


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    template = json.loads(iac.build_bicep(folder, _run))
    resources = template["resources"]
    assert len(resources) == 6
    account = resources["account"]
    assert account["kind"] == "FormRecognizer"
    assert account["sku"] == {"name": "S0"}
    assert set(account) & {"identity", "zones"} == set()
    # Public access is disabled unless dev or test opts in to a deny-by-default ACL.
    properties = account["properties"]
    for fragment in (
        "'customSubDomainName', parameters('name')",
        "'disableLocalAuth', true()",
        (
            "'publicNetworkAccess', if(parameters('allowPublicNetworkAccess'), "
            "'Enabled', 'Disabled')"
        ),
        (
            "if(parameters('allowPublicNetworkAccess'), createObject('networkAcls', "
            "createObject('defaultAction', 'Deny', 'ipRules'"
        ),
    ):
        assert fragment in properties, fragment
    assert template["variables"]["cognitiveServicesUser"] == COGNITIVE_SERVICES_USER
    assert resources["analyzeAccess"]["properties"] == {
        "roleDefinitionId": (
            "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
            "variables('cognitiveServicesUser'))]"
        ),
        "principalId": "[parameters('principalId')]",
        "principalType": "ServicePrincipal",
    }
    _assert_network_and_protection(resources)
    assert set(template["outputs"]) == {"documentIntelligenceResourceId", "endpoint"}
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "principalId"):
        assert "defaultValue" not in parameters[required]
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
    assert iac.guarded(template["variables"]) == {"network", "ipRanges", "workspaceId"}
    iac.build_examples(folder, _run)


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"\(stage, \{.*?\}\)", "(stage, null)", "prod_network"),
        (
            "privatelink.cognitiveservices.azure.com'",
            "privatelink.openai.azure.com'",
            "network",
        ),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, null)",
            "prod_workspace",
        ),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    example = relocated / "bicep/tests/prod.bicepparam"
    stderr = iac.rejected_example(example, _run, pattern, replacement, flags=re.DOTALL)
    assert MESSAGES[error] in stderr, stderr


@pytest.mark.parametrize(
    ("pattern", "replacement", "diagnostic"),
    [
        ("'sample-docs-dev'", "'a'", "BCP333"),
        ("'sample-docs-dev'", f"'{'a' * 65}'", "BCP332"),
        ("'dev'", "'production'", "BCP033"),
    ],
)
def test_bicep_native_constraints_reject_development_example(
    relocated: Path, pattern: str, replacement: str, diagnostic: str
) -> None:
    example = relocated / "bicep/tests/dev.bicepparam"
    stderr = iac.rejected_example(example, _run, re.escape(pattern), replacement)
    assert f"Error {diagnostic}" in stderr, stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    imports = ("requirePrivateEndpoint", "requirePublicAccess", "requireWorkspace")
    expected_name = uuid.uuid5(
        ARM_GUID_NAMESPACE, f"{ACCOUNT}-{PRINCIPAL}-{COGNITIVE_SERVICES_USER}"
    )
    rendered = iac.assert_bicep_guards(
        relocated / "bicep",
        _run,
        imports,
        _bicep_cases(),
        MESSAGES,
        # Terraform's uuidv5() name (asserted in its mocked plan) equals Bicep guid().
        extra=(
            f"param roleName = guid('{ACCOUNT}', '{PRINCIPAL}', "
            f"'{COGNITIVE_SERVICES_USER}')\n"
        ),
    )
    values = json.loads(json.loads(rendered)["parametersJson"])["parameters"]
    assert values["roleName"]["value"] == str(expected_name)
    tftest = (SOURCE / "terraform/tests/document-intelligence.tftest.hcl").read_text(
        encoding="utf-8"
    )
    assert f'"{expected_name}"' in tftest


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": NETWORK_GROUP,
        "location": "westeurope",
        "name": "sample-docs-dev",
        "stage": "dev",
        "principal_id": PRINCIPAL,
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run)
    output = iac.mock_plans(folder, _run)
    assert "Success! 7 passed, 0 failed." in output, output
