"""Offline subscription audit-log evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/audit-logs"
)
TIMEOUT_SECONDS: Final[int] = 300
GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
)
WORKSPACE: Final[str] = (
    f"{GROUP}/providers/Microsoft.OperationalInsights/workspaces/example"
)
ACTION_GROUP: Final[str] = f"{GROUP}/providers/Microsoft.Insights/actionGroups/notify"
CATEGORIES: Final[list[str]] = [
    "Administrative",
    "Security",
    "Policy",
    "Alert",
    "ServiceHealth",
    "ResourceHealth",
]
MESSAGES: Final[dict[str, str]] = {
    "workspace": "logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID.",
    "action_group": (
        "actionGroupId must be an action group ARM ID, for example the "
        "container-apps-alerts output."
    ),
}
# Platform defaults that the sources must never restate.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "logAnalyticsDestinationType",
    "retentionPolicy",
    "incidentType",
    "impactedServices",
)
_Case = tuple[str, str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
WORKSPACE_CASES: Final[tuple[_Case, ...]] = (
    (WORKSPACE, None),
    (WORKSPACE.lower(), None),
    ("", "workspace"),
    ("example", "workspace"),
    (GROUP, "workspace"),
    (WORKSPACE.replace("OperationalInsights", "Insights"), "workspace"),
)
ACTION_GROUP_CASES: Final[tuple[_Case, ...]] = (
    (ACTION_GROUP, None),
    (ACTION_GROUP.lower(), None),
    ("", "action_group"),
    ("notify", "action_group"),
    (GROUP, "action_group"),
    (f"{GROUP}/providers/Microsoft.App/containerApps/notify", "action_group"),
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


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *(
            (f"requireWorkspaceId('{value}')", error)
            for value, error in WORKSPACE_CASES
        ),
        *(
            (f"requireActionGroupId('{value}')", error)
            for value, error in ACTION_GROUP_CASES
        ),
    ]


def _terraform_cases() -> list[tuple[Mapping[str, object], str | None]]:
    return [
        *(
            (
                {"log_analytics_workspace_id": value},
                error and "log_analytics_workspace_id",
            )
            for value, error in WORKSPACE_CASES
        ),
        *(
            ({"action_group_id": value}, error and "action_group_id")
            for value, error in ACTION_GROUP_CASES
        ),
        ({"stage": "prod"}, None),
        ({"stage": "prod", "alert_on_access_changes": False}, None),
        ({"stage": "staging"}, None),
        ({"alert_on_access_changes": True}, None),
        ({"stage": "production"}, "stage"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    target = tmp_path / "consumer/audit-logs"
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


def test_sources_are_self_contained_and_never_restate_defaults(
    relocated: Path,
) -> None:
    main = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    bicep = main + (relocated / "bicep/activity-log.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").rglob("*.tf"))
    )
    assert not list(relocated.rglob("*.tfstate*"))
    # The only module is the local subscription-scope file in this directory.
    assert re.findall(r"^module \w+ '([^']+)'", main, flags=re.MULTILINE) == [
        "activity-log.bicep"
    ]
    assert 'module "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    for forbidden in ("listKeys", "listSecrets", "Microsoft.Authorization/locks"):
        assert forbidden not in bicep + terraform
    for forbidden in ("azapi_resource_action", 'response_export_values = ["*"]'):
        assert forbidden not in terraform
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    resource_types = re.compile(r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)""")
    declared = set(resource_types.findall(bicep))
    assert declared == {
        "Microsoft.Insights/activityLogAlerts@2020-10-01",
        "Microsoft.Insights/diagnosticSettings@2021-05-01-preview",
    }
    assert declared == set(resource_types.findall(terraform))
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    for message in MESSAGES.values():
        assert message in main, message
        assert message in variables, message


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    for source in sorted([*folder.rglob("*.bicep"), *folder.rglob("*.bicepparam")]):
        rendered = _ok(_run("bicep", folder, "format", str(source), "--stdout"))
        assert rendered == source.read_text(encoding="utf-8"), source.name
    for source in ("main.bicep", "activity-log.bicep"):
        lint = _run("bicep", folder, "lint", source, "--no-restore")
        assert _ok(lint) == ""
        assert lint.stderr == ""
    template = json.loads(
        _ok(_run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))
    )
    resources = template["resources"]
    assert set(resources) == {"activityLog", "serviceHealth", "accessChanges"}
    export = resources["activityLog"]
    assert export["type"] == "Microsoft.Resources/deployments"
    assert "subscriptionId" in export
    assert "resourceGroup" not in export
    nested = export["properties"]["template"]
    assert nested["$schema"].endswith("/subscriptionDeploymentTemplate.json#")
    assert nested["variables"]["categories"] == CATEGORIES
    (setting,) = nested["resources"]
    assert setting["type"] == "Microsoft.Insights/diagnosticSettings"
    assert set(setting["properties"]) == {"copy", "workspaceId"}
    assert setting["properties"]["copy"][0]["input"]["enabled"] is True
    parameters = template["parameters"]
    for required in ("stage", "logAnalyticsWorkspaceId", "actionGroupId"):
        assert "defaultValue" not in parameters[required]
    assert (
        parameters["alertOnAccessChanges"]["defaultValue"]
        == "[contains(createArray('staging', 'prod'), parameters('stage'))]"
    )
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert set(template["outputs"]) == {"activityLogSettingId"}
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    guarded = {
        name
        for name, value in template["variables"].items()
        if "__bicep.require" in str(value)
    }
    assert guarded == {"workspaceId", "notify"}
    for example in ("tests/dev.bicepparam", "tests/prod.bicepparam"):
        _ok(_run("bicep", folder, "build-params", example, "--no-restore", "--stdout"))


def test_bicep_alerts_route_to_the_action_group(relocated: Path) -> None:
    folder = relocated / "bicep"
    template = json.loads(
        _ok(_run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))
    )
    resources = template["resources"]
    for name in ("serviceHealth", "accessChanges"):
        alert = resources[name]
        assert alert["type"] == "Microsoft.Insights/activityLogAlerts"
        assert alert["location"] == "global"
        # No restated `enabled`: rules are enabled by default.
        assert set(alert["properties"]) == {
            "description",
            "scopes",
            "condition",
            "actions",
        }
        assert alert["properties"]["scopes"] == ["[subscription().id]"]
        assert alert["properties"]["actions"] == "[variables('notify')]"
    service_health = resources["serviceHealth"]
    assert "condition" not in service_health
    assert service_health["properties"]["condition"] == {
        "allOf": [{"field": "category", "equals": "ServiceHealth"}]
    }
    access = resources["accessChanges"]
    assert access["condition"] == "[parameters('alertOnAccessChanges')]"
    conditions = access["properties"]["condition"]["allOf"]
    assert conditions[:2] == [
        {"field": "category", "equals": "Administrative"},
        {"field": "status", "equals": "Succeeded"},
    ]
    operations = template["variables"]["accessOperations"]
    assert len(operations) == 6
    assert all(
        operation.startswith("Microsoft.Authorization/") for operation in operations
    )


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        ("OperationalInsights", "Insights", "workspace"),
        (
            "Microsoft.Insights/actionGroups",
            "Microsoft.Insights/actionRules",
            "action_group",
        ),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    folder = relocated / "bicep/tests"
    example = (folder / "prod.bicepparam").read_text(encoding="utf-8")
    unsafe_text, replaced = re.subn(re.escape(pattern), replacement, example, count=1)
    assert replaced == 1
    unsafe = folder / "unsafe.bicepparam"
    unsafe.write_text(unsafe_text, encoding="utf-8")
    result = _run(
        "bicep", folder, "build-params", unsafe.name, "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert MESSAGES[error] in result.stderr, result.stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    folder = relocated / "bicep"
    header = (
        "using none\n"
        "import { requireActionGroupId, requireWorkspaceId } from './main.bicep'\n"
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
        "resource_group_id": GROUP,
        "stage": "dev",
        "log_analytics_workspace_id": WORKSPACE,
        "action_group_id": ACTION_GROUP,
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
