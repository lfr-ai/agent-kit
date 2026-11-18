"""Offline Azure AI Search evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/ai-search"
)
TIMEOUT_SECONDS: Final[int] = 600
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
READER_ROLE: Final[str] = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
CONTRIBUTOR_ROLE: Final[str] = "8ebe5a00-799e-43f5-93ac-243d3dce84a7"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/search"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.search.windows.net"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
MESSAGES: Final[dict[str, str]] = {
    "prod_replicas": (
        "Production needs replicaCount 2 or more for the read SLA; use 3 for "
        "read-write."
    ),
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.search.windows.net zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.search.windows.net private DNS zone ARM ID."
    ),
    "prod_workspace": (
        "Staging and production require logAnalyticsWorkspaceId: an existing "
        "Log Analytics workspace for diagnostics."
    ),
    "public_stage": (
        "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
    ),
    "ranges_need_public": "allowedIpRanges needs allowPublicNetworkAccess.",
    "ranges_required": (
        "allowPublicNetworkAccess needs allowedIpRanges: Azure AI Search treats "
        "an empty list as all networks."
    ),
    "ip_range": (
        "allowedIpRanges must hold IPv4 addresses or CIDR ranges, "
        "such as 203.0.113.0/24."
    ),
    "workspace_empty": "logAnalyticsWorkspaceId must be omitted or non-empty.",
}
# Platform defaults that the sources must never restate; networkRuleSet is set
# only for the explicit public opt-in.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "partitionCount",
    "hostingMode",
    "authOptions",
    "encryptionWithCmk",
    "computeType",
    "dataExfiltrationProtections",
)
_PRIVATE = (SUBNET, ZONE)
_GUARDED_STAGES = ("staging", "prod")
_ReplicaCase = tuple[str, int | None, str | None]
_NetworkCase = tuple[str, tuple[str, str] | None, str | None]
_WorkspaceCase = tuple[str, str | None, str | None]
_PublicCase = tuple[str, tuple[str, str] | None, bool, list[str], str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
REPLICA_CASES: Final[tuple[_ReplicaCase, ...]] = (
    ("dev", None, None),
    ("dev", 1, None),
    ("test", 3, None),
    ("staging", 1, None),
    ("prod", None, None),
    ("prod", 2, None),
    ("prod", 3, None),
    ("prod", 1, "prod_replicas"),
)
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    (
        "dev",
        (SUBNET, ZONE.replace("privatelink.search", "PrivateLink.Search")),
        "network",
    ),
    ("dev", (SUBNET, ZONE.replace("search.windows", "blob.core.windows")), "network"),
    ("dev", (SUBNET, f"{ZONE}/extra"), "network"),
    ("dev", (SUBNET, ""), "network"),
    ("dev", (SUBNET.replace("/subnets/", "/subnet/"), ZONE), "network"),
    ("dev", (SUBNET.rsplit("/subnets/", 1)[0], ZONE), "network"),
)
# Azure AI Search treats an empty IP rule list as all networks, so the opt-in
# needs ranges.
PUBLIC_CASES: Final[tuple[_PublicCase, ...]] = (
    ("dev", None, False, [], None),
    ("test", None, True, ["198.51.100.7"], None),
    ("dev", None, True, ["203.0.113.0/24", "198.51.100.7"], None),
    ("test", None, True, [], "ranges_required"),
    ("prod", _PRIVATE, True, ["203.0.113.0/24"], "public_stage"),
    ("staging", _PRIVATE, True, ["203.0.113.0/24"], "public_stage"),
    ("dev", _PRIVATE, True, ["203.0.113.0/24"], "public_stage"),
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
            (f"requireReplicas('{stage}', {json.dumps(count)})", error)
            for stage, count, error in REPLICA_CASES
        ),
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
                {"stage": stage, "replica_count": count}
                | (private | diagnostics if stage in _GUARDED_STAGES else {}),
                error and "replica_count",
            )
            for stage, count, error in REPLICA_CASES
        ),
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
        # Bicep enforces these with native types and decorators at compile time.
        ({"indexing_principal_id": PRINCIPAL}, None),
        ({"indexing_principal_id": "app"}, "indexing_principal_id"),
        ({"principal_id": "app"}, "principal_id"),
        ({"replica_count": 0}, "replica_count"),
        ({"replica_count": 13}, "replica_count"),
        ({"name": "s"}, "name"),
        ({"name": "s" * 61}, "name"),
        ({"stage": "production"}, "stage"),
        ({"location": " "}, "location"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/ai-search")


def test_sources_are_self_contained_and_never_expose_keys(relocated: Path) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for forbidden in ("listAdminKeys", "listQueryKeys"):
        assert forbidden not in bicep
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    for role in (READER_ROLE, CONTRIBUTOR_ROLE):
        assert role in bicep
        assert role in terraform
    assert len(iac.shared_resource_types(bicep, terraform)) == 6
    # One named production replica floor per flavour, never a repeated literal.
    assert bicep.count("func productionMinReplicas() int => 2") == 1
    assert bicep.count("productionMinReplicas()") == 4
    assert terraform.count("production_min_replicas = 2") == 1
    assert terraform.count("local.production_min_replicas") == 2
    for literal in ("?? 2)", "? 2 :", ") < 2", "replica_count >= 2"):
        assert literal not in bicep + terraform, literal


def test_bicep_format_lint_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    iac.build_examples(folder, _run)


def test_bicep_search_service_and_roles(relocated: Path) -> None:
    template = json.loads(iac.build_bicep(relocated / "bicep", _run))
    resources = template["resources"]
    assert set(resources) == {
        "search",
        "indexReader",
        "indexContributor",
        "endpoint",
        "dnsZoneGroup",
        "diagnostics",
        "protection",
    }
    search = resources["search"]
    assert search["type"] == "Microsoft.Search/searchServices"
    assert search["sku"] == {
        "name": "[if(equals(parameters('stage'), 'prod'), 'standard', 'basic')]"
    }
    assert set(search) & {"zones", "identity"} == set()
    # Production-only properties are merged in, so dev/test keep platform defaults.
    # Production defaults to the same named floor that the guard enforces.
    assert template["variables"]["replicas"] == (
        "[__bicep.requireReplicas(parameters('stage'), coalesce("
        "parameters('replicaCount'), if(equals(parameters('stage'), 'prod'), "
        "__bicep.productionMinReplicas(), null())))]"
    )
    properties = search["properties"]
    for fragment in (
        "createObject('disableLocalAuth', true())",
        "createObject('replicaCount', variables('replicas'))",
        (
            "if(equals(parameters('stage'), 'prod'), "
            "createObject('semanticSearch', 'standard'), createObject())"
        ),
        "createObject('publicNetworkAccess', 'Disabled')",
        (
            "if(parameters('allowPublicNetworkAccess'), createObject("
            "'networkRuleSet', createObject('ipRules', map("
        ),
    ):
        assert fragment in properties, fragment
    reader = resources["indexReader"]
    contributor = resources["indexContributor"]
    assert "condition" not in reader
    assert contributor["condition"] == (
        "[not(equals(parameters('indexingPrincipalId'), null()))]"
    )
    for assignment, role in ((reader, READER_ROLE), (contributor, CONTRIBUTOR_ROLE)):
        assert assignment["type"] == "Microsoft.Authorization/roleAssignments"
        assert assignment["properties"]["principalType"] == "ServicePrincipal"
        assert role in json.dumps(template["variables"])
        assert "roleDefinitions" in assignment["properties"]["roleDefinitionId"]


def test_bicep_network_operations_and_contract(relocated: Path) -> None:
    template = json.loads(iac.build_bicep(relocated / "bicep", _run))
    resources = template["resources"]
    endpoint = resources["endpoint"]
    connection = endpoint["properties"]["privateLinkServiceConnections"][0]
    assert connection["properties"]["groupIds"] == ["searchService"]
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
        "logs": [{"category": "OperationLogs", "enabled": True}],
        "metrics": [{"category": "AllMetrics", "enabled": True}],
    }
    lock = resources["protection"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert set(template["outputs"]) == {"searchServiceId", "endpoint"}
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "principalId"):
        assert {"defaultValue", "nullable"}.isdisjoint(parameters[required])
    for optional in ("indexingPrincipalId", "replicaCount", "privateEndpoint"):
        assert parameters[optional]["nullable"] is True
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(template["variables"]) == {
        "replicas",
        "network",
        "ipRanges",
        "workspaceId",
    }


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"requireReplicas\(stage, 3\)", "requireReplicas(stage, 1)", "prod_replicas"),
        (
            r"requirePrivateEndpoint\(stage, \{.*?\}\)",
            "requirePrivateEndpoint(stage, null)",
            "prod_network",
        ),
        ("search.windows.net'", "blob.core.windows.net'", "network"),
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


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    imports = (
        "requireReplicas",
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
        "name": "sample-dev-search",
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
