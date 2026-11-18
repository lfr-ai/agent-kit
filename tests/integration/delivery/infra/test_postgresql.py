"""Offline PostgreSQL flexible server evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/postgresql"
)
TIMEOUT_SECONDS: Final[int] = 600
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
NETWORK_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network"
)
SUBNET: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/virtualNetworks/example"
    "/subnets/postgresql"
)
ZONE: Final[str] = (
    f"{NETWORK_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.postgres.database.azure.com"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
MESSAGES: Final[dict[str, str]] = {
    "prod_sku": (
        "Production needs a GeneralPurpose or MemoryOptimized sku; Burstable has "
        "no zone-redundant high availability."
    ),
    "prod_network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.postgres.database.azure.com zone."
    ),
    "network": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.postgres.database.azure.com private DNS zone ARM ID."
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
# Platform defaults that the sources must never restate.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "createMode",
    "backupRetentionDays",
    "availabilityZone",
    "maintenanceWindow",
    "charset",
    "collation",
    "replicationRole",
    "dataEncryption",
    "Premium_LRS",
)
# Password authentication stays off: no login, password or secret is ever declared.
PASSWORD_FIELDS: Final[tuple[str, ...]] = (
    r"\badministratorLogin",
    r"@secure\(",
    r"\bsensitive\s*=",
)
_PRIVATE = (SUBNET, ZONE)
_StageCase = tuple[str, str, str | None]
_WorkspaceCase = tuple[str, str | None, str | None]
_NetworkCase = tuple[str, tuple[str, str] | None, str | None]
_PublicCase = tuple[str, tuple[str, str] | None, bool, list[str], str | None]
_GUARDED_STAGES = ("staging", "prod")
# Shared positive/negative tables drive both the Bicep and Terraform guards.
SKU_CASES: Final[tuple[_StageCase, ...]] = (
    ("dev", "Burstable", None),
    ("test", "Burstable", None),
    ("staging", "Burstable", None),
    ("dev", "GeneralPurpose", None),
    ("prod", "GeneralPurpose", None),
    ("prod", "MemoryOptimized", None),
    ("prod", "Burstable", "prod_sku"),
)
NETWORK_CASES: Final[tuple[_NetworkCase, ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    (
        "dev",
        (SUBNET, ZONE.replace("privatelink.postgres", "PrivateLink.Postgres")),
        "network",
    ),
    ("prod", None, "prod_network"),
    ("staging", None, "prod_network"),
    ("dev", (SUBNET, ZONE.replace("postgres.database", "database.windows")), "network"),
    ("dev", (SUBNET, f"{ZONE}/extra"), "network"),
    ("dev", (SUBNET, ""), "network"),
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
            (f"requireSku('{stage}', {{ name: 'Standard_X', tier: '{tier}' }})", error)
            for stage, tier, error in SKU_CASES
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
    administrator = {"object_id": PRINCIPAL, "name": "db-admins", "type": "Group"}
    return [
        *(
            (
                {"stage": stage, "sku": {"name": "Standard_X", "tier": tier}}
                | (private | diagnostics if stage in _GUARDED_STAGES else {}),
                error and "sku",
            )
            for stage, tier, error in SKU_CASES
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
        ({"stage": "prod"} | private | diagnostics | {"sku": None}, None),
        ({"sku": {"name": "Standard_X", "tier": "Basic"}}, "sku"),
        ({"administrator": administrator | {"object_id": "app"}}, "administrator"),
        ({"administrator": administrator | {"name": ""}}, "administrator"),
        ({"administrator": administrator | {"type": "Unknown"}}, "administrator"),
        ({"storage_size_gb": 16}, "storage_size_gb"),
        ({"storage_size_gb": 32.5}, "storage_size_gb"),
        ({"storage_size_gb": 64}, None),
        ({"database_name": ""}, "database_name"),
        ({"database_name": "d" * 64}, "database_name"),
        ({"name": "pg"}, "name"),
        ({"name": "p" * 64}, "name"),
        ({"stage": "production"}, "stage"),
        ({"location": " "}, "location"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/postgresql")


def test_sources_are_self_contained_and_never_use_passwords(relocated: Path) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for pattern in PASSWORD_FIELDS:
        assert not re.search(pattern, bicep + terraform), pattern
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    assert len(iac.shared_resource_types(bicep, terraform)) == 9


def test_bicep_format_lint_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    iac.build_examples(folder, _run)


def test_bicep_server_admin_and_database(relocated: Path) -> None:
    resources = json.loads(iac.build_bicep(relocated / "bicep", _run))["resources"]
    assert set(resources) == {
        "server",
        "entraAdmin",
        "database",
        "allowedExtensions",
        "firewallRules",
        "endpoint",
        "dnsZoneGroup",
        "diagnostics",
        "protection",
    }
    server = resources["server"]
    assert server["type"] == "Microsoft.DBforPostgreSQL/flexibleServers"
    assert server["sku"] == "[variables('compute')]"
    assert set(server) & {"zones", "identity"} == set()
    # Production-only properties are merged in, so dev/test keep platform defaults.
    properties = server["properties"]
    for fragment in (
        "'version', '18'",
        "'activeDirectoryAuth', 'Enabled', 'passwordAuth', 'Disabled'",
        "'storageSizeGB', parameters('storageSizeGB'), 'autoGrow', 'Enabled'",
        (
            "'network', createObject('publicNetworkAccess', "
            "if(parameters('allowPublicNetworkAccess'), 'Enabled', 'Disabled'))"
        ),
        (
            "if(equals(parameters('stage'), 'prod'), createObject('highAvailability', "
            "createObject('mode', 'ZoneRedundant'), 'backup', "
            "createObject('geoRedundantBackup', 'Enabled')), createObject())"
        ),
    ):
        assert fragment in properties, fragment
    admin = resources["entraAdmin"]
    assert admin["name"].endswith("parameters('administrator').objectId)]")
    assert set(admin["properties"]) == {"principalName", "principalType", "tenantId"}
    # Server operations are serialized: administrator, then database, then endpoint.
    assert "entraAdmin" in resources["database"]["dependsOn"]
    assert "properties" not in resources["database"]
    assert "database" in resources["endpoint"]["dependsOn"]
    extensions = resources["allowedExtensions"]
    assert extensions["condition"] == "[not(empty(parameters('extensions')))]"
    assert extensions["name"].endswith("'azure.extensions')]")
    assert extensions["properties"] == {
        "value": "[join(parameters('extensions'), ',')]",
        "source": "user-override",
    }
    assert "database" in extensions["dependsOn"]
    assert "allowedExtensions" in resources["endpoint"]["dependsOn"]
    # Firewall rules exist only for the validated dev/test allow list, one at a time.
    rules = resources["firewallRules"]
    assert rules["copy"]["count"] == "[length(variables('ipRanges'))]"
    assert rules["copy"]["mode"] == "serial"
    assert rules["copy"]["batchSize"] == 1
    assert "allowedExtensions" in rules["dependsOn"]


def test_bicep_network_operations_and_contract(relocated: Path) -> None:
    template = json.loads(iac.build_bicep(relocated / "bicep", _run))
    resources = template["resources"]
    endpoint = resources["endpoint"]
    connection = endpoint["properties"]["privateLinkServiceConnections"][0]
    assert connection["properties"]["groupIds"] == ["postgresqlServer"]
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
        "logs": [{"category": "PostgreSQLLogs", "enabled": True}],
        "metrics": [{"category": "AllMetrics", "enabled": True}],
    }
    lock = resources["protection"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert set(template["outputs"]) == {"serverId", "fqdn", "databaseName"}
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "administrator", "databaseName"):
        assert {"defaultValue", "nullable"}.isdisjoint(parameters[required])
    for optional in ("sku", "privateEndpoint"):
        assert parameters[optional]["nullable"] is True
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    assert parameters["extensions"]["defaultValue"] == []
    # The smallest Premium SSD size is a named, overridable default, not a literal.
    assert parameters["storageSizeGB"]["type"] == "int"
    assert parameters["storageSizeGB"]["defaultValue"] == 32
    assert parameters["storageSizeGB"]["minValue"] == 32
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(template["variables"]) == {
        "compute",
        "network",
        "ipRanges",
        "workspaceId",
    }


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        ("'GeneralPurpose'", "'Burstable'", "prod_sku"),
        (
            r"requirePrivateEndpoint\(stage, \{.*?\}\)",
            "requirePrivateEndpoint(stage, null)",
            "prod_network",
        ),
        ("postgres.database.azure.com'", "database.windows.net'", "network"),
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
        "name": "sample-dev-pg",
        "stage": "dev",
        "administrator": {"object_id": PRINCIPAL, "name": "db-admins", "type": "Group"},
        "database_name": "app",
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run)
    iac.mock_plans(folder, _run)
