"""Offline Container Apps alert evidence from installed tools; never a deployment."""

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
    Path(__file__).resolve().parents[4]
    / "packages/delivery/infra/container-apps-alerts"
)
TIMEOUT_SECONDS: Final[int] = 300
GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
)
APP: Final[str] = f"{GROUP}/providers/Microsoft.App/containerApps/sample-dev"
ACTION_GROUP: Final[str] = (
    f"{GROUP}/providers/Microsoft.Insights/actionGroups/operations"
)
MESSAGES: Final[dict[str, str]] = {
    "name": (
        "name must use 2-32 lowercase letters, digits or single hyphens; "
        "start with a letter and end alphanumeric."
    ),
    "app": "containerAppResourceId must be a Microsoft.App/containerApps ARM ID.",
    "emails": "emailReceivers must be email addresses, for example ops@example.com.",
    "group": "existingActionGroupResourceId must be an action group ARM ID.",
    "none_dev": (
        "Set exactly one of emailReceivers, existingActionGroupResourceId or "
        "unmonitored=true."
    ),
    "none_prod": (
        "Staging and production require emailReceivers or "
        "existingActionGroupResourceId."
    ),
    "unmonitored_prod": (
        "unmonitored is allowed only for dev and test; staging and production "
        "require emailReceivers or existingActionGroupResourceId."
    ),
    "exclusive": (
        "emailReceivers, existingActionGroupResourceId and unmonitored are "
        "mutually exclusive; set exactly one."
    ),
}
# Defaults (or values derived from the single-resource scope) never restated.
# autoMitigate is deliberately explicit (true) on both metric alerts.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "useAadAuth",
    "skipMetricValidation",
    "metricNamespace",
    "targetResourceType",
    "targetResourceRegion",
)
# The inline Teams webhook secret and the Resource Health alert are removed.
REMOVED_TERMS: Final[tuple[str, ...]] = (
    "teamsWebhook",
    "teams_webhook",
    "webhookReceivers",
    "sensitive_body",
    "activityLogAlerts",
    "ResourceHealth",
)
# Real webhook hosts must never appear in sources or fixtures.
WEBHOOK_HOSTS: Final[tuple[str, ...]] = (
    "webhook.office.com",
    "logic.azure.com",
    "powerplatform.com",
)
_Case = tuple[str, str | None]
_GroupCase = tuple[str | None, str | None]
# (stage, emails, existing group (None = omitted), unmonitored, error)
_DestinationCase = tuple[str, tuple[str, ...], str | None, bool, str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
NAME_CASES: Final[tuple[_Case, ...]] = (
    ("sample-dev", None),
    ("a1", None),
    ("a" * 33, "name"),
    ("Sample", "name"),
    ("1sample", "name"),
    ("sample-", "name"),
    ("sample--dev", "name"),
)
APP_CASES: Final[tuple[_Case, ...]] = (
    (APP, None),
    (APP.replace("sample-dev", "orders"), None),
    (GROUP, "app"),
    ("sample-dev", "app"),
    (f"{APP}/revisions/sample-dev--r1", "app"),
    (APP.removesuffix("sample-dev"), "app"),
    (APP.replace("containerApps", "managedEnvironments"), "app"),
)
DESTINATION_CASES: Final[tuple[_DestinationCase, ...]] = (
    ("dev", (), None, True, None),
    ("test", (), None, True, None),
    ("dev", ("ops@example.com",), None, False, None),
    ("test", ("ops@example.com", "alerts@example.org"), None, False, None),
    ("dev", (), ACTION_GROUP, False, None),
    ("prod", ("ops@example.com",), None, False, None),
    ("prod", (), ACTION_GROUP, False, None),
    ("staging", ("ops@example.com",), None, False, None),
    ("staging", (), ACTION_GROUP, False, None),
    ("dev", (), None, False, "none_dev"),
    ("test", (), None, False, "none_dev"),
    ("prod", (), None, False, "none_prod"),
    ("staging", (), None, False, "none_prod"),
    ("prod", (), None, True, "unmonitored_prod"),
    ("staging", (), None, True, "unmonitored_prod"),
    ("dev", ("ops@example.com",), ACTION_GROUP, False, "exclusive"),
    ("dev", ("ops@example.com",), None, True, "exclusive"),
    ("dev", (), ACTION_GROUP, True, "exclusive"),
    ("prod", ("ops@example.com",), ACTION_GROUP, False, "exclusive"),
    ("dev", ("ops",), None, False, "emails"),
    ("dev", ("ops@",), None, False, "emails"),
    ("dev", ("@example.com",), None, False, "emails"),
    ("dev", ("ops@ex@ample.com",), None, False, "emails"),
    ("dev", ("ops @example.com",), None, False, "emails"),
    ("dev", ("ops\t@example.com",), None, False, "emails"),
    ("prod", ("ops@example.com\n",), None, False, "emails"),
    ("staging", ("ops@\u00a0example.com",), None, False, "emails"),
    ("prod", ("ops@example.com", "ops"), None, False, "emails"),
)
GROUP_CASES: Final[tuple[_GroupCase, ...]] = (
    (None, None),
    # Omission (null) is the only absent form; an empty string is rejected.
    ("", "group"),
    (ACTION_GROUP, None),
    (GROUP, "group"),
    (ACTION_GROUP + "/extra", "group"),
    (ACTION_GROUP.replace("actionGroups", "components"), "group"),
    (ACTION_GROUP + " ", "group"),
    (ACTION_GROUP.replace("operations", "oper\tations"), "group"),
    (ACTION_GROUP.replace("example", "ex\u00a0ample"), "group"),
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


def _bicep_destination(
    stage: str, emails: tuple[str, ...], group: str | None, unmonitored: bool
) -> str:
    addresses = ", ".join(_bicep_string(address) for address in emails)
    return (
        f"requireEmailReceivers('{stage}', [{addresses}], {_bicep_string(group)}, "
        f"{str(unmonitored).lower()})"
    )


def _bicep_string(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("\t", "\\t").replace("\n", "\\n") + "'"


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *((f"requireName('{value}')", error) for value, error in NAME_CASES),
        *((f"requireContainerAppId('{value}')", error) for value, error in APP_CASES),
        *(
            (_bicep_destination(stage, emails, group, unmonitored), error)
            for stage, emails, group, unmonitored, error in DESTINATION_CASES
        ),
        *(
            (f"requireActionGroup({_bicep_string(value)})", error)
            for value, error in GROUP_CASES
        ),
    ]


_TERRAFORM_FAILURES = {
    "name": "name_prefix",
    "app": "container_app_resource_id",
    "emails": "email_receivers",
    "group": "existing_action_group_resource_id",
    "none_dev": "unmonitored",
    "none_prod": "unmonitored",
    "unmonitored_prod": "unmonitored",
    "exclusive": "unmonitored",
}


def _terraform_cases() -> list[tuple[Mapping[str, object], str | None]]:
    return [
        *(
            ({"name_prefix": value}, error and _TERRAFORM_FAILURES[error])
            for value, error in NAME_CASES
        ),
        *(
            (
                {"container_app_resource_id": value},
                error and _TERRAFORM_FAILURES[error],
            )
            for value, error in APP_CASES
        ),
        *(
            (
                {
                    "stage": stage,
                    "email_receivers": list(emails),
                    "existing_action_group_resource_id": group,
                    "unmonitored": unmonitored,
                },
                error and _TERRAFORM_FAILURES[error],
            )
            for stage, emails, group, unmonitored, error in DESTINATION_CASES
        ),
        *(
            (
                # The baseline opt-out would conflict with a supplied group.
                {
                    "existing_action_group_resource_id": value,
                    "unmonitored": value is None,
                },
                error and _TERRAFORM_FAILURES[error],
            )
            for value, error in GROUP_CASES
        ),
        ({"stage": "production"}, "stage"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    target = tmp_path / "consumer/container-apps-alerts"
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


def test_sources_are_self_contained_and_carry_no_webhook_secret(
    relocated: Path,
) -> None:
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").rglob("*.tf"))
    )
    fixtures = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(relocated.rglob("*"))
        if path.is_file() and path.suffix in {".bicepparam", ".hcl"}
    )
    assert not list(relocated.rglob("*.tfstate*"))
    assert "module " not in bicep
    assert 'module "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    assert 'response_export_values = ["*"]' not in terraform
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    for host in WEBHOOK_HOSTS:
        assert host not in bicep + terraform + fixtures, host
    for term in REMOVED_TERMS:
        assert term not in bicep + terraform, f"{term} was removed from the module"
    assert "@secure" not in bicep
    assert "sensitive   = true" not in terraform
    # Both rules state auto-resolve explicitly.
    assert bicep.count("autoMitigate: true") == 2
    assert terraform.count("autoMitigate        = true") == 2
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    outputs = (relocated / "terraform/outputs.tf").read_text(encoding="utf-8")
    assert "teams" not in outputs
    resource_types = re.compile(r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)""")
    declared = set(resource_types.findall(bicep))
    assert declared == {
        "Microsoft.Insights/actionGroups@2023-01-01",
        "Microsoft.Insights/metricAlerts@2018-03-01",
    }
    assert declared == set(resource_types.findall(terraform))
    for message in MESSAGES.values():
        assert message in bicep, message
        assert message in variables, message


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def test_alert_policy_is_named_once_in_both_flavours(relocated: Path) -> None:
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = (relocated / "terraform/main.tf").read_text(encoding="utf-8")
    for bicep_name, (terraform_name, _) in ALERT_POLICY.items():
        assert len(re.findall(rf"^var {bicep_name} = ", bicep, re.MULTILINE)) == 1
        declared = re.findall(rf"^\s+{terraform_name}\s+= ", terraform, re.MULTILINE)
        assert len(declared) == 1, terraform_name
    for source in (bicep, terraform):
        # Rules reference the names; no severity, threshold or window literal repeats.
        assert re.search(r"\b(?:severity|threshold)\s*[:=]\s*\d", source) is None
        assert source.count("PT1M") == 1
        assert "PT5M" not in source
        # Descriptions interpolate the thresholds instead of restating them.
        assert "more than 3" not in source
        assert "More than 5" not in source
        assert "5 minutes" not in source


# Alert policy names, each declared once in both flavours (Bicep variable, Terraform local).
ALERT_POLICY: Final[dict[str, tuple[str, object]]] = {
    "alertSeverity": ("alert_severity", 2),
    "evaluationFrequency": ("evaluation_frequency", "PT1M"),
    "windowMinutes": ("window_minutes", 5),
    "restartThreshold": ("restart_threshold", 3),
    "serverErrorThreshold": ("server_error_threshold", 5),
}


def _assert_alerts(template: Mapping[str, Mapping[str, object]]) -> None:
    """Each rule targets the app, routes to the action group and states its signal."""
    resources = template["resources"]
    variables = template["variables"]
    for name, (_, value) in ALERT_POLICY.items():
        assert variables[name] == value, name
    assert variables["windowSize"] == "[format('PT{0}M', variables('windowMinutes'))]"
    expected = {
        "restarts": (
            "restarts",
            "RestartCount",
            "Maximum",
            "restartThreshold",
            None,
            (
                "[format('A replica restarted more than {0} times: crash loop or "
                "failing probes.', variables('restartThreshold'))]"
            ),
        ),
        "serverErrors": (
            "server-errors",
            "Requests",
            "Total",
            "serverErrorThreshold",
            [{"name": "statusCodeCategory", "operator": "Include", "values": ["5xx"]}],
            (
                "[format('More than {0} HTTP 5xx responses in {1} minutes.', "
                "variables('serverErrorThreshold'), variables('windowMinutes'))]"
            ),
        ),
    }
    for symbol, (
        name,
        metric,
        aggregation,
        threshold,
        dimensions,
        description,
    ) in expected.items():
        rule = _mapping(resources[symbol])
        assert rule["type"] == "Microsoft.Insights/metricAlerts"
        assert rule["location"] == "global"
        properties = _mapping(rule["properties"])
        assert set(properties) == {
            "description",
            "severity",
            "enabled",
            "autoMitigate",
            "scopes",
            "evaluationFrequency",
            "windowSize",
            "criteria",
            "actions",
        }
        # Descriptions are generated from the named thresholds, never restated.
        assert properties["description"] == description
        assert properties["severity"] == "[variables('alertSeverity')]"
        assert properties["autoMitigate"] is True
        assert properties["actions"] == "[variables('alertActions')]"
        assert (properties["evaluationFrequency"], properties["windowSize"]) == (
            "[variables('evaluationFrequency')]",
            "[variables('windowSize')]",
        )
        criterion = {
            "criterionType": "StaticThresholdCriterion",
            "name": name,
            "metricName": metric,
            "timeAggregation": aggregation,
            "operator": "GreaterThan",
            "threshold": f"[variables('{threshold}')]",
        } | ({"dimensions": dimensions} if dimensions else {})
        assert properties["criteria"] == {
            "odata.type": "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria",
            "allOf": [criterion],
        }
        assert properties["scopes"] == ["[variables('appId')]"]
        assert rule["dependsOn"] == ["notify"]


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    for source in sorted([*folder.rglob("*.bicep"), *folder.rglob("*.bicepparam")]):
        rendered = _ok(_run("bicep", folder, "format", str(source), "--stdout"))
        assert rendered == source.read_text(encoding="utf-8"), source.name
    lint = _run("bicep", folder, "lint", "main.bicep", "--no-restore")
    assert _ok(lint) == ""
    assert lint.stderr == ""
    template = json.loads(
        _ok(_run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))
    )
    resources = template["resources"]
    # No Resource Health alert: Container Apps is not a supported type.
    assert set(resources) == {"notify", "restarts", "serverErrors"}
    notify = resources["notify"]
    assert notify["type"] == "Microsoft.Insights/actionGroups"
    assert notify["location"] == "global"
    assert "condition" in notify
    properties = notify["properties"]
    assert set(properties) == {"groupShortName", "enabled", "emailReceivers"}
    assert properties["groupShortName"] == "[take(variables('prefix'), 12)]"
    assert "useCommonAlertSchema" not in properties["emailReceivers"]
    _assert_alerts(template)
    assert set(template["outputs"]) == {"actionGroupId"}
    # Null when unmonitored, never an empty string.
    assert template["outputs"]["actionGroupId"]["nullable"] is True
    parameters = template["parameters"]
    for required in ("namePrefix", "stage", "containerAppResourceId"):
        assert "defaultValue" not in parameters[required]
    assert set(parameters) == {
        "namePrefix",
        "stage",
        "containerAppResourceId",
        "emailReceivers",
        "existingActionGroupResourceId",
        "unmonitored",
    }
    assert parameters["emailReceivers"]["defaultValue"] == []
    assert "defaultValue" not in parameters["existingActionGroupResourceId"]
    assert parameters["existingActionGroupResourceId"]["nullable"] is True
    assert parameters["existingActionGroupResourceId"]["minLength"] == 1
    assert parameters["unmonitored"]["type"] == "bool"
    assert parameters["unmonitored"]["defaultValue"] is False
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    guarded = {
        name
        for name, value in template["variables"].items()
        if "__bicep.require" in str(value)
    }
    assert guarded == {"prefix", "appId", "emails", "existingGroupId"}
    for example in ("tests/dev.bicepparam", "tests/prod.bicepparam"):
        _ok(_run("bicep", folder, "build-params", example, "--no-restore", "--stdout"))


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"\['operations@example\.com'\]", "[]", "none_prod"),
        ("'operations@example.com'", "'operations'", "emails"),
        (r"null, false\)", "null, true)", "unmonitored_prod"),
        ("Microsoft.App/containerApps/", "Microsoft.App/managedEnvironments/", "app"),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    folder = relocated / "bicep/tests"
    example = (folder / "prod.bicepparam").read_text(encoding="utf-8")
    unsafe_text, replaced = re.subn(pattern, replacement, example, count=1)
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
        "import { requireName, requireContainerAppId, requireEmailReceivers,"
        " requireActionGroup } from './main.bicep'\n"
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


@pytest.mark.parametrize(
    ("group", "emails", "unmonitored", "failure"),
    [
        (ACTION_GROUP, [], False, None),
        (GROUP, [], False, "existing_action_group_resource_id"),
        (ACTION_GROUP + "/extra", [], False, "existing_action_group_resource_id"),
        (ACTION_GROUP, ["ops@example.com"], False, "unmonitored"),
        (ACTION_GROUP, [], True, "unmonitored"),
    ],
)
def test_terraform_existing_action_group_guards(
    tmp_path: Path,
    group: str,
    emails: list[str],
    unmonitored: bool,
    failure: str | None,
) -> None:
    shutil.copyfile(SOURCE / "terraform/variables.tf", tmp_path / "variables.tf")
    (tmp_path / "inputs.auto.tfvars.json").write_text(
        json.dumps(
            {
                "resource_group_id": GROUP,
                "name_prefix": "sample-prod",
                "stage": "prod",
                "container_app_resource_id": APP,
                "existing_action_group_resource_id": group,
                "email_receivers": emails,
                "unmonitored": unmonitored,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "existing.tftest.hcl").write_text(
        'run "existing" {\n  command = plan\n'
        + (f"  expect_failures = [var.{failure}]\n" if failure else "")
        + "}\n",
        encoding="utf-8",
    )
    _ok(_run("terraform", tmp_path, "validate", "-json"))
    _ok(_run("terraform", tmp_path, "test", "-no-color"))
    assert not list(tmp_path.glob("*.tfstate*"))


def test_existing_action_group_is_reference_only_and_preserves_owned_state_address(
    relocated: Path,
) -> None:
    compiled = json.loads(
        _ok(
            _run(
                "bicep",
                relocated / "bicep",
                "build",
                "main.bicep",
                "--no-restore",
                "--stdout",
            )
        )
    )
    group = compiled["parameters"]["existingActionGroupResourceId"]
    assert "defaultValue" not in group
    assert group["nullable"] is True
    assert "condition" in compiled["resources"]["notify"]
    for symbol in ("restarts", "serverErrors"):
        assert "variables('alertActions')" in str(
            compiled["resources"][symbol]["properties"]["actions"]
        )
    assert "variables('notificationGroupId')" in str(
        compiled["variables"]["alertActions"]
    )
    terraform = (relocated / "terraform/main.tf").read_text()
    assert "count     = local.create_group ? 1 : 0" in terraform
    assert "from = azapi_resource.notify\n" in terraform
    assert "to   = azapi_resource.notify[0]" in terraform
    assert terraform.count("actions = local.alert_actions") == 2
    assert 'data "azapi_resource"' not in terraform


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    # The unchanged variables.tf alone proves input validation, not AzAPI schemas.
    shutil.copyfile(SOURCE / "terraform/variables.tf", tmp_path / "variables.tf")
    baseline = {
        "resource_group_id": GROUP,
        "name_prefix": "sample-dev",
        "stage": "dev",
        "container_app_resource_id": APP,
        "unmonitored": True,
    }
    (tmp_path / "inputs.auto.tfvars.json").write_text(
        json.dumps(baseline), encoding="utf-8"
    )
    cases = _terraform_cases()
    blocks = []
    for index, (overrides, failure) in enumerate(cases):
        # JSON scalars, lists and null are valid HCL expressions.
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
