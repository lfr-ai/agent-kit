"""Offline storage composition evidence; no account context, downloads or deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/storage-account"
)
TIMEOUT_SECONDS: Final[int] = 900
NAME_LENGTH: Final[tuple[int, int]] = (3, 24)
CONTAINER_LENGTH: Final[tuple[int, int]] = (3, 63)
PRINCIPAL_LENGTH: Final[int] = 36
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
BLOB_CONTRIBUTOR_ROLE: Final[str] = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
RESOURCE_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
)
SUBNET: Final[str] = (
    f"{RESOURCE_GROUP}/providers/Microsoft.Network/virtualNetworks/example/subnets/storage"
)
ZONE: Final[str] = (
    f"{RESOURCE_GROUP}/providers/Microsoft.Network/privateDnsZones/"
    "privatelink.blob.core.windows.net"
)
WORKSPACE: Final[str] = (
    f"{RESOURCE_GROUP}/providers/Microsoft.OperationalInsights/workspaces/example"
)
ACCOUNTS: Final[str] = f"{RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts"
# Role-assignment names asserted literally by the Terraform mocked plans.
ASSIGNMENT_NAMES: Final[dict[str, str]] = {
    f"{ACCOUNTS}/sampledevstorage": "62eb3300-6905-5524-8277-5caf485a4f5d",
    f"{ACCOUNTS}/sampleprodstorage/blobServices/default/containers/uploads": (
        "7f7ae395-db58-560e-ad5e-24f4d3476cfe"
    ),
    f"{ACCOUNTS}/sampleprodstorage/blobServices/default/containers/exports": (
        "eda4d73d-a660-53ce-8726-0f7631a43caf"
    ),
}
MESSAGES: Final[dict[str, str]] = {
    "network": (
        "Staging and production require privateEndpoint: an existing subnet and "
        "privatelink.blob.core.windows.net zone."
    ),
    "zone": (
        "privateEndpoint needs a subnet ARM ID and a "
        "privatelink.blob.core.windows.net private DNS zone ARM ID."
    ),
    "workspace": (
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
_PRIVATE = (SUBNET, ZONE)
NETWORK_CASES: Final[tuple[tuple[str, tuple[str, str] | None, str | None], ...]] = (
    ("dev", None, None),
    ("test", _PRIVATE, None),
    ("staging", _PRIVATE, None),
    ("prod", _PRIVATE, None),
    ("prod", None, "network"),
    ("staging", None, "network"),
    ("dev", (SUBNET, ZONE.upper()), "zone"),
    ("test", (SUBNET, ""), "zone"),
    ("dev", (SUBNET, ZONE.replace("blob", "file")), "zone"),
    ("dev", (SUBNET, f"{ZONE}/extra"), "zone"),
    ("dev", (SUBNET.replace("/subnets/", "/subnet/"), ZONE), "zone"),
    ("dev", (SUBNET.rsplit("/subnets/", 1)[0], ZONE), "zone"),
)
_PublicCase = tuple[str, tuple[str, str] | None, bool, list[str], str | None]
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
WORKSPACE_CASES: Final[tuple[tuple[str, str | None, str | None], ...]] = (
    ("dev", None, None),
    ("test", WORKSPACE, None),
    ("staging", WORKSPACE, None),
    ("prod", WORKSPACE, None),
    ("prod", None, "workspace"),
    ("staging", None, "workspace"),
    ("dev", "", "workspace_empty"),
    ("prod", "", "workspace_empty"),
)


def _run(name: str, folder: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return iac.run_isolated(name, folder, *arguments, timeout=TIMEOUT_SECONDS)


def _ok(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return result.stdout


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Relocate the byte-identical source closure without borrowing sibling modules."""
    target = tmp_path / "consumer/storage-account"
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


def test_sources_are_complete_pinned_and_entra_only(relocated: Path) -> None:
    for required in ("README.md", "REFERENCE.md", "terraform/variables.tf"):
        assert (relocated / required).is_file(), required
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").glob("*.tf"))
    )
    assert not list(relocated.rglob("*.tfstate*"))
    assert "module " not in bicep
    assert 'module "' not in terraform
    assert 'provider "azapi"' not in terraform
    assert 'backend "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    assert "allowSharedKeyAccess: false" in bicep
    assert "allowSharedKeyAccess         = false" in terraform
    for forbidden in ("listKeys", "listAccountSas", "listServiceSas"):
        assert forbidden not in bicep + terraform
    for forbidden in ("azapi_resource_action", 'response_export_values = ["*"]'):
        assert forbidden not in terraform
    types = re.compile(r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)""")
    assert set(types.findall(bicep)) == set(types.findall(terraform))
    assert len(set(types.findall(bicep))) == 8
    assert BLOB_CONTRIBUTOR_ROLE in bicep
    assert BLOB_CONTRIBUTOR_ROLE in terraform
    assert terraform.count('"ServicePrincipal"') == 2
    # One named soft-delete window per flavour, used by both retention policies.
    assert bicep.count("var softDeleteRetentionDays = 30\n") == 1
    assert bicep.count("days: softDeleteRetentionDays }") == 2
    assert len(re.findall(r"\bsoft_delete_retention_days\s+= 30\n", terraform)) == 1
    assert terraform.count("days = local.soft_delete_retention_days }") == 2
    assert "days: 30 }" not in bicep
    assert "days = 30 }" not in terraform
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    for message in MESSAGES.values():
        assert message in bicep
        assert message in variables


def _assert_blob_contract(resources: dict[str, dict[str, object]]) -> None:
    account = resources["account"]
    assert account["kind"] == "StorageV2"
    assert account["sku"] == {
        "name": "[if(equals(parameters('stage'), 'prod'), 'Standard_ZRS', 'Standard_LRS')]"
    }
    properties = str(account["properties"])
    for expected in (
        "'allowSharedKeyAccess', false()",
        "'defaultToOAuthAuthentication', true()",
        "'allowBlobPublicAccess', false()",
        "'minimumTlsVersion', 'TLS1_2'",
        "'publicNetworkAccess', 'Disabled'",
        (
            "if(parameters('allowPublicNetworkAccess'), createObject('networkAcls', "
            "createObject('defaultAction', 'Deny', 'ipRules'"
        ),
    ):
        assert expected in properties
    retention = str(resources["blobService"]["properties"])
    assert "if(equals(parameters('stage'), 'prod')" in retention
    for setting in (
        "'isVersioningEnabled', true()",
        (
            "'deleteRetentionPolicy', createObject('enabled', true(), "
            "'days', variables('softDeleteRetentionDays'))"
        ),
        (
            "'containerDeleteRetentionPolicy', createObject('enabled', true(), "
            "'days', variables('softDeleteRetentionDays'))"
        ),
    ):
        assert setting in retention
    container = resources["blobContainers"]
    assert "properties" not in container
    assert container["copy"] == {
        "name": "blobContainers",
        "count": "[length(parameters('containers'))]",
    }


def _assert_private_contract(resources: dict[str, dict[str, object]]) -> None:
    endpoint = resources["endpoint"]
    assert endpoint["condition"] == "[not(equals(variables('network'), null()))]"
    assert '"groupIds": ["blob"]' in json.dumps(endpoint["properties"])
    dns = resources["dnsZoneGroup"]
    assert dns["condition"] == endpoint["condition"]
    assert "variables('network').privateDnsZoneId" in str(dns["properties"])
    diagnostics = resources["diagnostics"]
    assert diagnostics["condition"] == (
        "[not(equals(variables('workspaceId'), null()))]"
    )
    assert "/blobServices/" in str(diagnostics["scope"])
    assert diagnostics["properties"] == {
        "workspaceId": "[variables('workspaceId')]",
        "logs": [
            {"category": category, "enabled": True}
            for category in ("StorageRead", "StorageWrite", "StorageDelete")
        ],
        "metrics": [{"category": "Transaction", "enabled": True}],
    }
    lock = resources["protection"]
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"
    assert (
        lock["scope"]
        == "[format('Microsoft.Storage/storageAccounts/{0}', parameters('name'))]"
    )
    assert lock["properties"] == {"level": "CanNotDelete"}


def _assert_role_contract(resources: dict[str, dict[str, object]]) -> None:
    properties = {
        "roleDefinitionId": (
            "[subscriptionResourceId('Microsoft.Authorization/roleDefinitions', "
            "variables('blobContributorRoleId'))]"
        ),
        "principalId": "[parameters('principalId')]",
        "principalType": "ServicePrincipal",
    }
    containers = resources["containerBlobContributor"]
    assert containers["type"] == "Microsoft.Authorization/roleAssignments"
    assert containers["copy"] == {
        "name": "containerBlobContributor",
        "count": "[length(parameters('containers'))]",
    }
    container_id = (
        "resourceId('Microsoft.Storage/storageAccounts/blobServices/containers', "
        "parameters('name'), 'default', parameters('containers')[copyIndex()])"
    )
    assert containers["name"] == (
        f"[guid({container_id}, parameters('principalId'), "
        "variables('blobContributorRoleId'))]"
    )
    assert "/containers/" in str(containers["scope"])
    assert containers["properties"] == properties
    account = resources["accountBlobContributor"]
    assert account["condition"] == "[empty(parameters('containers'))]"
    assert account["name"] == (
        "[guid(resourceId('Microsoft.Storage/storageAccounts', parameters('name')), "
        "parameters('principalId'), variables('blobContributorRoleId'))]"
    )
    assert (
        account["scope"]
        == "[format('Microsoft.Storage/storageAccounts/{0}', parameters('name'))]"
    )
    assert account["properties"] == properties


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
    assert len(template["resources"]) == 9
    assert template["variables"]["blobContributorRoleId"] == BLOB_CONTRIBUTOR_ROLE
    assert template["variables"]["softDeleteRetentionDays"] == 30
    _assert_blob_contract(template["resources"])
    _assert_role_contract(template["resources"])
    _assert_private_contract(template["resources"])
    parameters = template["parameters"]
    assert (
        parameters["name"]["minLength"],
        parameters["name"]["maxLength"],
    ) == NAME_LENGTH
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["containers"]["defaultValue"] == []
    assert "defaultValue" not in parameters["principalId"]
    assert parameters["principalId"]["minLength"] == PRINCIPAL_LENGTH
    assert parameters["principalId"]["maxLength"] == PRINCIPAL_LENGTH
    assert parameters["privateEndpoint"]["nullable"] is True
    assert parameters["allowPublicNetworkAccess"]["defaultValue"] is False
    assert parameters["allowedIpRanges"]["defaultValue"] == []
    # Omitted means no diagnostics; an empty string is rejected, never "absent".
    workspace_parameter = parameters["logAnalyticsWorkspaceId"]
    assert workspace_parameter["nullable"] is True
    assert workspace_parameter["minLength"] == 1
    assert "defaultValue" not in workspace_parameter
    guarded = {
        name
        for name, value in template["variables"].items()
        if "__bicep.require" in str(value)
    }
    assert guarded == {"network", "ipRanges", "workspaceId"}
    assert set(template["outputs"]) == {
        "storageAccountId",
        "blobEndpoint",
        "containerNames",
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


def _bicep_string(value: str | None) -> str:
    return "null" if value is None else f"'{value}'"


def test_bicep_shared_input_guards(relocated: Path) -> None:
    folder = relocated / "bicep"
    cases = []
    for stage, network, error in NETWORK_CASES:
        value = (
            "null"
            if network is None
            else (f"{{ subnetId: '{network[0]}', privateDnsZoneId: '{network[1]}' }}")
        )
        cases.append((f"requirePrivateEndpoint('{stage}', {value})", error))
    cases.extend(
        (
            (
                f"requirePublicAccess('{stage}', "
                f"{str(network is not None).lower()}, {str(allow).lower()}, {ranges!r})"
            ),
            error,
        )
        for stage, network, allow, ranges, error in PUBLIC_CASES
    )
    cases.extend(
        (f"requireWorkspace('{stage}', {_bicep_string(workspace)})", error)
        for stage, workspace, error in WORKSPACE_CASES
    )
    header = (
        "using none\n"
        "import { requirePrivateEndpoint, requirePublicAccess, requireWorkspace }"
        " from './main.bicep'\n"
    )
    for accepted in (True, False):
        selected = [
            (i, expr, error)
            for i, (expr, error) in enumerate(cases)
            if (error is None) == accepted
        ]
        fixture = folder / "guards.bicepparam"
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


def test_bicep_guid_matches_terraform_assignment_names(relocated: Path) -> None:
    # The Terraform tests assert these literal uuidv5() names; Bicep guid() must agree.
    folder = relocated / "bicep"
    fixture = folder / "names.bicepparam"
    fixture.write_text(
        "using none\n"
        + "".join(
            f"param name{index} = guid('{scope}', '{PRINCIPAL}', "
            f"'{BLOB_CONTRIBUTOR_ROLE}')\n"
            for index, scope in enumerate(ASSIGNMENT_NAMES)
        ),
        encoding="utf-8",
    )
    result = json.loads(
        _ok(
            _run(
                "bicep",
                folder,
                "build-params",
                fixture.name,
                "--no-restore",
                "--stdout",
            )
        )
    )
    values = json.loads(result["parametersJson"])["parameters"]
    assert [values[f"name{index}"]["value"] for index in range(len(values))] == list(
        ASSIGNMENT_NAMES.values()
    )
    tests = (relocated / "terraform/tests/storage-account.tftest.hcl").read_text(
        encoding="utf-8"
    )
    for scope, name in ASSIGNMENT_NAMES.items():
        assert f'id = "{scope}"' in tests or f'id     = "{scope}"' in tests
        assert f'"{name}"' in tests


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"\(stage, \{.*?\}\)", "(stage, null)", "network"),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, null)",
            "workspace",
        ),
        (
            r"privatelink\.blob\.core\.windows\.net'",
            "privatelink.file.core.windows.net'",
            "zone",
        ),
    ],
)
def test_bicep_production_example_rejects_unsafe_inputs(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    folder = relocated / "bicep/tests"
    example = (folder / "prod.bicepparam").read_text(encoding="utf-8")
    unsafe, count = re.subn(pattern, replacement, example, count=1, flags=re.DOTALL)
    assert count == 1
    (folder / "unsafe.bicepparam").write_text(unsafe, encoding="utf-8")
    result = _run(
        "bicep", folder, "build-params", "unsafe.bicepparam", "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert MESSAGES[error] in result.stderr


def _terraform_cases() -> list[tuple[dict[str, object], str | None]]:
    private = {"subnet_id": SUBNET, "private_dns_zone_id": ZONE}
    cases: list[tuple[dict[str, object], str | None]] = [
        (
            {
                "stage": stage,
                "private_endpoint": None
                if network is None
                else {"subnet_id": network[0], "private_dns_zone_id": network[1]},
                "log_analytics_workspace_id": WORKSPACE,
            },
            "private_endpoint" if error else None,
        )
        for stage, network, error in NETWORK_CASES
    ]
    cases.extend(
        (
            {
                "stage": stage,
                "private_endpoint": private,
                "log_analytics_workspace_id": workspace,
            },
            "log_analytics_workspace_id" if error else None,
        )
        for stage, workspace, error in WORKSPACE_CASES
    )
    cases.extend(
        (
            {
                "stage": stage,
                "private_endpoint": None
                if network is None
                else {"subnet_id": network[0], "private_dns_zone_id": network[1]},
                "allow_public_network_access": allow,
                "allowed_ip_ranges": ranges,
                "log_analytics_workspace_id": WORKSPACE,
            },
            None
            if error is None
            else "allow_public_network_access"
            if error == "public_stage"
            else "allowed_ip_ranges",
        )
        for stage, network, allow, ranges, error in PUBLIC_CASES
    )
    cases.extend(({"name": "a" * length}, None) for length in NAME_LENGTH)
    cases.extend(({"containers": ["a" * length]}, None) for length in CONTAINER_LENGTH)
    cases.extend(
        ({key: value}, key)
        for key, value in (
            ("name", "aa"),
            ("name", "a" * (NAME_LENGTH[1] + 1)),
            ("name", "Uppercase"),
            ("name", "has-hyphen"),
            ("containers", ["aa"]),
            ("containers", ["a" * (CONTAINER_LENGTH[1] + 1)]),
            ("containers", ["UPPER"]),
            ("containers", ["-prefix"]),
            ("containers", ["suffix-"]),
            ("containers", ["two--hyphens"]),
            ("containers", ["duplicate", "duplicate"]),
            ("stage", "production"),
            ("location", " "),
            ("resource_group_id", "example"),
            ("principal_id", "not-a-guid"),
            ("principal_id", PRINCIPAL + "0"),
        )
    )
    return cases


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    shutil.copyfile(SOURCE / "terraform/variables.tf", tmp_path / "variables.tf")
    baseline = {
        "resource_group_id": RESOURCE_GROUP,
        "location": "westeurope",
        "name": "sampledevstorage",
        "stage": "dev",
        "principal_id": PRINCIPAL,
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


def test_terraform_lock_depends_on_every_protected_child(
    initialized_terraform: Path,
) -> None:
    # Native configuration graph, not a mock-plan assertion. Terraform destroys
    # dependants before their dependencies; reachability excludes sibling races.
    graph = _ok(_run("terraform", initialized_terraform, "graph"))
    edges: dict[str, set[str]] = {}
    for dependent, prerequisite in re.findall(r'"([^"]+)" -> "([^"]+)"', graph):
        edges.setdefault(dependent, set()).add(prerequisite)
    dependencies: set[str] = set()
    pending = ["azapi_resource.protection"]
    while pending:
        resource = pending.pop()
        if resource not in dependencies:
            dependencies.add(resource)
            pending.extend(edges.get(resource, ()))
    protected = {
        "azapi_resource.account",
        "azapi_resource.blob_service",
        "azapi_resource.container",
        "azapi_resource.container_blob_contributor",
        "azapi_resource.account_blob_contributor",
        "azapi_resource.diagnostics",
    }
    assert protected <= dependencies, (
        f"Lock lacks dependency paths to {sorted(protected - dependencies)}; "
        f"destroy can race the inherited deletion lock.\n{graph}"
    )


def test_terraform_full_validation_and_mock_plans(
    initialized_terraform: Path,
) -> None:
    folder = initialized_terraform
    _ok(_run("terraform", folder, "validate", "-json"))
    output = _ok(_run("terraform", folder, "test", "-no-color"))
    assert "Success! 8 passed, 0 failed." in output, output
    assert not list(folder.glob("*.tfstate*"))
