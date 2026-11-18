"""Offline Azure API Management evidence from installed tools; never a deployment."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Final
from xml.etree import ElementTree as ET

import pytest
from tests.integration.delivery.infra import iac

if TYPE_CHECKING:
    from collections.abc import Mapping
    import subprocess

pytestmark = pytest.mark.integration
SOURCE: Final[Path] = (
    Path(__file__).resolve().parents[4] / "packages/delivery/infra/api-management"
)
# The pinned AzAPI provider starts slowly; one mocked test run can take minutes.
TIMEOUT_SECONDS: Final[int] = 900
NAME_LENGTH: Final[tuple[int, int]] = (1, 50)
TENANT: Final[str] = "00000000-0000-0000-0000-000000000000"
AUDIENCE: Final[str] = "api://sample-backend"
BACKEND: Final[str] = "https://sample-app.example.com"
RESOURCE_GROUP: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
)
WORKSPACE: Final[str] = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
    "/providers/Microsoft.OperationalInsights/workspaces/example"
)
METRICS_PUBLISHER_ROLE: Final[str] = "3913510d-42f4-4e42-8a64-420c390055eb"
MESSAGES: Final[dict[str, str]] = {
    "backend_url": "backendUrl must be an https:// URL.",
    "token_pair": "entraTenantId and entraAudience must be set together.",
    "prod_token": (
        "Staging and production require entraTenantId and entraAudience: callers "
        "must present an Entra token."
    ),
    "llm_insights": (
        "llmTokensPerMinute needs applicationInsightsName to publish token metrics."
    ),
    "prod_workspace": (
        "Staging and production require logAnalyticsWorkspaceId: an existing Log "
        "Analytics workspace for gateway logs."
    ),
    "token_empty": "entraTenantId and entraAudience must be omitted or non-empty.",
    "insights_empty": "applicationInsightsName must be omitted or non-empty.",
    "workspace_empty": "logAnalyticsWorkspaceId must be omitted or non-empty.",
}
# Platform and policy defaults that must never be restated.
RESTATED_DEFAULTS: Final[tuple[str, ...]] = (
    "publicNetworkAccess",
    "virtualNetworkType",
    "disableGateway",
    "apiType",
    "format:",
    "format =",
    "isBuffered",
    "retry-after-header-name",
    "failed-validation-httpcode",
    "header-name=",
)
_UrlCase = tuple[str, str | None]
# None omits an optional input; an empty string is a supplied value and is rejected.
_TokenCase = tuple[str, str | None, str | None, str | None]
_InsightsCase = tuple[int, str | None, str | None]
_WorkspaceCase = tuple[str, str | None, str | None]
# Shared positive/negative tables drive both the Bicep and Terraform guards.
BACKEND_CASES: Final[tuple[_UrlCase, ...]] = (
    (BACKEND, None),
    ("https://sample-app.example.com/api", None),
    ("http://sample-app.example.com", "backend_url"),
    ("HTTPS://sample-app.example.com", "backend_url"),
    ("https://", "backend_url"),
    ("", "backend_url"),
)
TOKEN_CASES: Final[tuple[_TokenCase, ...]] = (
    ("dev", None, None, None),
    ("test", TENANT, AUDIENCE, None),
    ("prod", TENANT, AUDIENCE, None),
    ("dev", TENANT, None, "token_pair"),
    ("prod", None, AUDIENCE, "token_pair"),
    ("prod", None, None, "prod_token"),
    ("staging", TENANT, AUDIENCE, None),
    ("staging", None, None, "prod_token"),
    ("dev", "", "", "token_empty"),
    ("dev", "", AUDIENCE, "token_empty"),
    ("prod", TENANT, "", "token_empty"),
)
INSIGHTS_CASES: Final[tuple[_InsightsCase, ...]] = (
    (0, None, None),
    (0, "sample-insights", None),
    (1000, "sample-insights", None),
    (1000, None, "llm_insights"),
    (0, "", "insights_empty"),
    (1000, "", "insights_empty"),
)
# The Terraform variable whose validation reports each insights error.
INSIGHTS_VARIABLES: Final[dict[str, str]] = {
    "llm_insights": "llm_tokens_per_minute",
    "insights_empty": "application_insights_name",
}
WORKSPACE_CASES: Final[tuple[_WorkspaceCase, ...]] = (
    ("dev", None, None),
    ("test", WORKSPACE, None),
    ("prod", WORKSPACE, None),
    ("prod", None, "prod_workspace"),
    ("staging", WORKSPACE, None),
    ("staging", None, "prod_workspace"),
    ("dev", "", "workspace_empty"),
    ("prod", "", "workspace_empty"),
)
_GUARDED_STAGES = ("staging", "prod")
# Bicep enforces these with native decorators; Terraform with validation blocks.
NATIVE_TERRAFORM_CASES: Final[tuple[tuple[dict[str, object], str | None], ...]] = (
    ({"name": "a" * NAME_LENGTH[0]}, None),
    ({"name": "a" * NAME_LENGTH[1]}, None),
    ({"name": ""}, "name"),
    ({"name": "a" * (NAME_LENGTH[1] + 1)}, "name"),
    ({"stage": "production"}, "stage"),
    ({"location": " "}, "location"),
    ({"resource_group_id": "example"}, "resource_group_id"),
    ({"publisher_email": ""}, "publisher_email"),
    ({"requests_per_minute": 0}, "requests_per_minute"),
    ({"requests_per_minute": 1.5}, "requests_per_minute"),
    ({"llm_tokens_per_minute": -1}, "llm_tokens_per_minute"),
)


def _run(name: str, workdir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return iac.run(name, workdir, *arguments, timeout=TIMEOUT_SECONDS)


def _policy(name: str) -> str:
    return (SOURCE / "policies" / name).read_text(encoding="utf-8")


def _xml(text: str) -> ET.Element:
    return ET.fromstring(text)  # noqa: S314 - repository files, not input


def _render_policy(*, tenant: str | None, tokens_per_minute: int) -> str:
    """Mirror the replace() chain that both sources apply to the policy files."""
    validation = (
        _policy("validate-token.xml")
        .replace("{tenant-id}", tenant)
        .replace("{audience}", AUDIENCE)
        if tenant is not None
        else ""
    )
    tokens = (
        _policy("llm-tokens.xml").replace("{tokens-per-minute}", str(tokens_per_minute))
        if tokens_per_minute
        else ""
    )
    return (
        _policy("api.xml")
        .replace("<!-- validate-token -->", validation.strip())
        .replace("<!-- llm-tokens -->", tokens.strip())
        .replace("{requests-per-minute}", "120")
    )


def _bicep_string(value: str | None) -> str:
    return "null" if value is None else f"'{value}'"


def _bicep_cases() -> list[tuple[str, str | None]]:
    return [
        *((f"requireBackendUrl('{url}')", error) for url, error in BACKEND_CASES),
        *(
            (
                (
                    f"requireTokenValidation('{stage}', {_bicep_string(tenant)}, "
                    f"{_bicep_string(audience)})"
                ),
                error,
            )
            for stage, tenant, audience, error in TOKEN_CASES
        ),
        *(
            (f"requireApplicationInsights({tokens}, {_bicep_string(name)})", error)
            for tokens, name, error in INSIGHTS_CASES
        ),
        *(
            (f"requireWorkspace('{stage}', {_bicep_string(workspace)})", error)
            for stage, workspace, error in WORKSPACE_CASES
        ),
    ]


def _terraform_cases() -> list[tuple[Mapping[str, object], str | None]]:
    # Production cases add the other production inputs so only one guard fails.
    token = {"entra_tenant_id": TENANT, "entra_audience": AUDIENCE}
    diagnostics = {"log_analytics_workspace_id": WORKSPACE}
    return [
        *(
            ({"backend_url": url}, error and "backend_url")
            for url, error in BACKEND_CASES
        ),
        *(
            (
                {"stage": stage, "entra_tenant_id": tenant, "entra_audience": audience}
                | (diagnostics if stage in _GUARDED_STAGES else {}),
                error and "entra_tenant_id",
            )
            for stage, tenant, audience, error in TOKEN_CASES
        ),
        *(
            (
                {"llm_tokens_per_minute": tokens, "application_insights_name": name},
                error and INSIGHTS_VARIABLES[error],
            )
            for tokens, name, error in INSIGHTS_CASES
        ),
        *(
            (
                {"stage": stage, "log_analytics_workspace_id": workspace}
                | (token if stage in _GUARDED_STAGES else {}),
                error and "log_analytics_workspace_id",
            )
            for stage, workspace, error in WORKSPACE_CASES
        ),
        *NATIVE_TERRAFORM_CASES,
    ]


@pytest.fixture
def relocated(tmp_path: Path) -> Path:
    """Copy only this composition elsewhere and prove the copy is byte-identical."""
    return iac.relocate(SOURCE, tmp_path / "consumer/api-management")


def test_sources_are_self_contained_and_never_expose_secrets(relocated: Path) -> None:
    bicep, terraform = iac.self_contained_sources(relocated, MESSAGES)
    policies = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "policies").glob("*.xml"))
    )
    for forbidden in ("listKeys", "listSecrets", "@secure", "subscriptionKey"):
        assert forbidden not in bicep + terraform, forbidden
    for name in RESTATED_DEFAULTS:
        assert name not in bicep + terraform + policies, (
            f"{name} restates a platform default"
        )
    declared = iac.shared_resource_types(bicep, terraform)
    assert len(declared) == 10
    assert "Microsoft.ApiManagement/service@2024-05-01" in declared
    # Both sources load the same policy files rather than embedding copies.
    for name in ("api.xml", "validate-token.xml", "llm-tokens.xml"):
        assert f"../policies/{name}" in bicep, name
        assert f"/../policies/{name}" in terraform, name


def test_policy_files_render_well_formed_and_ordered() -> None:
    _xml(_policy("api.xml"))
    _xml(_policy("validate-token.xml"))
    # The AI fragment holds two sibling policies, so parse it inside a wrapper.
    _xml(f"<fragment>{_policy('llm-tokens.xml')}</fragment>")

    def inbound(rendered: str) -> list[ET.Element]:
        assert not re.search(r"\{[a-z-]+\}", rendered), rendered
        root = _xml(rendered)
        assert [section.tag for section in root] == [
            "inbound",
            "backend",
            "outbound",
            "on-error",
        ]
        section = root.find("inbound")
        assert section is not None
        return list(section)

    minimal = inbound(_render_policy(tenant=None, tokens_per_minute=0))
    assert [element.tag for element in minimal] == ["base", "rate-limit-by-key"]
    full = inbound(_render_policy(tenant=TENANT, tokens_per_minute=5000))
    # Token validation runs first, so anonymous calls never consume a budget.
    assert [element.tag for element in full] == [
        "base",
        "validate-azure-ad-token",
        "rate-limit-by-key",
        "llm-token-limit",
        "llm-emit-token-metric",
    ]
    validation, limit, tokens = full[1], full[2], full[3]
    assert validation.attrib == {
        "tenant-id": TENANT,
        "output-token-variable-name": "caller",
    }
    assert [audience.text for audience in validation.iter("audience")] == [AUDIENCE]
    assert limit.attrib["calls"] == "120"
    assert limit.attrib["renewal-period"] == "60"
    assert tokens.attrib["tokens-per-minute"] == "5000"
    # One caller key: the validated token subject, else the client IP.
    key = limit.attrib["counter-key"]
    assert key == tokens.attrib["counter-key"]
    assert 'context.Variables["caller"]' in key
    assert key.endswith(": context.Request.IpAddress)")


def test_bicep_format_lint_build_and_examples(relocated: Path) -> None:
    folder = relocated / "bicep"
    iac.assert_bicep_clean(folder, _run)
    template = json.loads(iac.build_bicep(folder, _run))
    # loadTextContent inlines the shared policy files unchanged.
    loaded = {
        str(value).replace("\r\n", "\n")
        for name, value in template["variables"].items()
        if name.startswith("$fxv#")
    }
    assert loaded == {
        _policy(name).replace("\r\n", "\n")
        for name in ("api.xml", "validate-token.xml", "llm-tokens.xml")
    }
    assert set(template["outputs"]) == {
        "apiManagementResourceId",
        "gatewayUrl",
        "principalId",
    }
    parameters = template["parameters"]
    for required in ("location", "name", "stage", "publisherEmail", "backendUrl"):
        assert "defaultValue" not in parameters[required]
    # The same limits as the Terraform validation blocks.
    assert (parameters["name"]["minLength"], parameters["name"]["maxLength"]) == (
        NAME_LENGTH
    )
    assert parameters["stage"]["allowedValues"] == ["dev", "test", "staging", "prod"]
    assert parameters["requestsPerMinute"]["defaultValue"] == 120
    assert parameters["requestsPerMinute"]["minValue"] == 1
    assert parameters["llmTokensPerMinute"]["defaultValue"] == 0
    assert parameters["llmTokensPerMinute"]["minValue"] == 0
    # Omitted means off; an empty string is rejected, never "absent".
    for optional in (
        "entraTenantId",
        "entraAudience",
        "applicationInsightsName",
        "logAnalyticsWorkspaceId",
    ):
        assert parameters[optional]["nullable"] is True, optional
        assert parameters[optional]["minLength"] == 1, optional
        assert "defaultValue" not in parameters[optional], optional
    # Guards stay in the template, so a direct deployment fails ARM validation too.
    assert iac.guarded(template["variables"]) == {
        "serviceUrl",
        "tenantId",
        "insightsName",
        "workspaceId",
    }
    iac.build_examples(folder, _run)


def test_bicep_template_applies_stage_rules(relocated: Path) -> None:
    template = json.loads(iac.build_bicep(relocated / "bicep", _run))
    resources = template["resources"]
    by_type = {resource["type"]: resource for resource in resources.values()}
    assert len(resources) == len(by_type) == 10
    service = by_type["Microsoft.ApiManagement/service"]
    assert service["apiVersion"] == "2024-05-01"
    assert service["sku"] == {
        "name": "[if(equals(parameters('stage'), 'prod'), 'StandardV2', 'BasicV2')]",
        "capacity": 1,
    }
    assert service["identity"] == {"type": "SystemAssigned"}
    api = by_type["Microsoft.ApiManagement/service/apis"]
    assert api["properties"] == {
        "displayName": "Backend",
        "path": "",
        "serviceUrl": "[variables('serviceUrl')]",
        "protocols": ["https"],
        "subscriptionRequired": False,
    }
    operations = by_type["Microsoft.ApiManagement/service/apis/operations"]
    assert operations["properties"]["urlTemplate"] == "/*"
    assert "'GET', 'POST', 'PUT', 'PATCH', 'DELETE'" in operations["copy"]["count"]
    insights = by_type["Microsoft.Insights/components"]
    assert insights["existing"] is True
    role = by_type["Microsoft.Authorization/roleAssignments"]
    assert role["properties"]["principalType"] == "ServicePrincipal"
    assert template["variables"]["metricsPublisherRoleId"] == METRICS_PUBLISHER_ROLE
    logger = by_type["Microsoft.ApiManagement/service/loggers"]
    assert logger["properties"]["credentials"]["identityClientId"] == "SystemAssigned"
    telemetry = by_type["Microsoft.ApiManagement/service/diagnostics"]
    assert telemetry["properties"]["metrics"] is True
    for optional in (insights, role, logger, telemetry):
        assert optional["condition"] == (
            "[not(equals(variables('insightsName'), null()))]"
        )
    # ARM evaluates names of skipped resources; the placeholder is never deployed.
    assert insights["name"] == "[coalesce(variables('insightsName'), '')]"
    # The token fragment is only rendered when a tenant is supplied.
    assert template["variables"]["tokenValidation"].startswith(
        "[if(equals(variables('tenantId'), null()), '', "
    )
    diagnostics = by_type["Microsoft.Insights/diagnosticSettings"]
    assert diagnostics["condition"] == (
        "[not(equals(variables('workspaceId'), null()))]"
    )
    assert diagnostics["properties"] == {
        "workspaceId": "[variables('workspaceId')]",
        "logAnalyticsDestinationType": "Dedicated",
        "logs": [{"category": "GatewayLogs", "enabled": True}],
    }
    lock = by_type["Microsoft.Authorization/locks"]
    assert lock["properties"] == {"level": "CanNotDelete"}
    assert "scope" in lock
    assert lock["condition"] == "[equals(parameters('stage'), 'prod')]"


@pytest.mark.parametrize(
    ("pattern", "replacement", "error"),
    [
        (r"requireBackendUrl\('https://", "requireBackendUrl('http://", "backend_url"),
        (rf"'{TENANT}', entraAudience\)", "null, null)", "prod_token"),
        (rf"'{TENANT}', entraAudience\)", "null, entraAudience)", "token_pair"),
        (rf"'{TENANT}', entraAudience\)", "'', entraAudience)", "token_empty"),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, null)",
            "prod_workspace",
        ),
        (
            r"requireWorkspace\(\s*stage,\s*'[^']*'\s*\)",
            "requireWorkspace(stage, '')",
            "workspace_empty",
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
        "requireBackendUrl",
        "requireTokenValidation",
        "requireApplicationInsights",
        "requireWorkspace",
    )
    iac.assert_bicep_guards(
        relocated / "bicep", _run, imports, _bicep_cases(), MESSAGES
    )


def test_terraform_sources_are_canonically_formatted(relocated: Path) -> None:
    iac.ok(_run("terraform", relocated / "terraform", "fmt", "-check", "-recursive"))


def test_terraform_variable_contract_without_provider(tmp_path: Path) -> None:
    baseline = {
        "resource_group_id": RESOURCE_GROUP,
        "location": "westeurope",
        "name": "sample-apim-dev",
        "stage": "dev",
        "publisher_email": "platform@example.com",
        "backend_url": BACKEND,
    }
    variables = SOURCE / "terraform/variables.tf"
    cases = _terraform_cases()
    iac.assert_variable_contract(tmp_path, variables, _run, baseline, cases)


def test_terraform_full_validation_and_mock_plans(relocated: Path) -> None:
    folder = relocated / "terraform"
    iac.init_from_mirror(folder, _run)
    iac.mock_plans(folder, _run)
