"""Offline Application Insights evidence from installed tools; never a deployment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final
import uuid

import pytest
from tests.integration.delivery.infra import iac

if TYPE_CHECKING:
    from collections.abc import Mapping
    import subprocess

pytestmark = pytest.mark.integration
SOURCE: Final[Path] = (
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/application-insights"
)
TIMEOUT_SECONDS: Final[int] = 300
PRINCIPAL: Final[str] = "00000000-0000-0000-0000-000000000000"
GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
)
WORKSPACE: Final[str] = (
    f"{GROUP}/providers/Microsoft.OperationalInsights/workspaces/example"
)
PUBLISHER_ROLE: Final[str] = "3913510d-42f4-4e42-8a64-420c390055eb"
# ARM guid() is UUIDv5 over its '-'-joined arguments in this namespace.
ARM_GUID_NAMESPACE: Final[uuid.UUID] = uuid.UUID("11fb06fb-712d-4ddd-98c7-e71bbd588830")
COMPONENT: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
    "/providers/Microsoft.Insights/components/sample-dev"
)
MESSAGES: Final[dict[str, str]] = {
    "workspace": "logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID.",
    "principal": (
        "principalId must be the object (principal) ID GUID of the existing app "
        "identity."
    ),
}
# Platform defaults that the sources must never restate.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "Flow_Type",
    "Request_Source",
    "IngestionMode",
    "publicNetworkAccessForIngestion",
    "publicNetworkAccessForQuery",
    "RetentionInDays",
    "SamplingPercentage",
    "DisableIpMasking",
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
PRINCIPAL_CASES: Final[tuple[_Case, ...]] = (
    (PRINCIPAL, None),
    ("A1B2C3D4-0000-4000-8000-00000000000F", None),
    ("", "principal"),
    ("not-a-guid", "principal"),
    ("00000000000000000000000000000000", "principal"),
    (
        f"{GROUP}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/app",
        "principal",
    ),
)


def _run(name: str, workdir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return iac.run(name, workdir, *arguments, timeout=TIMEOUT_SECONDS)


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *(
            (f"requireWorkspaceId('{value}')", error)
            for value, error in WORKSPACE_CASES
        ),
        *(
            (f"requirePrincipalId('{value}')", error)
            for value, error in PRINCIPAL_CASES
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
            ({"principal_id": value}, error and "principal_id")
            for value, error in PRINCIPAL_CASES
        ),
        ({"stage": "test"}, None),
        ({"stage": "staging"}, None),
        ({"stage": "prod"}, None),
        ({"stage": "production"}, "stage"),
        ({"location": ""}, "location"),
        ({"name": ""}, "name"),
        ({"resource_group_id": "example"}, "resource_group_id"),
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/application-insights")


def test_sources_are_self_contained_and_never_restate_defaults(
    relocated: Path,
) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    for forbidden in ("listKeys", "listSecrets", "Microsoft.Authorization/locks"):
        assert forbidden not in bicep + terraform
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform, f"{name} restates a platform default"
    assert iac.shared_resource_types(bicep, terraform) == {
        "Microsoft.Insights/components@2020-02-02",
        "Microsoft.Authorization/roleAssignments@2022-04-01",
    }


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    template = json.loads(iac.build_bicep(folder, _run))
    resources = template["resources"]
    assert set(resources) == {"component", "publisher"}
    component = resources["component"]
    assert component["kind"] == "web"
    assert component["properties"] == {
        "Application_Type": "web",
        "WorkspaceResourceId": "[variables('workspaceId')]",
        "DisableLocalAuth": "[not(equals(parameters('stage'), 'dev'))]",
    }
    publisher = resources["publisher"]["properties"]
    assert publisher["principalType"] == "ServicePrincipal"
    assert PUBLISHER_ROLE in json.dumps(template["variables"])
    assert "roleDefinitions" in publisher["roleDefinitionId"]
    assert set(template["outputs"]) == {
        "applicationInsightsResourceId",
        "connectionString",
    }
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "logAnalyticsWorkspaceId"):
        assert "defaultValue" not in parameters[required]
    assert "defaultValue" not in parameters["principalId"]
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(template["variables"]) == {"workspaceId", "objectId"}
    iac.build_examples(folder, _run)


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        ("OperationalInsights", "Insights", "workspace"),
        (
            r"requirePrincipalId\('[^']*'\)",
            "requirePrincipalId('not-a-guid')",
            "principal",
        ),
    ],
)
def test_bicep_production_example_rejects_unsafe_values(
    relocated: Path, pattern: str, replacement: str, error: str
) -> None:
    example = relocated / "bicep/tests/prod.bicepparam"
    stderr = iac.rejected_example(example, _run, pattern, replacement)
    assert MESSAGES[error] in stderr, stderr


def test_bicep_guards_accept_and_reject_shared_cases(relocated: Path) -> None:
    imports = ("requirePrincipalId", "requireWorkspaceId")
    expected_name = uuid.uuid5(
        ARM_GUID_NAMESPACE, f"{COMPONENT}-{PRINCIPAL}-{PUBLISHER_ROLE}"
    )
    rendered = iac.assert_bicep_guards(
        relocated / "bicep",
        _run,
        imports,
        _bicep_cases(),
        MESSAGES,
        # Terraform's uuidv5() name (asserted in its mocked plan) equals Bicep guid().
        extra=f"param roleName = guid('{COMPONENT}', '{PRINCIPAL}', '{PUBLISHER_ROLE}')\n",
    )
    values = json.loads(json.loads(rendered)["parametersJson"])["parameters"]
    assert values["roleName"]["value"] == str(expected_name)
    tftest = (SOURCE / "terraform/tests/application-insights.tftest.hcl").read_text(
        encoding="utf-8"
    )
    assert f'"{expected_name}"' in tftest


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": GROUP,
        "location": "westeurope",
        "name": "sample-dev",
        "stage": "dev",
        "log_analytics_workspace_id": WORKSPACE,
        "principal_id": PRINCIPAL,
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run)
    iac.mock_plans(folder, _run)
