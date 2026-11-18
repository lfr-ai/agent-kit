"""Offline network composition evidence; no account context, downloads or deployment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import TYPE_CHECKING, Final

import pytest
from tests.integration.delivery.infra import iac

if TYPE_CHECKING:
    import subprocess

pytestmark = pytest.mark.integration
SOURCE: Final[Path] = (
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/network"
)
TIMEOUT_SECONDS: Final[int] = 900
NAME_LENGTH: Final[tuple[int, int]] = (2, 64)
RESOURCE_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
)
MESSAGES: Final[dict[str, str]] = {
    "prefix": (
        "addressPrefix must be one IPv4 network address in CIDR notation from "
        "/16 to /24, for example 10.20.0.0/22."
    ),
    "duplicate": "privateDnsZones must not repeat a service key.",
    "egress": (
        "egress.routeTableId must be a route table ARM ID when mode is routeTable, "
        "and omitted otherwise."
    ),
}
ROUTE_TABLE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/hub"
    "/providers/Microsoft.Network/routeTables/to-firewall"
)
# Keys and zones from the Private Link DNS reference; containerApps embeds the region.
ZONES: Final[dict[str, str]] = {
    "keyVault": "privatelink.vaultcore.azure.net",
    "redis": "privatelink.redis.azure.net",
    "postgresql": "privatelink.postgres.database.azure.com",
    "blob": "privatelink.blob.core.windows.net",
    "queue": "privatelink.queue.core.windows.net",
    "table": "privatelink.table.core.windows.net",
    "file": "privatelink.file.core.windows.net",
    "dfs": "privatelink.dfs.core.windows.net",
    "containerRegistry": "privatelink.azurecr.io",
    "search": "privatelink.search.windows.net",
    "cognitiveServices": "privatelink.cognitiveservices.azure.com",
    "openai": "privatelink.openai.azure.com",
    "aiServices": "privatelink.services.ai.azure.com",
    "cosmosDb": "privatelink.documents.azure.com",
    "containerApps": "privatelink.westeurope.azurecontainerapps.io",
    "monitor": "privatelink.monitor.azure.com",
    "oms": "privatelink.oms.opinsights.azure.com",
    "ods": "privatelink.ods.opinsights.azure.com",
    "agentsvc": "privatelink.agentsvc.azure-automation.net",
}
# Apps get (prefix + 1, index 0); private endpoints (prefix + 2, index 2).
SUBNETS: Final[dict[str, tuple[str, str]]] = {
    "10.20.0.0/16": ("10.20.0.0/17", "10.20.128.0/18"),
    "10.20.0.0/22": ("10.20.0.0/23", "10.20.2.0/24"),
    "10.20.0.0/24": ("10.20.0.0/25", "10.20.0.128/26"),
}
ACCEPTED_PREFIXES: Final[tuple[str, ...]] = (*SUBNETS, "172.16.0.0/20")
REJECTED_PREFIXES: Final[tuple[str, ...]] = (
    "10.0.0.0/15",
    "10.20.0.0/25",
    "10.0.0.0/8",
    "10.0.0.0/09",
    "10.20.0.5/22",
    "fd00::/16",
    "010.0.0.0/16",
    "10.0.0.0/016",
    "300.0.0.0/16",
    "10.0.0/16",
    "10.0.0.0",
    "",
    " 10.0.0.0/16",
    "10.0.0.0/16/1",
)


def _run(name: str, folder: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return iac.run_isolated(name, folder, *arguments, timeout=TIMEOUT_SECONDS)


def _ok(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return result.stdout


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Relocate the byte-identical source closure without borrowing sibling modules."""
    target = tmp_path / "consumer/network"
    shutil.copytree(SOURCE, target)

    def digests(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    assert digests(target) == digests(SOURCE)
    return target


def test_prefix_length_bounds_are_named_in_both_flavours(relocated: Path) -> None:
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    assert "func minPrefixLength() int => 16\n" in bicep
    assert "func maxPrefixLength() int => 24\n" in bicep
    guard = "isNumber(last(split(prefix, '/')), minPrefixLength(), maxPrefixLength())"
    assert guard in bicep
    assert re.search(r"^\s+min_prefix_length = 16$", variables, re.MULTILINE)
    assert re.search(r"^\s+max_prefix_length = 24$", variables, re.MULTILINE)
    assert ">= local.min_prefix_length" in variables
    assert "<= local.max_prefix_length" in variables
    # The bounds live only in the names, not in a length alternation or call site.
    assert "1[6-9]|2[0-4]" not in variables
    assert ", 16, 24)" not in bicep


def test_sources_are_complete_pinned_and_equivalent(relocated: Path) -> None:
    for required in ("README.md", "REFERENCE.md", "terraform/variables.tf"):
        assert (relocated / required).is_file(), required
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").glob("*.tf"))
    )
    readme = (relocated / "README.md").read_text(encoding="utf-8")
    assert not list(relocated.rglob("*.tfstate*"))
    assert "module " not in bicep
    assert 'module "' not in terraform
    assert 'provider "azapi"' not in terraform
    assert 'backend "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    for forbidden in ("azapi_resource_action", 'response_export_values = ["*"]'):
        assert forbidden not in terraform
    types = re.compile(r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)""")
    assert set(types.findall(bicep)) == set(types.findall(terraform))
    assert len(set(types.findall(bicep))) == 7
    assert len(re.findall(r"defaultOutboundAccess: false", bicep)) == 2
    assert len(re.findall(r"defaultOutboundAccess\s+= false", terraform)) == 2
    for key, zone in ZONES.items():
        literal = zone.replace(".westeurope.", ".<location>.")
        assert literal in readme, key
        if key != "containerApps":
            assert f"{key}: '{zone}'" in bicep
            assert re.search(rf'{key}\s+= "{re.escape(zone)}"', terraform), key
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    for message in MESSAGES.values():
        assert message in bicep
        assert message in variables


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    for source in sorted([*folder.rglob("*.bicep"), *folder.rglob("*.bicepparam")]):
        assert _ok(_run("bicep", folder, "format", str(source), "--stdout")) == (
            source.read_text(encoding="utf-8")
        )
    lint = _run("bicep", folder, "lint", "main.bicep", "--no-restore")
    assert _ok(lint) == ""
    assert lint.stderr == ""
    template = json.loads(
        _ok(_run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))
    )
    resources = template["resources"]
    assert len(resources) == 11
    security_group = "[resourceId('Microsoft.Network/networkSecurityGroups', format('{0}-{1}-nsg', parameters('name')))]"
    subnets = resources["network"]["properties"]["subnets"]
    # The apps subnet merges the selected egress association into its base settings.
    assert subnets[0]["properties"] == (
        "[union(createObject("
        "'addressPrefix', cidrSubnet(variables('prefix'), add(variables('prefixLength'), 1), 0), "
        "'networkSecurityGroup', createObject('id', "
        "resourceId('Microsoft.Network/networkSecurityGroups', "
        "format('{0}-apps-nsg', parameters('name')))), "
        "'delegations', createArray(createObject('name', 'Microsoft.App.environments', "
        "'properties', createObject('serviceName', 'Microsoft.App/environments'))), "
        "'defaultOutboundAccess', false()), variables('appsEgress'))]"
    )
    assert subnets[1]["properties"] == {
        "addressPrefix": "[cidrSubnet(variables('prefix'), add(variables('prefixLength'), 2), 2)]",
        "networkSecurityGroup": {"id": security_group.replace("{1}", "pe")},
        "privateEndpointNetworkPolicies": "Enabled",
        "defaultOutboundAccess": False,
    }
    assert (
        template["variables"]["prefixLength"] == "[parseCidr(variables('prefix')).cidr]"
    )
    for group in ("appsSecurityGroup", "endpointsSecurityGroup"):
        assert "properties" not in resources[group]
    zones = {"name": "zones", "count": "[length(variables('zoneKeys'))]"}
    assert resources["zones"]["copy"] == zones
    assert resources["zones"]["location"] == "global"
    links = resources["zoneLinks"]
    assert links["location"] == "global"
    assert links["properties"] == {
        "virtualNetwork": {
            "id": "[resourceId('Microsoft.Network/virtualNetworks', parameters('name'))]"
        },
        "registrationEnabled": False,
    }
    production = "[equals(parameters('stage'), 'prod')]"
    nat_production = (
        "[and(equals(parameters('stage'), 'prod'), variables('natGatewayEnabled'))]"
    )
    for name, scope, condition in (
        (
            "protection",
            "Microsoft.Network/virtualNetworks/{0}', parameters('name'))]",
            production,
        ),
        ("zoneProtection", "Microsoft.Network/privateDnsZones/{0}'", production),
        ("natProtection", "Microsoft.Network/natGateways/{0}'", nat_production),
        (
            "natIpProtection",
            "Microsoft.Network/publicIPAddresses/{0}'",
            nat_production,
        ),
    ):
        lock = resources[name]
        assert lock["condition"] == condition
        assert scope in lock["scope"]
        assert lock["properties"] == {"level": "CanNotDelete"}
    assert resources["zoneProtection"]["copy"]["count"] == zones["count"]
    zone_names = template["variables"]["zoneNames"]
    assert {key: zone_names[key] for key in ZONES if key != "containerApps"} == {
        key: zone for key, zone in ZONES.items() if key != "containerApps"
    }
    assert zone_names["containerApps"] == (
        "[format('privatelink.{0}.azurecontainerapps.io', "
        "toLower(replace(parameters('location'), ' ', '')))]"
    )
    parameters = template["parameters"]
    assert (
        parameters["name"]["minLength"],
        parameters["name"]["maxLength"],
    ) == NAME_LENGTH
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["privateDnsZones"]["defaultValue"] == []
    assert set(template["definitions"]["PrivateDnsZone"]["allowedValues"]) == set(ZONES)
    guarded = {
        name
        for name, value in template["variables"].items()
        if "__bicep.require" in str(value)
    }
    assert guarded == {"prefix", "zoneKeys", "egressSettings"}
    assert set(template["outputs"]) == {
        "virtualNetworkResourceId",
        "appsSubnetResourceId",
        "privateEndpointSubnetResourceId",
        "privateDnsZoneResourceIds",
        "egressMode",
        "natGatewayPublicIpResourceId",
    }
    for example in ("dev", "prod"):
        _ok(
            _run(
                "bicep",
                folder,
                "build-params",
                f"tests/{example}.bicepparam",
                "--no-restore",
                "--stdout",
            )
        )


def test_bicep_egress_and_nat_gateway(relocated: Path) -> None:
    folder = relocated / "bicep"
    template = json.loads(
        _ok(_run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))
    )
    resources = template["resources"]
    parameters = template["parameters"]
    assert template["variables"]["egressSettings"] == (
        "[__bicep.requireEgress(coalesce(parameters('egress'), createObject('mode', "
        "if(contains(createArray('staging', 'prod'), parameters('stage')), "
        "'natGateway', 'platform'))))]"
    )
    assert template["variables"]["appsEgress"] == (
        "[if(equals(variables('egressSettings').mode, 'natGateway'), "
        "createObject('natGateway', createObject('id', "
        "resourceId('Microsoft.Network/natGateways', format('{0}-nat', parameters('name'))))), "
        "if(equals(variables('egressSettings').mode, 'routeTable'), "
        "createObject('routeTable', createObject('id', "
        "variables('egressSettings').routeTableId)), createObject()))]"
    )
    assert "natGateway" in resources["network"]["dependsOn"]
    nat = "[variables('natGatewayEnabled')]"
    public_ip = resources["natPublicIp"]
    assert public_ip["condition"] == nat
    assert public_ip["sku"] == {"name": "Standard", "tier": "Regional"}
    assert public_ip["properties"] == {
        "publicIPAddressVersion": "IPv4",
        "publicIPAllocationMethod": "Static",
    }
    assert "zones" not in public_ip
    assert resources["natGateway"]["condition"] == nat
    assert resources["natGateway"]["sku"] == {"name": "Standard"}
    assert resources["natGateway"]["properties"] == {
        "publicIpAddresses": [
            {
                "id": "[resourceId('Microsoft.Network/publicIPAddresses', "
                "format('{0}-nat-pip', parameters('name')))]"
            }
        ]
    }
    assert parameters["egress"]["nullable"] is True
    assert "defaultValue" not in parameters["egress"]
    egress_type = template["definitions"]["Egress"]["properties"]
    assert set(egress_type["mode"]["allowedValues"]) == {
        "platform",
        "natGateway",
        "routeTable",
    }
    assert template["outputs"]["natGatewayPublicIpResourceId"]["value"] == (
        "[if(variables('natGatewayEnabled'), "
        "resourceId('Microsoft.Network/publicIPAddresses', "
        "format('{0}-nat-pip', parameters('name'))), null())]"
    )
    # Null, never an empty string, when no NAT gateway exists.
    assert template["outputs"]["natGatewayPublicIpResourceId"]["nullable"] is True


def test_bicep_subnet_math_matches_terraform(relocated: Path) -> None:
    folder = relocated / "bicep"
    # The compiled expressions asserted above, evaluated offline for the shared cases.
    lines = ["using none\n"]
    for index, prefix in enumerate(SUBNETS):
        for subnet, (bits, offset) in enumerate(((1, 0), (2, 2))):
            lines.append(
                f"param case{index}x{subnet} = cidrSubnet('{prefix}', "
                f"parseCidr('{prefix}').cidr + {bits}, {offset})\n"
            )
    (folder / "subnets.bicepparam").write_text("".join(lines), encoding="utf-8")
    result = json.loads(
        _ok(
            _run(
                "bicep",
                folder,
                "build-params",
                "subnets.bicepparam",
                "--no-restore",
                "--stdout",
            )
        )
    )
    values = json.loads(result["parametersJson"])["parameters"]
    tests = (relocated / "terraform/tests/network.tftest.hcl").read_text(
        encoding="utf-8"
    )
    for index, (prefix, expected) in enumerate(SUBNETS.items()):
        actual = tuple(values[f"case{index}x{subnet}"]["value"] for subnet in (0, 1))
        assert actual == expected, prefix
        assert f'"{prefix}"' in tests
        assert all(f'"{subnet}"' in tests for subnet in expected), prefix


def _egress_guard_cases() -> list[tuple[str, str | None]]:
    cases: list[tuple[str, str | None]] = []
    route_tables: list[tuple[str | None, str | None]] = [
        (None, "egress"),
        ("", "egress"),
        (ROUTE_TABLE, None),
        (ROUTE_TABLE.lower(), None),
        (ROUTE_TABLE.replace("routeTables", "virtualNetworks"), "egress"),
        (f"{ROUTE_TABLE}/routes/default", "egress"),
        (ROUTE_TABLE[1:], "egress"),
    ]
    for route_table, error in route_tables:
        field = "" if route_table is None else f", routeTableId: '{route_table}'"
        cases.append((f"requireEgress({{ mode: 'routeTable'{field} }})", error))
    for mode in ("platform", "natGateway"):
        cases.append((f"requireEgress({{ mode: '{mode}' }})", None))
        cases.append(
            (
                f"requireEgress({{ mode: '{mode}', routeTableId: '{ROUTE_TABLE}' }})",
                "egress",
            )
        )
    return cases


def test_bicep_shared_input_guards(relocated: Path) -> None:
    folder = relocated / "bicep"
    cases: list[tuple[str, str | None]] = [
        (f"requireAddressPrefix('{prefix}')", None) for prefix in ACCEPTED_PREFIXES
    ]
    cases.extend(
        (f"requireAddressPrefix('{prefix}')", "prefix") for prefix in REJECTED_PREFIXES
    )
    keys = ", ".join(f"'{key}'" for key in ZONES)
    cases.extend(
        (
            ("requirePrivateDnsZones([])", None),
            (f"requirePrivateDnsZones([{keys}])", None),
            ("requirePrivateDnsZones(['keyVault', 'blob', 'keyVault'])", "duplicate"),
        )
    )
    cases.extend(_egress_guard_cases())
    header = (
        "using none\n"
        "import { requireAddressPrefix, requireEgress, requirePrivateDnsZones } "
        "from './main.bicep'\n"
    )
    fixture = folder / "guards.bicepparam"
    for accepted in (True, False):
        selected = [
            (i, expr, error)
            for i, (expr, error) in enumerate(cases)
            if (error is None) == accepted
        ]
        fixture.write_text(
            header + "".join(f"param case{i} = {expr}\n" for i, expr, _ in selected),
            encoding="utf-8",
        )
        result = _run(
            "bicep", folder, "build-params", fixture.name, "--no-restore", "--stdout"
        )
        if accepted:
            _ok(result)
        else:
            assert result.returncode != 0
            assert result.stderr.count("Error BCP") == len(selected), result.stderr
            for index, _, error in selected:
                assert error is not None
                assert (
                    f'Failed to evaluate parameter "case{index}": {MESSAGES[error]}'
                    in result.stderr
                )
    # Unknown keys and modes fail the union types at compile time, before evaluation.
    for unknown, code in (
        ("requirePrivateDnsZones(['sql'])", "BCP033"),
        ("requireEgress({ mode: 'firewall' })", "BCP036"),
    ):
        fixture.write_text(header + f"param case0 = {unknown}\n", encoding="utf-8")
        result = _run(
            "bicep", folder, "build-params", fixture.name, "--no-restore", "--stdout"
        )
        assert result.returncode != 0, unknown
        assert f"Error {code}" in result.stderr, unknown


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"'10\.30\.0\.0/24'", "'10.30.0.0/25'", MESSAGES["prefix"]),
        (r"\['keyVault', ", "['keyVault', 'keyVault', ", MESSAGES["duplicate"]),
        (r"'containerApps'", "'sql'", "Error BCP033"),
        (
            r"mode: 'natGateway' \}",
            f"mode: 'natGateway', routeTableId: '{ROUTE_TABLE}' }}",
            MESSAGES["egress"],
        ),
        (r"mode: 'natGateway' \}", "mode: 'routeTable' }", MESSAGES["egress"]),
    ],
)
def test_bicep_production_example_rejects_unsafe_inputs(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    folder = relocated / "bicep/tests"
    example = (folder / "prod.bicepparam").read_text(encoding="utf-8")
    unsafe, count = re.subn(pattern, replacement, example, count=1)
    assert count == 1
    (folder / "unsafe.bicepparam").write_text(unsafe, encoding="utf-8")
    result = _run(
        "bicep", folder, "build-params", "unsafe.bicepparam", "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert error in result.stderr


def _terraform_cases() -> list[tuple[dict[str, object], str | None]]:
    cases: list[tuple[dict[str, object], str | None]] = [
        ({"address_prefix": prefix}, None) for prefix in ACCEPTED_PREFIXES
    ]
    cases.extend(
        ({"address_prefix": prefix}, "address_prefix") for prefix in REJECTED_PREFIXES
    )
    cases.extend(({"name": "a" * length}, None) for length in NAME_LENGTH)
    cases += [
        ({"name": "a.b_c-d_"}, None),
        ({"private_dns_zones": []}, None),
        ({"private_dns_zones": list(ZONES)}, None),
        ({"stage": "staging"}, None),
        ({"egress": None}, None),
        ({"egress": {"mode": "platform"}}, None),
        ({"egress": {"mode": "natGateway"}}, None),
        ({"egress": {"mode": "routeTable", "route_table_id": ROUTE_TABLE}}, None),
        (
            {"egress": {"mode": "routeTable", "route_table_id": ROUTE_TABLE.lower()}},
            None,
        ),
    ]
    cases.extend(
        ({key: value}, key)
        for key, value in (
            ("name", "a"),
            ("name", "a" * (NAME_LENGTH[1] + 1)),
            ("name", "-vnet"),
            ("name", "vnet."),
            ("name", "has space"),
            ("private_dns_zones", ["sql"]),
            ("egress", {"mode": "firewall"}),
            ("egress", {"mode": "routeTable"}),
            ("egress", {"mode": "routeTable", "route_table_id": ""}),
            ("egress", {"mode": "routeTable", "route_table_id": f"{ROUTE_TABLE}/x"}),
            ("egress", {"mode": "natGateway", "route_table_id": ROUTE_TABLE}),
            ("egress", {"mode": "platform", "route_table_id": ROUTE_TABLE}),
            ("private_dns_zones", ["keyVault", "blob", "keyVault"]),
            ("stage", "production"),
            ("location", " "),
            ("resource_group_id", "example"),
        )
    )
    return cases


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    shutil.copyfile(SOURCE / "terraform/variables.tf", tmp_path / "variables.tf")
    baseline = {
        "resource_group_id": RESOURCE_GROUP,
        "location": "westeurope",
        "name": "sample-dev-vnet",
        "stage": "dev",
        "address_prefix": "10.20.0.0/22",
    }
    (tmp_path / "inputs.auto.tfvars.json").write_text(
        json.dumps(baseline), encoding="utf-8"
    )
    blocks = []
    cases = _terraform_cases()
    for index, (overrides, failure) in enumerate(cases):
        assignments = "".join(
            f"    {key} = {json.dumps(value)}\n" for key, value in overrides.items()
        )
        expected = f"  expect_failures = [var.{failure}]\n" if failure else ""
        blocks.append(
            f'run "case{index}" {{\n  command = plan\n  variables {{\n{assignments}  }}\n{expected}}}\n'
        )
    (tmp_path / "contract.tftest.hcl").write_text("".join(blocks), encoding="utf-8")
    _ok(_run("terraform", tmp_path, "validate", "-json"))
    output = _ok(_run("terraform", tmp_path, "test", "-no-color"))
    assert f"Success! {len(cases)} passed, 0 failed." in output
    assert not list(tmp_path.glob("*.tfstate*"))


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    _ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


@pytest.fixture
def initialized_terraform(relocated: Path) -> Path:
    """Initialize a relocated module from the existing provider mirror only."""
    mirror = os.environ.get("CONTAINER_APPS_AZAPI_MIRROR")
    if not mirror:
        pytest.skip(
            "Full AzAPI validation needs cached Azure/azapi 2.13.0 in "
            "CONTAINER_APPS_AZAPI_MIRROR; no provider download attempted."
        )
    plugins = Path(mirror).resolve(strict=True)
    assert plugins.is_dir()
    folder = relocated / "terraform"
    _ok(
        _run(
            "terraform",
            folder,
            "init",
            "-backend=false",
            "-input=false",
            "-get=false",
            f"-plugin-dir={plugins}",
        )
    )
    return folder


def test_terraform_locks_depend_on_what_they_protect(
    initialized_terraform: Path,
) -> None:
    # Native configuration graph: reverse destroy removes each lock first.
    graph = _ok(_run("terraform", initialized_terraform, "graph"))
    edges: dict[str, set[str]] = {}
    for dependent, prerequisite in re.findall(r'"([^"]+)" -> "([^"]+)"', graph):
        edges.setdefault(dependent, set()).add(prerequisite)

    def reachable(start: str) -> set[str]:
        found: set[str] = set()
        pending = [start]
        while pending:
            resource = pending.pop()
            if resource not in found:
                found.add(resource)
                pending.extend(edges.get(resource, ()))
        return found

    assert "azapi_resource.network" in reachable("azapi_resource.protection"), graph
    assert {"azapi_resource.zone", "azapi_resource.zone_link"} <= reachable(
        "azapi_resource.zone_protection"
    ), graph


def test_terraform_full_validation_and_mock_plans(
    initialized_terraform: Path,
) -> None:
    folder = initialized_terraform
    # validate also runs AzAPI's embedded schema check on every request body.
    _ok(_run("terraform", folder, "validate", "-json"))
    output = _ok(_run("terraform", folder, "test", "-no-color"))
    assert "Success! 14 passed, 0 failed." in output, output
    assert not list(folder.glob("*.tfstate*"))
