"""Offline Microsoft Foundry evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/ai-foundry"
)
TIMEOUT_SECONDS: Final[int] = 300
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/ai"
)
ZONES: Final[tuple[str, ...]] = tuple(
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/privatelink.{zone}"
    for zone in (
        "cognitiveservices.azure.com",
        "openai.azure.com",
        "services.ai.azure.com",
    )
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
OPENAI_USER: Final[str] = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
FOUNDRY_USER: Final[str] = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
# ARM guid() is UUIDv5 over its '-'-joined arguments in this namespace.
ARM_GUID_NAMESPACE: Final[uuid.UUID] = uuid.UUID("11fb06fb-712d-4ddd-98c7-e71bbd588830")
ACCOUNT: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
    "/providers/Microsoft.CognitiveServices/accounts/sample-foundry-dev"
)
PROJECT: Final[str] = f"{ACCOUNT}/projects/sample-foundry-dev"
MESSAGES: Final[dict[str, str]] = {
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "the three Foundry private DNS zones."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and the "
        "privatelink.cognitiveservices.azure.com, privatelink.openai.azure.com and "
        "privatelink.services.ai.azure.com private DNS zone ARM IDs."
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
    "all_clients": (
        "allowAllPublicClients needs allowPublicNetworkAccess and no allowedIpRanges."
    ),
    "workspace_empty": "logAnalyticsWorkspaceId must be omitted or non-empty.",
}
# Platform defaults that the sources must never restate; networkAcls is set only
# for the explicit public opt-in.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "restrictOutboundNetworkAccess",
    "dynamicThrottlingEnabled",
    "versionUpgradeOption",
    "raiPolicyName",
    "apiProperties",
    "encryption",
    "userOwnedStorage",
)
_Network = tuple[str, tuple[str, ...]]
_NetworkCase = tuple[str, _Network | None, str | None]
_WorkspaceCase = tuple[str, str | None, str | None]
_PublicCase = tuple[str, _Network | None, bool, list[str], str | None]
_PRIVATE = (SUBNET, ZONES)
_GUARDED_STAGES = ("staging", "prod")
# Shared positive/negative tables drive both the Bicep and Terraform guards.
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", (SUBNET, ZONES[::-1]), None),
    ("prod", (SUBNET, (ZONES[0].upper(), *ZONES[1:])), "network"),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    ("dev", (SUBNET, ()), "network"),
    ("dev", (SUBNET, ZONES[:2]), "network"),
    ("dev", (SUBNET, (*ZONES[:2], ZONES[1])), "network"),
    ("dev", (SUBNET, (*ZONES, ZONES[0])), "network"),
    (
        "dev",
        (
            SUBNET,
            (*ZONES[:2], ZONES[2].replace("services.ai.azure.com", "api.azureml.ms")),
        ),
        "network",
    ),
    ("dev", (SUBNET, (*ZONES[:2], f"{ZONES[2]}/extra")), "network"),
    (
        "dev",
        (SUBNET, (*ZONES[:2], ZONES[2].replace("/privateDnsZones/", "/dnsZones/"))),
        "network",
    ),
    ("dev", (SUBNET.replace("/subnets/", "/subnet/"), ZONES), "network"),
    ("dev", (SUBNET.rsplit("/subnets/", 1)[0], ZONES), "network"),
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
# Rows: public opt-in, IP ranges, all-clients opt-in, expected error.
ALL_CLIENTS_CASES: Final[tuple[tuple[bool, list[str], bool, str | None], ...]] = (
    (False, [], False, None),
    (True, ["203.0.113.0/24"], False, None),
    (True, [], True, None),
    (False, [], True, "all_clients"),
    (True, ["203.0.113.0/24"], True, "all_clients"),
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


def _bicep_network(network: _Network | None) -> str:
    if network is None:
        return "null"
    zones = ", ".join(f"'{zone}'" for zone in network[1])
    return f"{{ subnetId: '{network[0]}', privateDnsZoneIds: [{zones}] }}"


def _terraform_network(network: _Network | None) -> dict[str, object] | None:
    if network is None:
        return None
    return {"subnet_id": network[0], "private_dns_zone_ids": list(network[1])}


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
            (f"requirePrivateEndpoint('{stage}', {_bicep_network(network)})", error)
            for stage, network, error in NETWORK_CASES
        ),
        *((_bicep_public(case), case[-1]) for case in PUBLIC_CASES),
        *(
            (
                (
                    f"requireAllClients({str(allow).lower()}, {ranges!r}, "
                    f"{str(allow_all).lower()})"
                ),
                error,
            )
            for allow, ranges, allow_all, error in ALL_CLIENTS_CASES
        ),
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
    private = {"private_endpoint": _terraform_network(_PRIVATE)}
    diagnostics = {"log_analytics_workspace_id": WORKSPACE}
    return [
        *(
            (
                {"stage": stage, "private_endpoint": _terraform_network(network)}
                | (diagnostics if stage in _GUARDED_STAGES else {}),
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
                    "allowed_ip_ranges": ranges,
                }
                | (diagnostics if stage in _GUARDED_STAGES else {}),
                _public_variable(error),
            )
            for stage, network, allow, ranges, error in PUBLIC_CASES
        ),
        *(
            (
                {
                    "allow_public_network_access": allow,
                    "allowed_ip_ranges": ranges,
                    "allow_all_public_clients": allow_all,
                },
                error and "allow_all_public_clients",
            )
            for allow, ranges, allow_all, error in ALL_CLIENTS_CASES
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
    return iac.relocate(SOURCE, tmp_path / "consumer/ai-foundry")


def test_sources_are_self_contained_and_never_expose_keys(relocated: Path) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for forbidden in ("listKeys", "listSecrets"):
        assert forbidden not in bicep
    # No model is hard-coded; examples live only in tests/dev.bicepparam and README.
    assert "gpt-" not in bicep + terraform
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    assert len(iac.shared_resource_types(bicep, terraform)) == 8
    for role in (OPENAI_USER, FOUNDRY_USER):
        assert role in bicep
        assert role in terraform


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
    # The endpoint binds only after the account, project and deployments settle.
    assert endpoint["dependsOn"] == ["foundry", "modelDeployments", "project"]
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
    assert len(resources) == 9
    foundry = resources["foundry"]
    assert foundry["kind"] == "AIServices"
    assert foundry["identity"] == {"type": "SystemAssigned"}
    # Public access is disabled unless dev or test opts in to a deny-by-default ACL.
    properties = foundry["properties"]
    for fragment in (
        "'allowProjectManagement', true()",
        "'customSubDomainName', parameters('name')",
        "'disableLocalAuth', true()",
        (
            "'publicNetworkAccess', if(parameters('allowPublicNetworkAccess'), "
            "'Enabled', 'Disabled')"
        ),
        (
            "if(parameters('allowPublicNetworkAccess'), createObject('networkAcls', "
            "createObject('defaultAction', variables('aclDefault'), 'ipRules'"
        ),
    ):
        assert fragment in properties, fragment
    assert resources["project"]["properties"] == {}
    deployments = resources["modelDeployments"]
    assert deployments["copy"]["mode"] == "serial"
    assert deployments["copy"]["batchSize"] == 1
    assert "project" in deployments["dependsOn"]
    assert deployments["properties"]["model"]["format"] == (
        "[coalesce(tryGet(parameters('deployments')[copyIndex()], 'format'), 'OpenAI')]"
    )
    for assignment, variable, role in (
        ("inferenceAccess", "openAiUser", OPENAI_USER),
        ("projectAccess", "foundryUser", FOUNDRY_USER),
    ):
        assert template["variables"][variable] == role
        assert resources[assignment]["properties"] == {
            "roleDefinitionId": (
                "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
                f"variables('{variable}'))]"
            ),
            "principalId": "[parameters('principalId')]",
            "principalType": "ServicePrincipal",
        }
    _assert_network_and_protection(resources)
    assert set(template["outputs"]) == {
        "foundryResourceId",
        "projectResourceId",
        "openAiEndpoint",
        "projectEndpoint",
    }
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "principalId"):
        assert "defaultValue" not in parameters[required]
    assert parameters["deployments"]["defaultValue"] == []
    assert parameters["privateEndpoint"]["nullable"] is True
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    assert parameters["allowAllPublicClients"]["defaultValue"] is False
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(template["variables"]) == {
        "network",
        "ipRanges",
        "aclDefault",
        "workspaceId",
    }
    iac.build_examples(folder, _run)


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"\(stage, \{.*?\}\)", "(stage, null)", "prod_network"),
        (r"\s*'[^']*privatelink\.openai\.azure\.com'", "", "network"),
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
        ("'sample-foundry-dev'", "'a'", "BCP333"),
        ("'sample-foundry-dev'", f"'{'a' * 65}'", "BCP332"),
        ("'dev'", "'production'", "BCP033"),
        ("    capacity: 10\n", "", "BCP035"),
        ("    capacity: 10\n", "    capacity: 10\n    raiPolicyName: 'x'\n", "BCP037"),
    ],
)
def test_bicep_native_constraints_reject_development_example(
    relocated: Path, pattern: str, replacement: str, diagnostic: str
) -> None:
    example = relocated / "bicep/tests/dev.bicepparam"
    stderr = iac.rejected_example(example, _run, re.escape(pattern), replacement)
    assert f"Error {diagnostic}" in stderr, stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    imports = (
        "requirePrivateEndpoint",
        "requirePublicAccess",
        "requireAllClients",
        "requireWorkspace",
    )
    grants = {
        "inferenceName": (ACCOUNT, OPENAI_USER, "inference_access"),
        "projectName": (PROJECT, FOUNDRY_USER, "project_access"),
    }
    rendered = iac.assert_bicep_guards(
        relocated / "bicep",
        _run,
        imports,
        _bicep_cases(),
        MESSAGES,
        # Terraform's uuidv5() names (asserted in its mocked plan) equal Bicep guid().
        extra="".join(
            f"param {param} = guid('{scope}', '{PRINCIPAL}', '{role}')\n"
            for param, (scope, role, _) in grants.items()
        ),
    )
    values = json.loads(json.loads(rendered)["parametersJson"])["parameters"]
    tftest = (SOURCE / "terraform/tests/ai-foundry.tftest.hcl").read_text(
        encoding="utf-8"
    )
    for param, (scope, role, resource) in grants.items():
        expected = uuid.uuid5(ARM_GUID_NAMESPACE, f"{scope}-{PRINCIPAL}-{role}")
        assert values[param]["value"] == str(expected)
        assert f'azapi_resource.{resource}.name == "{expected}"' in tftest


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": NETWORK_GROUP,
        "location": "swedencentral",
        "name": "sample-foundry-dev",
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
    assert "Success! 8 passed, 0 failed." in output, output
