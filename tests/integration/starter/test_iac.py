"""Offline starter composition proof; no checkout mutation, installation or Azure."""

import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess

from copier import run_copy
import pytest

_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = os.environ.get(
    "STARTER_KIT_COMMIT", "1234567890abcdef1234567890abcdef12345678"
)
_MODULES = (
    "container-apps",
    "container-apps-alerts",
    "network",
    # The default registry answer with cloud IaC is a stack-owned ACR.
    "container-registry",
)
_TIMEOUT = 120


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("iac-template")
    shutil.copyfile(_ROOT / "copier.yml", directory / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", directory / "packages/starter/template"
    )
    return directory


def _render(
    source: Path,
    destination: Path,
    iac: str,
    service: str = "api",
    telemetry: str = "none",
) -> Path:
    cached = source.parent / f"{source.name}-{service}-{iac}-{telemetry}"
    if not cached.exists():
        run_copy(
            str(source),
            cached,
            data={
                "project_name": "sample",
                "service": service,
                "iac": iac,
                "kit_commit": _COMMIT,
                "telemetry": telemetry,
            },
            defaults=True,
            quiet=True,
        )
    shutil.copytree(cached, destination)
    return destination


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
@pytest.mark.parametrize("telemetry", ["none", "application-insights"])
def test_one_workspace_and_explicit_telemetry(
    source: Path, tmp_path: Path, iac: str, telemetry: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac, telemetry=telemetry)
    main = (root / f"infra/main.{'bicep' if iac == 'bicep' else 'tf'}").read_text()
    enabled = telemetry == "application-insights"
    # Toolchain-free structure check: optional blocks must not strand a brace.
    assert main.count("{") == main.count("}")
    assert ("application-insights/" in main) is enabled
    assert ("insights.outputs.connectionString" in main) is (enabled and iac == "bicep")
    assert ("module.insights.connection_string" in main) is (
        enabled and iac == "terraform"
    )
    if iac == "bicep":
        assert ("output runtimeIdentityClientId " in main) is enabled
        assert "existingLogAnalyticsWorkspaceResourceId: telemetry.id" in main
        assert "name: '${namePrefix}-telemetry'" in main
        assert "deployApp && alerts" not in main
        assert "unmonitored: alertsUnmonitored" in main
        vendor = (root / "scripts/vendor_bicep.py").read_text()
        assert ('"application-insights"' in vendor) is enabled
    else:
        assert ('output "runtime_identity_client_id"' in main) is enabled
        assert re.search(
            r"existing_log_analytics_workspace_resource_id\s*=\s*local.telemetry_workspace_id",
            main,
        )
        assert 'name      = "${var.name_prefix}-telemetry"' in main
        assert "!var.alerts_unmonitored" not in main
        assert re.search(r"unmonitored\s*=\s*var.alerts_unmonitored", main)


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    fallback = Path.home() / ".azure/bin/bicep.exe"
    if name == "bicep" and fallback.is_file():
        return str(fallback)
    pytest.skip(f"Installed {name} unavailable; no installation attempted")


def _run(name: str, cwd: Path, *args: str, timeout: int = _TIMEOUT) -> str:
    result = subprocess.run(  # noqa: S603 - installed tools, offline fixed arguments
        [_tool(name), *args],
        cwd=cwd,
        env={
            **os.environ,
            "CHECKPOINT_DISABLE": "1",
            "TF_IN_AUTOMATION": "1",
            "TF_DATA_DIR": str(cwd / ".terraform"),
            "ARM_ENABLE_PREFLIGHT": "false",
            "ARM_SKIP_PROVIDER_REGISTRATION": "true",
        },
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.parametrize(
    ("service", "iac"), [("api", "none"), ("none", "bicep"), ("none", "terraform")]
)
def test_no_cloud_scaffold_without_both_opt_ins(
    source: Path, tmp_path: Path, service: str, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac, service)
    assert not (root / "infra").exists()
    assert not (root / "scripts/vendor_bicep.py").exists()
    assert not (root / ".github/workflows/deploy.yml").exists()


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_selected_iac_is_a_real_pinned_foundation(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac)
    extension = "bicep" if iac == "bicep" else "tf"
    main = (root / f"infra/main.{extension}").read_text(encoding="utf-8")
    for module in _MODULES:
        assert module in main
    assert "teamsWebhookUrl" not in main
    assert "teams_webhook_url" not in main
    assert not list(root.rglob("*.tfstate*"))
    if iac == "terraform":
        assert main.count(f"?ref={_COMMIT}") == len(_MODULES)
        assert 'backend "azurerm" {}' in (root / "infra/versions.tf").read_text()
        assert 'version = "= 2.13.0"' in (root / "infra/versions.tf").read_text()
        assert not (root / "scripts/vendor_bicep.py").exists()
    else:
        assert not (root / "infra/vendor").exists()
        assert _COMMIT in (root / "scripts/vendor_bicep.py").read_text()
    # Default ACR: the app pulls from the stack-owned registry by managed identity.
    assert re.search(
        r"registryServer: registry\.outputs\.loginServer"
        if iac == "bicep"
        else r'registry_server\s+= "\$\{var\.registry_name\}\.azurecr\.io"',
        main,
    )


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_ghcr_registry_keeps_public_image_without_acr(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = tmp_path / "consumer"
    run_copy(
        str(source),
        root,
        data={
            "project_name": "sample",
            "service": "api",
            "iac": iac,
            "registry": "ghcr",
            "kit_commit": _COMMIT,
        },
        defaults=True,
        quiet=True,
    )
    main = (root / f"infra/main.{'bicep' if iac == 'bicep' else 'tf'}").read_text()
    params = (
        root / f"infra/dev.{'bicepparam' if iac == 'bicep' else 'tfvars'}"
    ).read_text()
    for text in (main, params):
        assert "container-registry" not in text
        assert "registry" not in text.lower()
    assert (
        "registry-bootstrap" not in (root / ".github/workflows/deploy.yml").read_text()
    )
    if iac == "terraform":
        _run("terraform", root / "infra", "fmt", "-check", "-recursive", "-diff")
    else:
        assert (
            "container-registry" not in (root / "scripts/vendor_bicep.py").read_text()
        )


def _fixture_vendor(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate read-only Git object responses, not a released toolkit commit."""
    namespace = runpy.run_path(str(root / "scripts/vendor_bicep.py"))
    calls: list[tuple[str, ...]] = []

    def git(checkout: Path, *args: str) -> bytes:
        calls.append(args)
        if args == ("rev-parse", "--verify", "HEAD"):
            return f"{_COMMIT}\n".encode()
        assert args[0:2] == ("cat-file", "blob")
        revision, relative = args[-1].split(":", 1)
        assert revision == _COMMIT
        return (_ROOT / relative).read_bytes()

    monkeypatch.setitem(namespace["read_sources"].__globals__, "_git", git)
    contents = namespace["read_sources"](root / "unused-checkout")
    vendor = root / "infra/vendor"
    namespace["write_vendor"](vendor, contents)
    assert calls[0] == ("rev-parse", "--verify", "HEAD")
    # A module split must extend the vendored closure, or consumer builds break.
    manifest = json.loads((vendor / "manifest.json").read_text())
    for module in {Path(relative).parts[0] for relative in manifest["sources"]}:
        if (vendor / module).is_dir():
            sources = _ROOT / f"packages/delivery/infra/{module}/bicep"
            expected = {path.name for path in sources.iterdir() if path.is_file()}
            assert {path.name for path in (vendor / module).iterdir()} == expected


def test_vendor_uses_only_commit_objects_and_detects_tampering(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    _fixture_vendor(root, monkeypatch)
    namespace = runpy.run_path(str(root / "scripts/vendor_bicep.py"))
    vendor = root / "infra/vendor"
    namespace["check_vendor"](vendor)
    manifest = json.loads((vendor / "manifest.json").read_text())
    assert manifest["commit"] == _COMMIT
    assert manifest["repository"] == "https://github.com/lfr-ai/agent-kit"
    assert "MIT License" in (vendor / "LICENSE").read_text()
    for relative, digest in manifest["sha256"].items():
        assert hashlib.sha256((vendor / relative).read_bytes()).hexdigest() == digest
    with pytest.raises(ValueError, match="already exists"):
        namespace["write_vendor"](vendor, {})
    (vendor / "container-apps/main.bicep").write_text("dirty", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        namespace["check_vendor"](vendor)


def test_vendor_rejects_checkout_at_another_commit(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    namespace = runpy.run_path(str(root / "scripts/vendor_bicep.py"))
    monkeypatch.setitem(
        namespace["read_sources"].__globals__, "_git", lambda *_: b"f" * 40
    )
    with pytest.raises(ValueError, match="kit_commit"):
        namespace["read_sources"](tmp_path)
    assert not (root / "infra/vendor").exists()


@pytest.mark.parametrize("telemetry", ["none", "application-insights"])
def test_relocated_bicep_formats_lints_and_compiles_without_restore(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    telemetry: str,
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep", telemetry=telemetry)
    _fixture_vendor(root, monkeypatch)
    relocated = tmp_path / "unrelated" / "infra"
    shutil.copytree(root / "infra", relocated)
    for path in [relocated / "main.bicep", relocated / "dev.bicepparam"]:
        assert _run("bicep", relocated, "format", str(path), "--stdout") == (
            path.read_text(encoding="utf-8")
        )
    _run("bicep", relocated, "lint", "main.bicep", "--no-restore")
    compiled = json.loads(
        _run("bicep", relocated, "build", "main.bicep", "--no-restore", "--stdout")
    )
    resources = compiled["resources"]
    # Modules plus the runtime identity, telemetry workspace and its prod-like lock.
    enabled = telemetry == "application-insights"
    assert len(resources) == len(_MODULES) + 3 + int(enabled)
    assert resources["runtimeIdentity"]["type"] == (
        "Microsoft.ManagedIdentity/userAssignedIdentities"
    )
    assert resources["telemetry"]["type"] == "Microsoft.OperationalInsights/workspaces"
    assert resources["telemetryLock"]["type"] == "Microsoft.Authorization/locks"
    foundation = resources["foundation"]
    identity = foundation["properties"]["parameters"]["existingIdentityResourceId"]
    assert "Microsoft.ManagedIdentity/userAssignedIdentities" in identity["value"]
    assert "runtimeIdentity" in foundation["dependsOn"]
    assert ("insights" in resources) is enabled
    if enabled:
        assert "telemetry" in resources["insights"]["dependsOn"]
    assert "telemetry" in foundation["dependsOn"]
    workspace = foundation["properties"]["parameters"][
        "existingLogAnalyticsWorkspaceResourceId"
    ]
    assert "telemetry" in workspace["value"]
    notifications = resources["notifications"]
    assert notifications["condition"] == "[variables('deployApp')]"
    assert notifications["properties"]["parameters"]["unmonitored"]["value"] == (
        "[parameters('alertsUnmonitored')]"
    )
    assert "REPLACE_" not in (relocated / "dev.bicepparam").read_text()
    _run(
        "bicep", relocated, "build-params", "dev.bicepparam", "--no-restore", "--stdout"
    )


@pytest.mark.parametrize("telemetry", ["none", "application-insights"])
def test_terraform_sources_are_canonically_formatted(
    source: Path, tmp_path: Path, telemetry: str
) -> None:
    root = (
        _render(source, tmp_path / "consumer", "terraform", telemetry=telemetry)
        / "infra"
    )
    _run("terraform", root, "fmt", "-check", "-recursive", "-diff")


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_starter_exposes_environment_secrets_and_existing_action_group(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac) / "infra"
    if iac == "bicep":
        main = (root / "main.bicep").read_text()
        params = (root / "dev.bicepparam").read_text()
        for field in ("environmentVariables", "secretReferences"):
            assert f"param {field} = " in params
        assert "environmentVariables: appEnvironment" in main
        assert "secretReferences: secretReferences" in main
        assert re.search(r"requireUserEnvironment\(\s*environmentVariables,", main)
        assert "existingActionGroupResourceId: alertActionGroupResourceId" in main
        assert "param alertActionGroupResourceId = ''" in params
    else:
        main = (root / "main.tf").read_text()
        params = (root / "dev.tfvars").read_text()
        for field in ("environment_variables", "secret_references"):
            assert re.search(rf"{field}\s*=", params)
        assert re.search(r"environment_variables\s*=\s*local.app_environment", main)
        assert re.search(r"secret_references\s*=\s*var.secret_references", main)
        assert re.search(
            r"existing_action_group_resource_id\s*=\s*var.alert_action_group_resource_id",
            main,
        )
        assert re.search(r'alert_action_group_resource_id\s*=\s*""', params)


@pytest.mark.parametrize("stage", ["staging", "prod"])
def test_starter_accepts_teams_through_existing_action_group(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    _fixture_vendor(root, monkeypatch)
    group = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts/providers/Microsoft.Insights/actionGroups/operations"
    (root / "infra/teams.bicepparam").write_text(
        "using none\nimport { requireAlerts } from './main.bicep'\n"
        f"param enabled = requireAlerts('{stage}', [], '{group}', false)\n",
        encoding="utf-8",
    )
    output = _run(
        "bicep",
        root / "infra",
        "build-params",
        "teams.bicepparam",
        "--no-restore",
        "--stdout",
    )
    parameters = json.loads(json.loads(output)["parametersJson"])["parameters"]
    assert parameters["enabled"]["value"] is True
    assert "webhook" not in output.lower()


def test_starter_compiled_root_forwards_runtime_settings_unchanged(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    _fixture_vendor(root, monkeypatch)
    template = json.loads(
        _run("bicep", root / "infra", "build", "main.bicep", "--no-restore", "--stdout")
    )
    parameters = template["resources"]["foundation"]["properties"]["parameters"]
    assert parameters["secretReferences"]["value"] == "[parameters('secretReferences')]"
    assert (
        parameters["environmentVariables"]["value"] == "[variables('appEnvironment')]"
    )
    assert "requireUserEnvironment" in str(template["variables"]["userEnvironment"])
    alerts = template["resources"]["notifications"]["properties"]["parameters"]
    assert alerts["existingActionGroupResourceId"]["value"] == (
        "[parameters('alertActionGroupResourceId')]"
    )
    assert "teamsWebhookUrl" not in alerts
    assert template["parameters"]["environmentVariables"]["defaultValue"] == {}
    assert template["parameters"]["secretReferences"]["defaultValue"] == []
    # Mirrors the Terraform container_image validation: only this stack's registry.
    assert parameters["containerImage"]["value"] == "[variables('checkedImage')]"
    guard = template["variables"]["checkedImage"]
    assert ".azurecr.io/" in guard
    assert "fail(" in guard
    lock = template["resources"]["telemetryLock"]
    assert lock["condition"] == "[variables('prodLike')]"
    assert lock["properties"]["level"] == "CanNotDelete"


def test_starter_terraform_alert_destination_contract_without_provider(
    source: Path, tmp_path: Path
) -> None:
    root = _render(source, tmp_path / "consumer", "terraform") / "infra"
    isolated = tmp_path / "variables"
    isolated.mkdir()
    shutil.copyfile(root / "variables.tf", isolated / "variables.tf")
    group = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts"
    action_group = f"{group}/providers/Microsoft.Insights/actionGroups/operations"
    (isolated / "inputs.auto.tfvars.json").write_text(
        json.dumps(
            {
                "resource_group_id": group,
                "stage": "dev",
                "name_prefix": "sample-dev",
                "registry_name": "sampleacr",
                "registry_sku": "Basic",
                "container_image": "sampleacr.azurecr.io/app@sha256:" + "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    cases = [
        ("dev", True, "", [], None),
        ("test", True, "", [], None),
        ("dev", False, "", ["ops@example.com"], None),
        ("staging", False, action_group, [], None),
        ("prod", False, action_group, [], None),
        ("staging", False, "", ["ops@example.com"], None),
        ("prod", False, "", ["ops@example.com"], None),
        ("dev", False, "", [], "alerts_unmonitored"),
        ("test", False, "", [], "alerts_unmonitored"),
        ("staging", False, "", [], "alerts_unmonitored"),
        ("prod", False, "", [], "alerts_unmonitored"),
        ("staging", True, "", [], "alerts_unmonitored"),
        ("prod", True, "", [], "alerts_unmonitored"),
        ("dev", True, action_group, [], "alerts_unmonitored"),
        ("dev", False, action_group, ["ops@example.com"], "alerts_unmonitored"),
        ("dev", False, "", ["invalid"], "alert_email_receivers"),
        (
            "prod",
            False,
            "https://example.invalid/receiver",
            [],
            "alert_action_group_resource_id",
        ),
    ]
    blocks = []
    for index, (stage, unmonitored, group_id, emails, failure) in enumerate(cases):
        variables = {
            "stage": stage,
            "registry_sku": "Premium" if stage in {"staging", "prod"} else "Basic",
            "alerts_unmonitored": unmonitored,
            "alert_action_group_resource_id": group_id,
            "alert_email_receivers": emails,
        }
        assignments = "\n".join(
            f"    {key} = {json.dumps(value)}" for key, value in variables.items()
        )
        expected = f"  expect_failures = [var.{failure}]\n" if failure else ""
        blocks.append(
            f'run "case{index}" {{\n  command = plan\n  variables {{\n'
            f"{assignments}\n  }}\n{expected}}}\n"
        )
    owned_names = (
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "AZURE_CLIENT_ID",
        "OTEL_SERVICE_NAME",
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
    )
    for name in owned_names:
        for field, value in (
            ("environment_variables", {name.lower(): "override"}),
            (
                "secret_references",
                [
                    {
                        "name": "override",
                        "environment_variable": name,
                        "key_vault_url": "https://example.vault.azure.net/secrets/override",
                    }
                ],
            ),
        ):
            blocks.append(
                f'run "reject_{field}_{name.lower()}" {{\n  command = plan\n'
                "  variables {\n    alerts_unmonitored = true\n"
                f"    {field} = {json.dumps(value)}\n"
                f"  }}\n  expect_failures = [var.{field}]\n}}\n"
            )
    (isolated / "alerts.tftest.hcl").write_text("".join(blocks), encoding="utf-8")
    _run("terraform", isolated, "validate", "-json")
    output = _run("terraform", isolated, "test", "-no-color")
    assert f"Success! {len(blocks)} passed, 0 failed." in output


def test_terraform_installed_cache_validation(source: Path, tmp_path: Path) -> None:
    root = _render(source, tmp_path / "consumer", "terraform") / "infra"
    cache = os.environ.get("STARTER_TERRAFORM_CACHE")
    if not cache:
        pytest.skip(
            "validate needs STARTER_TERRAFORM_CACHE containing an "
            "already initialized .terraform directory for this generated root. "
            "No init, provider installation or module download attempted."
        )
    cache_path = Path(cache).resolve(strict=True)
    manifest = json.loads((cache_path / "modules/modules.json").read_text())
    sources = {entry["Source"] for entry in manifest["Modules"] if entry["Key"]}
    assert sources == {
        f"git::https://github.com/lfr-ai/agent-kit.git//packages/delivery/infra/{module}/terraform?ref={_COMMIT}"
        for module in _MODULES
    }
    for entry in manifest["Modules"]:
        directory = Path(entry["Dir"])
        assert not directory.is_absolute()
        assert ".." not in directory.parts
    # Copy only installed code, never backend metadata or cached state.
    for name in ("modules", "providers"):
        shutil.copytree(cache_path / name, root / ".terraform" / name)
    result = json.loads(_run("terraform", root, "validate", "-json"))
    assert result["valid"]


def test_terraform_foundation_identity_is_plannable_on_first_apply(
    source: Path, tmp_path: Path
) -> None:
    """Static guard; the mirror-gated plan below cannot prove apply ordering."""
    main = (
        _render(source, tmp_path / "consumer", "terraform") / "infra/main.tf"
    ).read_text(encoding="utf-8")
    foundation = main[
        main.index('module "foundation"') : main.index('module "notifications"')
    ]
    # An apply-time .id would make the module's identity data-source count unknown.
    assert re.search(
        r"existing_identity_resource_id\s*=\s*local\.runtime_identity_id", foundation
    )
    assert re.search(
        r"depends_on\s*=\s*\[azapi_resource\.runtime_identity\b", foundation
    )
    identity = re.search(r"^\s*runtime_identity_id\s*=\s*(.+)$", main, re.MULTILINE)
    assert identity
    assert "var.resource_group_id" in identity.group(1)
    assert "var.name_prefix" in identity.group(1)
    assert "azapi_resource.runtime_identity.id" not in identity.group(1)


_FIRST_PLAN = """
mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      location = "westeurope"
      output   = { properties = { clientId = "22222222-2222-2222-2222-222222222222" } }
    }
  }
  mock_data "azapi_client_config" {
    defaults = { object_id = "33333333-3333-3333-3333-333333333333" }
  }
}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/app"
  stage             = "dev"
  name_prefix       = "sample-dev"
  registry_name     = "sampleacr"
  registry_sku      = "Basic"
  container_image   = "sampleacr.azurecr.io/app@sha256:DIGEST"
  alerts_unmonitored = true
}

run "region_defaults_to_resource_group" {
  command = plan
  assert {
    condition     = azapi_resource.runtime_identity.location == "westeurope"
    error_message = "location must default to the resource group region"
  }
  assert {
    condition     = endswith(local.runtime_identity_id, "/userAssignedIdentities/sample-dev-identity")
    error_message = "foundation must receive the stack-owned runtime identity"
  }
}

run "explicit_region_wins" {
  command = plan
  variables {
    location = "swedencentral"
  }
  assert {
    condition     = azapi_resource.telemetry.location == "swedencentral"
    error_message = "an explicit location must override the resource group region"
  }
}
""".replace("DIGEST", "a" * 64)


def test_terraform_root_plans_first_apply_with_working_tree_modules(
    source: Path, tmp_path: Path
) -> None:
    """The stack-owned identity must not make module counts unknown on first plan."""
    root = _render(source, tmp_path / "consumer", "terraform") / "infra"
    _check_first_plans(root=root, cases=_FIRST_PLAN, expected_runs=2)


def _check_first_plans(*, root: Path, cases: str, expected_runs: int) -> None:
    mirror = os.environ.get("CONTAINER_APPS_AZAPI_MIRROR")
    if not mirror:
        pytest.skip(
            "First-apply plan needs reviewed Azure/azapi 2.13.0 in "
            "CONTAINER_APPS_AZAPI_MIRROR; no provider install attempted."
        )
    main = root / "main.tf"
    main.write_text(
        re.sub(
            r"git::https://github\.com/lfr-ai/agent-kit\.git//(\S+?)\?ref=[0-9a-f]{40}",
            lambda match: (_ROOT / match.group(1)).as_posix(),
            main.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    versions = root / "versions.tf"
    versions.write_text(
        versions.read_text(encoding="utf-8").replace('  backend "azurerm" {}\n', ""),
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests/first-plan.tftest.hcl").write_text(cases, encoding="utf-8")
    plugins = Path(mirror).resolve(strict=True)
    # -plugin-dir limits init to the operator-provisioned local mirror.
    _run(
        "terraform",
        root,
        "init",
        "-backend=false",
        "-input=false",
        f"-plugin-dir={plugins}",
    )
    assert json.loads(_run("terraform", root, "validate", "-json"))["valid"]
    output = _run("terraform", root, "test", "-no-color", timeout=600)
    assert f"Success! {expected_runs} passed, 0 failed." in output
    assert not list(root.glob("*.tfstate*"))


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_alert_opt_out_is_explicit_and_never_accepts_webhook_secrets(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac) / "infra"
    extension = "bicepparam" if iac == "bicep" else "tfvars"
    params = (root / f"dev.{extension}").read_text()
    pattern = (
        r"alertsUnmonitored\s*=\s*true"
        if iac == "bicep"
        else r"alerts_unmonitored\s*=\s*true"
    )
    assert re.search(pattern, params)
    assert "webhook" not in params.lower()
    definition = (
        root / ("main.bicep" if iac == "bicep" else "variables.tf")
    ).read_text()
    assert "email" in definition
    assert "alertTransport" not in definition
    assert "alert_transport" not in definition
    assert "unmonitored" in definition.lower()


@pytest.mark.parametrize("stage", ["staging", "prod"])
@pytest.mark.parametrize("unmonitored", ["true", "false"])
def test_native_bicep_rejects_unmonitored_production_like_stages(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    unmonitored: str,
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    _fixture_vendor(root, monkeypatch)
    directory = root / "infra"
    (directory / "invalid.bicepparam").write_text(
        "using none\nimport { requireAlerts } from './main.bicep'\n"
        f"param enabled = requireAlerts('{stage}', [], '', {unmonitored})\n",
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - installed compiler and synthetic offline parameters
        [
            _tool("bicep"),
            "build-params",
            "invalid.bicepparam",
            "--no-restore",
            "--stdout",
        ],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    assert result.returncode != 0
    assert "require emailReceivers or existingActionGroupResourceId" in result.stderr


def test_real_git_checkout_mismatch_fails_without_writing(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    namespace = runpy.run_path(str(root / "scripts/vendor_bicep.py"))
    monkeypatch.setitem(namespace["read_sources"].__globals__, "_COMMIT", "1" * 40)
    with pytest.raises(ValueError, match="kit_commit"):
        namespace["read_sources"](_ROOT)
    assert not (root / "infra/vendor").exists()


def test_real_git_blob_reader_ignores_working_tree_file_reads(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    namespace = runpy.run_path(str(root / "scripts/vendor_bicep.py"))
    commit = namespace["_git"](_ROOT, "rev-parse", "--verify", "HEAD").decode().strip()
    globals_ = namespace["read_sources"].__globals__
    monkeypatch.setitem(globals_, "_COMMIT", commit)
    # Current HEAD predates delivery: exercise real object I/O with its MIT license.
    monkeypatch.setitem(globals_, "_FILES", {"LICENSE": "LICENSE"})

    def reject_working_file(path: Path) -> bytes:
        pytest.fail(f"Vendoring must not read working-tree bytes: {path}")

    monkeypatch.setattr(Path, "read_bytes", reject_working_file)
    contents = namespace["read_sources"](_ROOT)
    assert contents["LICENSE"].startswith(b"MIT License")
