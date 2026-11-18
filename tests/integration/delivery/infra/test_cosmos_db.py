"""Offline Cosmos DB for NoSQL evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/cosmos-db"
)
TIMEOUT_SECONDS: Final[int] = 900
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
DATA_CONTRIBUTOR: Final[str] = "00000000-0000-0000-0000-000000000002"
# ARM guid() is UUIDv5 over its '-'-joined arguments in this namespace.
ARM_GUID_NAMESPACE: Final[uuid.UUID] = uuid.UUID("11fb06fb-712d-4ddd-98c7-e71bbd588830")
ACCOUNT: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
    "/providers/Microsoft.DocumentDB/databaseAccounts/sample-prod-cosmos"
)
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example"
    "/subnets/cosmos-db"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.documents.azure.com"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
MESSAGES: Final[dict[str, str]] = {
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.documents.azure.com zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.documents.azure.com private DNS zone ARM ID."
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
        "allowPublicNetworkAccess needs allowedIpRanges: Cosmos DB treats an "
        "empty list as all networks."
    ),
    "ip_range": (
        "allowedIpRanges must hold IPv4 addresses or CIDR ranges, "
        "such as 203.0.113.0/24."
    ),
    "workspace_empty": "logAnalyticsWorkspaceId must be omitted or non-empty.",
}
# Platform defaults that the sources must never restate.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "consistencyPolicy",
    "enableAutomaticFailover",
    "enableMultipleWriteLocations",
    "enableFreeTier",
    "enableAnalyticalStorage",
    "isVirtualNetworkFilterEnabled",
    "kind:",
    "kind =",
)
# Local authentication stays off: no key, token or connection string is ever read.
SECRET_FIELDS: Final[tuple[str, ...]] = (
    r"listKeys",
    r"listReadOnlyKeys",
    r"listConnectionStrings",
    r"(?i)masterKey",
    r"@secure\(",
    r"\bsensitive\s*=",
)
# NoSQL only: no Gremlin, MongoDB, Cassandra or Table resources or capabilities.
OTHER_APIS: Final[tuple[str, ...]] = (
    "EnableGremlin",
    "gremlinDatabases",
    "mongodbDatabases",
    "cassandraKeyspaces",
    "EnableTable",
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
    (
        "dev",
        (SUBNET, ZONE.replace("privatelink.documents", "PrivateLink.Documents")),
        "network",
    ),
    (
        "dev",
        (SUBNET, ZONE.replace("documents.azure.com", "mongo.cosmos.azure.com")),
        "network",
    ),
    ("dev", (SUBNET, f"{ZONE}/extra"), "network"),
    ("dev", (SUBNET, ""), "network"),
    ("dev", (SUBNET.replace("/subnets/", "/subnet/"), ZONE), "network"),
    ("dev", (SUBNET.rsplit("/subnets/", 1)[0], ZONE), "network"),
)
# Cosmos DB treats an empty IP rule list as all networks, so the opt-in needs ranges.
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
    container = {"name": "items", "partition_key_path": "/tenantId"}
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
        # Bicep enforces lengths with native types and decorators at compile time.
        ({"database": {"name": "app"}}, None),
        ({"database": {"name": "app", "containers": [container]}}, None),
        ({"database": {"name": ""}}, "database"),
        ({"database": {"name": "d" * 256}}, "database"),
        (
            {"database": {"name": "app", "containers": [container | {"name": ""}]}},
            "database",
        ),
        (
            {
                "database": {
                    "name": "app",
                    "containers": [container | {"partition_key_path": "tenantId"}],
                }
            },
            "database",
        ),
        (
            {"database": {"name": "app", "containers": [container, container]}},
            "database",
        ),
        ({"principal_id": PRINCIPAL}, None),
        ({"principal_id": None}, None),
        ({"principal_id": "app"}, "principal_id"),
        ({"autoscale_max_throughput": 1000}, None),
        ({"autoscale_max_throughput": 400}, "autoscale_max_throughput"),
        ({"name": "abc"}, None),
        ({"name": "c" * 44}, None),
        ({"name": "db"}, "name"),
        ({"name": "c" * 45}, "name"),
        ({"name": "Upper-Case"}, "name"),
        ({"name": "-leading"}, "name"),
        ({"stage": "production"}, "stage"),
        ({"location": " "}, "location"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/cosmos-db")


def test_sources_are_self_contained_nosql_and_keyless(relocated: Path) -> None:
    for required in ("README.md", "REFERENCE.md", "terraform/variables.tf"):
        assert (relocated / required).is_file(), required
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    assert 'provider "azapi"' not in terraform
    assert 'backend "' not in terraform
    assert "disableLocalAuth: true" in bicep
    assert "disableLocalAuth  = true" in terraform
    for pattern in SECRET_FIELDS:
        assert not re.search(pattern, bicep + terraform), pattern
    for name in RESTATED_DEFAULTS + OTHER_APIS:
        assert name not in bicep + terraform, name
    assert len(iac.shared_resource_types(bicep, terraform)) == 8


def test_bicep_format_lint_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    iac.build_examples(folder, _run)


def test_bicep_account_database_and_role(relocated: Path) -> None:
    resources = json.loads(iac.build_bicep(relocated / "bicep", _run))["resources"]
    assert set(resources) == {
        "account",
        "sqlDatabase",
        "sqlContainers",
        "dataContributor",
        "endpoint",
        "dnsZoneGroup",
        "diagnostics",
        "protection",
    }
    account = resources["account"]
    assert account["type"] == "Microsoft.DocumentDB/databaseAccounts"
    assert set(account) & {"kind", "identity", "sku"} == set()
    # Stage-specific properties are merged in, so each stage keeps other defaults.
    properties = account["properties"]
    for fragment in (
        "'databaseAccountOfferType', 'Standard'",
        "createObject('locationName', parameters('location'), 'failoverPriority', 0)",
        (
            "if(equals(parameters('stage'), 'prod'), "
            "createObject('isZoneRedundant', true()), createObject())"
        ),
        "'disableLocalAuth', true()",
        "'minimalTlsVersion', 'Tls12'",
        "createObject('publicNetworkAccess', 'Disabled')",
        "if(parameters('allowPublicNetworkAccess'), createObject('ipRules', map(",
        (
            "createObject('backupPolicy', createObject('type', 'Continuous', "
            "'continuousModeProperties', createObject('tier', 'Continuous30Days')))"
        ),
        "createObject('capabilities', createArray(createObject('name', 'EnableServerless')))",
    ):
        assert fragment in properties, fragment
    database = resources["sqlDatabase"]
    assert database["condition"] == "[not(equals(parameters('database'), null()))]"
    assert (
        "if(equals(parameters('stage'), 'prod'), createObject('options', "
        "createObject('autoscaleSettings', createObject('maxThroughput', "
        "parameters('autoscaleMaxThroughput')))), createObject())"
    ) in database["properties"]
    containers = resources["sqlContainers"]
    assert containers["copy"]["count"] == "[length(variables('containers'))]"
    assert containers["properties"]["resource"]["partitionKey"] == {
        "paths": ["[variables('containers')[copyIndex()].partitionKeyPath]"],
        "version": 2,
    }
    role = resources["dataContributor"]
    assert role["condition"] == "[not(equals(parameters('principalId'), null()))]"
    assert role["properties"]["roleDefinitionId"] == (
        "[format('{0}/sqlRoleDefinitions/{1}', resourceId('Microsoft.DocumentDB/"
        "databaseAccounts', parameters('name')), variables('dataContributorRoleId'))]"
    )
    assert set(role["properties"]) == {"roleDefinitionId", "principalId", "scope"}


def test_bicep_network_operations_and_contract(relocated: Path) -> None:
    template = json.loads(iac.build_bicep(relocated / "bicep", _run))
    resources = template["resources"]
    endpoint = resources["endpoint"]
    connection = endpoint["properties"]["privateLinkServiceConnections"][0]
    assert connection["properties"]["groupIds"] == ["Sql"]
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
        "logAnalyticsDestinationType": "Dedicated",
        "logs": [
            {"category": "DataPlaneRequests", "enabled": True},
            {"category": "ControlPlaneRequests", "enabled": True},
        ],
        "metrics": [{"category": "Requests", "enabled": True}],
    }
    lock = resources["protection"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert set(template["outputs"]) == {
        "accountId",
        "documentEndpoint",
        "databaseName",
        "containerNames",
    }
    # Without a database the name output is null, not an empty string.
    database_name = template["outputs"]["databaseName"]
    assert database_name["nullable"] is True
    assert database_name["value"] == "[tryGet(parameters('database'), 'name')]"
    parameters = template["parameters"]
    for required in ("location", "name", "stage"):
        assert {"defaultValue", "nullable"}.isdisjoint(parameters[required])
    assert (parameters["name"]["minLength"], parameters["name"]["maxLength"]) == (3, 44)
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    for optional in ("database", "principalId", "privateEndpoint"):
        assert parameters[optional]["nullable"] is True
    assert parameters["autoscaleMaxThroughput"]["defaultValue"] == 1000
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(template["variables"]) == {"network", "ipRanges", "workspaceId"}


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (
            r"requirePrivateEndpoint\(stage, \{.*?\}\)",
            "requirePrivateEndpoint(stage, null)",
            "prod_network",
        ),
        ("documents.azure.com'", "mongo.cosmos.azure.com'", "network"),
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
    expected_name = uuid.uuid5(
        ARM_GUID_NAMESPACE, f"{ACCOUNT}-{PRINCIPAL}-{DATA_CONTRIBUTOR}"
    )
    rendered = iac.assert_bicep_guards(
        relocated / "bicep",
        _run,
        ("requirePrivateEndpoint", "requirePublicAccess", "requireWorkspace"),
        _bicep_cases(),
        MESSAGES,
        # Terraform's uuidv5() name (asserted in its mocked plan) equals Bicep guid().
        extra=f"param roleName = guid('{ACCOUNT}', '{PRINCIPAL}', '{DATA_CONTRIBUTOR}')\n",
    )
    values = json.loads(json.loads(rendered)["parametersJson"])["parameters"]
    assert values["roleName"]["value"] == str(expected_name)
    tftest = (SOURCE / "terraform/tests/cosmos-db.tftest.hcl").read_text(
        encoding="utf-8"
    )
    assert f'"{expected_name}"' in tftest


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": NETWORK_GROUP,
        "location": "westeurope",
        "name": "sample-dev-cosmos",
        "stage": "dev",
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run, "-get=false")
    output = iac.mock_plans(folder, _run)
    assert "Success! 8 passed, 0 failed." in output, output
