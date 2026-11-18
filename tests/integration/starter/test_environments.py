"""Offline rendered-output contracts for the starter's cloud environments."""

import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

from copier import Settings, run_copy
import pytest
from tests.integration.starter import test_iac as starter_iac
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = "1234567890abcdef1234567890abcdef12345678"
_CLOUD_STAGES = ("dev", "test", "staging", "prod")
# Premium only where the registry is private; anything else is unreachable or rejected.
_REGISTRY_SKU_MISMATCHES = (("dev", "Premium"), ("prod", "Basic"))
_TIMEOUT = 120


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
@pytest.mark.parametrize("stage", _CLOUD_STAGES)
def test_prebuild_alert_contract_is_checked_before_registry_lookup(
    source: Path, tmp_path: Path, iac: str, stage: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac)
    namespace = runpy.run_path(str(root / "scripts/validate_environment.py"))
    extension = "bicepparam" if iac == "bicep" else "tfvars"
    path = root / "infra" / f"{stage}.{extension}"
    text = (
        path.read_text()
        .replace(
            "REPLACE_WITH_RESOURCE_GROUP_ARM_ID",
            "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/app",
        )
        .replace("REPLACE_WITH_NONOVERLAPPING_CIDR", "10.44.0.0/22")
    )
    # Remove all destination fields so defaults cannot accidentally count as opt-in.
    text = re.sub(
        r"(?m)^.*(?:alertsUnmonitored|alertEmailReceivers|alertActionGroupResourceId|"
        r"alerts_unmonitored|alert_email_receivers|alert_action_group_resource_id).*\n?",
        "",
        text,
    )
    prefix = "param " if iac == "bicep" else ""
    emails, group, unmonitored = (
        ("alertEmailReceivers", "alertActionGroupResourceId", "alertsUnmonitored")
        if iac == "bicep"
        else (
            "alert_email_receivers",
            "alert_action_group_resource_id",
            "alerts_unmonitored",
        )
    )
    quote = "'" if iac == "bicep" else '"'
    invalid = (
        "",
        f"{prefix}{emails} = [{quote}invalid{quote}]\n",
        f"{prefix}{group} = {quote}https://example.invalid/receiver{quote}\n",
        (
            f"{prefix}{emails} = [{quote}ops@example.com{quote}]\n"
            f"{prefix}{unmonitored} = true\n"
        ),
        f"{prefix}{unmonitored} = false || true\n",
    )
    if stage in {"staging", "prod"}:
        invalid += (f"{prefix}{unmonitored} = true\n",)
    for value in invalid:
        path.write_text(text + value, encoding="utf-8")
        with pytest.raises(
            ValueError,
            match=r"exactly one|email addresses|action group ARM ID|literal|monitored",
        ):
            namespace["registry_server"](stage, root)
    path.write_text(
        text + f"{prefix}{emails} = [{quote}ops@example.com{quote}]\n",
        encoding="utf-8",
    )
    assert namespace["registry_server"](stage, root).endswith(".azurecr.io")


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("registry_sku", '"Premium"'),
        ("name_prefix", '"INVALID"'),
        ("network_address_prefix", '"10.44.1.1/22"'),
        ("environment_variables", '{ azure_client_id = "override" }'),
        ("environment_variables", '{ APP_POSTGRES_HOST = "override" }'),
        ("environment_variables", '{ APP_AI_API_KEY = "override" }'),
        ("environment_variables", '{ APP_ENVIRONMENT = "local" }'),
        ("environment_variables", '{ OTEL_SERVICE_NAME = "override" }'),
        ("unknown_setting", "true"),
        ("alerts_unmonitored", "true\n{declaration} = true"),
    ],
)
def test_prebuild_rejects_invalid_settings_and_owned_collisions(
    source: Path, tmp_path: Path, iac: str, field: str, value: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac, "postgresql", "text")
    namespace = runpy.run_path(str(root / "scripts/validate_environment.py"))
    extension = "bicepparam" if iac == "bicep" else "tfvars"
    path = root / "infra" / f"dev.{extension}"
    # These are synthetic local inputs, never deployed.
    replacements = {
        "REPLACE_WITH_RESOURCE_GROUP_ARM_ID": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/app",
        "REPLACE_WITH_NONOVERLAPPING_CIDR": "10.44.0.0/22",
        "REPLACE_WITH_ENTRA_ADMIN_OBJECT_ID": "11111111-1111-1111-1111-111111111111",
        "REPLACE_WITH_ENTRA_ADMIN_DISPLAY_NAME": "database-admins",
        "REPLACE_WITH_REGIONAL_MODEL": "synthetic-model",
        "REPLACE_WITH_PINNED_MODEL_VERSION": "2026-01-01",
        "REPLACE_WITH_DEPLOYMENT_SKU": "GlobalStandard",
    }
    text = path.read_text()
    for placeholder, literal in replacements.items():
        text = text.replace(placeholder, literal)
    path.write_text(text, encoding="utf-8")
    namespace["validate"]("dev", root)
    if iac == "bicep":
        field = re.sub(r"_([a-z])", lambda match: match[1].upper(), field)
        value = value.replace('"', "'").replace(" = ", ": ")
        declaration = f"param {field}"
    else:
        declaration = field
    text = re.sub(rf"(?m)^{declaration}\s*=.*\n", "", text)
    value = value.replace("{declaration}", declaration)
    path.write_text(f"{text}\n{declaration} = {value}\n", encoding="utf-8")
    with pytest.raises(
        ValueError,
        match=r"SKU|name prefix|host bits|provisioner-owned|Key Vault|Unknown|Duplicate|syntax|camelCase",
    ):
        namespace["validate"]("dev", root)


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("environment-template")
    shutil.copyfile(_ROOT / "copier.yml", directory / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", directory / "packages/starter/template"
    )
    return directory


def _render(
    source: Path,
    destination: Path,
    iac: str,
    data: str = "none",
    ai_service: str = "none",
) -> Path:
    cached = source.parent / f"{source.name}-{iac}-{data}-{ai_service}"
    if not cached.exists():
        run_copy(
            str(source),
            cached,
            data={
                "project_name": "sample",
                "service": "api",
                "iac": iac,
                "kit_commit": _COMMIT,
                "data": data,
                "ai_service": ai_service,
            },
            settings=Settings(),
            defaults=True,
            quiet=True,
        )
    shutil.copytree(cached, destination)
    return destination


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_generated_preflight_scripts_pass_consumer_lint(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac, "postgresql", "text")
    for arguments in (("format", "--check"), ("check",)):
        result = subprocess.run(  # noqa: S603 - installed Ruff, generated offline fixture
            [sys.executable, "-m", "ruff", *arguments, "scripts"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT,
        )
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("stage", _CLOUD_STAGES)
@pytest.mark.parametrize(
    ("iac", "extension", "declaration"),
    [
        ("bicep", "bicepparam", r"param\s+stage\s*=\s*'([^']+)'"),
        ("terraform", "tfvars", r'stage\s*=\s*"([^"]+)"'),
    ],
    ids=["bicep", "terraform"],
)
def test_each_cloud_environment_has_parameters_with_its_stage(
    source: Path,
    tmp_path: Path,
    iac: str,
    extension: str,
    declaration: str,
    stage: str,
) -> None:
    root = _render(source, tmp_path / "consumer", iac)
    parameters = root / "infra" / f"{stage}.{extension}"
    assert parameters.is_file(), f"{iac} must generate infra/{parameters.name}"
    stages = re.findall(
        rf"(?m)^[ \t]*{declaration}[ \t]*(?://[^\n]*|#[^\n]*)?$",
        parameters.read_text(encoding="utf-8"),
    )
    assert stages == [stage], (
        f"infra/{parameters.name} must explicitly set stage={stage!r}; got {stages}"
    )
    # Bicep's fail() only runs at deployment, so pin the shipped registry SKU here.
    skus = re.findall(
        r"(?m)^[ \t]*(?:param\s+)?registry_?[sS]ku\s*=\s*['\"](\w+)['\"]",
        parameters.read_text(encoding="utf-8"),
    )
    expected = "Premium" if stage in {"staging", "prod"} else "Basic"
    assert skus == [expected], (
        f"infra/{parameters.name} must set the registry SKU to {expected}; got {skus}"
    )


def test_iac_none_keeps_compose_without_cloud_infrastructure(
    source: Path, tmp_path: Path
) -> None:
    root = _render(source, tmp_path / "consumer", "none")
    assert (root / "compose.yaml").is_file(), "Local Compose must remain available"
    assert not (root / "infra").exists(), "iac=none must not emit infrastructure"
    assert not (root / ".github/workflows/deploy.yml").exists(), (
        "iac=none must not emit an Azure deployment workflow"
    )


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_deploy_dispatch_offers_all_cloud_environments_but_not_local(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac)
    deploy = yaml.load(
        (root / ".github/workflows/deploy.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    inputs = deploy["on"]["workflow_dispatch"]["inputs"]
    assert "environment" in inputs, f"{iac} deploy must offer an environment selector"
    environment = inputs["environment"]
    assert environment.get("type") == "choice", (
        f"{iac} deploy environment must be a choice input"
    )
    assert sorted(environment.get("options", [])) == sorted(_CLOUD_STAGES), (
        f"{iac} deploy must offer exactly dev/test/staging/prod, never local"
    )
    jobs = deploy["jobs"]
    assert jobs["image"]["needs"] == ["checks", "intent"]
    assert "validate_environment.py" in str(jobs["intent"])
    assert jobs["deploy"]["with"]["environment"] == "${{ inputs.environment }}"
    assert jobs["deploy"]["with"]["runs-on"] == "${{ inputs.runs-on }}"


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_dispatch_stage_guard_rejects_mismatch_duplicate_local_and_placeholders(
    source: Path, tmp_path: Path, iac: str
) -> None:
    root = _render(source, tmp_path / "consumer", iac)
    namespace = runpy.run_path(str(root / "scripts/validate_environment.py"))
    validate = namespace["validate"]
    extension = "bicepparam" if iac == "bicep" else "tfvars"
    declaration = "param stage = 'dev'" if iac == "bicep" else 'stage = "dev"'
    path = root / "infra" / f"dev.{extension}"
    original = path.read_text().replace(
        "REPLACE_WITH_RESOURCE_GROUP_ARM_ID",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/app",
    )
    path.write_text(original, encoding="utf-8")
    validate("dev", root)
    with pytest.raises(ValueError, match="local uses Compose"):
        validate("local", root)
    for text in (
        declaration.replace("dev", "test"),
        declaration + "\n" + declaration,
        declaration.replace("'dev'", "'dev' + ''").replace('"dev"', '"${local.stage}"'),
        "/*\n" + declaration + "\n*/",
    ):
        path.write_text(text + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="stage must"):
            validate("dev", root)
    path.write_text(declaration + "\n# REPLACE_WITH_CONFIG\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Complete caller-owned"):
        validate("dev", root)


_NOT_DEV = "[not(equals(parameters('stage'), 'dev'))]"
_PROD_LIKE = "[variables('prodLike')]"


def _assert_bicep_topology(compiled: str, data: str, ai_service: str) -> None:
    """Assert compiled per-stage network rules, independent of parameter files."""
    arm = json.loads(compiled)
    variables, resources = arm["variables"], arm["resources"]
    assert variables["prodLike"] == (
        "[contains(createArray('staging', 'prod'), parameters('stage'))]"
    )
    if data == "postgresql":
        assert variables["needsNetwork"] is True
    else:
        assert variables["needsNetwork"] == (
            _NOT_DEV if ai_service == "text" else _PROD_LIKE
        )
    assert resources["network"]["condition"] == "[variables('needsNetwork')]"
    zones = resources["network"]["properties"]["parameters"]["privateDnsZones"]
    if ai_service == "text":
        assert variables["privateAi"] == _NOT_DEV
        assert (
            "if(variables('privateAi'), createArray('cognitiveServices', 'openai', "
            "'aiServices'), createArray())"
        ) in zones["value"]
        ai = resources["aiService"]["properties"]["parameters"]
        assert ai["privateEndpoint"].startswith(
            "[if(variables('privateAi'), createObject("
        )
        assert "privateEndpointSubnetResourceId" in ai["privateEndpoint"]
        # Dev has no private endpoint, so it must opt in to the Entra-only public endpoint.
        for opt_in in ("allowPublicNetworkAccess", "allowAllPublicClients"):
            assert ai[opt_in]["value"] == "[not(variables('privateAi'))]", opt_in
    else:
        assert "privateAi" not in variables
        assert "aiServices" not in zones["value"]
    # The default ACR registry is private wherever the app environment is internal.
    assert variables["acrZones"] == (
        "[if(variables('prodLike'), createArray('containerRegistry'), createArray())]"
    )
    assert "variables('acrZones')" in zones["value"]
    registry = resources["registry"]["properties"]["parameters"]
    assert registry["privateEndpoint"].startswith(
        "[if(variables('prodLike'), createObject("
    )
    # A Premium registry outside staging and prod would deny public pulls.
    assert variables["checkedRegistrySku"].startswith(
        "[if(equals(variables('prodLike'), equals(parameters('registrySku'), "
        "'Premium')), parameters('registrySku'), fail("
    )
    assert registry["sku"] == {"value": "[variables('checkedRegistrySku')]"}
    foundation = resources["foundation"]["properties"]["parameters"]
    assert foundation["internalEnvironment"] == {"value": _PROD_LIKE}
    assert foundation["publicNetworkAccess"] == (
        "[if(variables('prodLike'), createObject('value', 'Disabled'), "
        "createObject('value', 'Enabled'))]"
    )


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
@pytest.mark.parametrize(
    ("data", "ai_service"),
    [
        ("none", "none"),
        ("postgresql", "none"),
        ("none", "text"),
        ("postgresql", "text"),
    ],
)
def test_selected_service_composition_and_offline_native_sources(
    source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    iac: str,
    data: str,
    ai_service: str,
) -> None:
    root = _render(source, tmp_path / "consumer", iac, data, ai_service)
    infra = root / "infra"
    main = (infra / ("main.bicep" if iac == "bicep" else "main.tf")).read_text()
    assert ("/postgresql/" in main) == (data == "postgresql")
    assert ("/ai-foundry/" in main) == (ai_service == "text")
    assert "/managed-redis/" not in main
    assert ("APP_POSTGRES_HOST" in main) == (data == "postgresql")
    assert ("APP_AI_API_BASE" in main) == (ai_service == "text")
    assert "APP_REDIS_ENTRA_AUTHENTICATION" not in main
    if iac == "bicep":
        starter_iac._fixture_vendor(root, monkeypatch)
        starter_iac._run("bicep", infra, "lint", "main.bicep", "--no-restore")
        compiled = starter_iac._run(
            "bicep", infra, "build", "main.bicep", "--no-restore", "--stdout"
        )
        for stage in _CLOUD_STAGES:
            starter_iac._run(
                "bicep",
                infra,
                "build-params",
                f"{stage}.bicepparam",
                "--no-restore",
                "--stdout",
            )
        _assert_bicep_topology(compiled, data, ai_service)
        assert "APP_ENVIRONMENT: stage" in main
        assert "appsSubnetResourceId" in main
        assert "requireUserEnvironment" in main
    else:
        starter_iac._run("terraform", infra, "fmt", "-check", "-recursive", "-diff")
        assert 'prod_like     = contains(["staging", "prod"], var.stage)' in main
        assert "internal_environment  = local.prod_like" in main
        assert "APP_ENVIRONMENT = var.stage" in main
        assert "apps_subnet_resource_id" in main
        if ai_service == "text":
            for opt_in in ("allow_public_network_access", "allow_all_public_clients"):
                assert re.search(rf"(?m)^\s*{opt_in}\s*=\s*!local\.ai_private$", main)
        for variable in ("runtime_identity_id", "telemetry_workspace_id"):
            value = re.search(rf"(?m)^\s*{variable}\s*=\s*(.+)$", main)
            assert value
            assert "var.resource_group_id" in value.group(1)
            assert ".id" not in value.group(1)


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_cloud_redis_fails_explicitly_without_key_fallback(
    source: Path, tmp_path: Path, iac: str
) -> None:
    for selected in ({}, {"data": "postgresql", "ai_service": "text"}):
        with pytest.raises(ValueError, match="Azure Redis Entra runtime"):
            run_copy(
                str(source),
                tmp_path / "consumer",
                data={
                    "service": "api",
                    "iac": iac,
                    "cache": "redis",
                    "kit_commit": _COMMIT,
                    **selected,
                },
                settings=Settings(),
                defaults=True,
                quiet=True,
            )


def test_ai_guidance_does_not_provision_ai(source: Path, tmp_path: Path) -> None:
    run_copy(
        str(source),
        tmp_path / "consumer",
        data={"service": "api", "iac": "bicep", "ai": True, "kit_commit": _COMMIT},
        settings=Settings(),
        defaults=True,
        quiet=True,
    )
    main = (tmp_path / "consumer/infra/main.bicep").read_text()
    assert "/ai-foundry/" not in main
    assert "APP_AI_API_BASE" not in main


def test_bicep_provisioner_owned_names_reject_both_user_maps(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    starter_iac._fixture_vendor(root, monkeypatch)
    infra = root / "infra"
    cases = (
        ("{ EXTRA: 'value' }", "[]", True),
        ("{ app_environment: 'local' }", "[]", False),
        ("{}", "['APP_ENVIRONMENT']", False),
        ("{ APP_POSTGRES_HOST: 'override' }", "[]", False),
        ("{}", "['app_ai_api_base']", False),
    )
    for values, secrets, accepted in cases:
        (infra / "collision.bicepparam").write_text(
            "using none\nimport { requireUserEnvironment } from './main.bicep'\n"
            f"param checked = requireUserEnvironment({values}, {secrets}, "
            "['APP_ENVIRONMENT', 'APP_POSTGRES_HOST', 'APP_AI_API_BASE'])\n",
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603 - installed compiler and synthetic offline parameters
            [
                starter_iac._tool("bicep"),
                "build-params",
                "collision.bicepparam",
                "--no-restore",
                "--stdout",
            ],
            cwd=infra,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT,
        )
        assert (result.returncode == 0) is accepted, result.stderr
        if not accepted:
            assert "collide with provisioner-owned settings" in result.stderr


def test_bicep_root_accepts_staging_and_rejects_local(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _render(source, tmp_path / "consumer", "bicep")
    starter_iac._fixture_vendor(root, monkeypatch)
    infra = root / "infra"
    for stage in ("staging", "local"):
        (infra / "stage-check.bicepparam").write_text(
            "using './main.bicep'\n"
            f"param stage = '{stage}'\nparam namePrefix = 'sample'\n"
            "param registryName = 'sampleacr'\nparam registrySku = 'Premium'\n"
            f"param containerImage = 'sampleacr.azurecr.io/app@sha256:{'a' * 64}'\n",
            encoding="utf-8",
        )
        result = subprocess.run(  # noqa: S603 - installed compiler and synthetic offline parameters
            [
                starter_iac._tool("bicep"),
                "build-params",
                "stage-check.bicepparam",
                "--no-restore",
                "--stdout",
            ],
            cwd=infra,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TIMEOUT,
        )
        assert (result.returncode == 0) is (stage == "staging"), result.stderr
        if stage == "local":
            assert "stage" in result.stderr


def _stage_plan(stage: str, data: str, ai_service: str) -> str:
    """Return one first-plan run asserting the stage's selected private topology."""
    prod_like = stage in {"staging", "prod"}
    private_ai = ai_service == "text" and stage != "dev"
    network = data == "postgresql" or private_ai or prod_like
    zones = sorted(
        (["postgresql"] if data == "postgresql" else [])
        + (["cognitiveServices", "openai", "aiServices"] if private_ai else [])
        + (["containerRegistry"] if prod_like else [])
    )
    zone_keys = 'join(",", sort(keys(module.network[0].private_dns_zone_resource_ids)))'
    checks = [
        (
            f'local.app_environment.APP_ENVIRONMENT == "{stage}"',
            "The application must receive the selected environment.",
        ),
        (
            f"length(module.network) == {int(network)}",
            "The network must exist exactly when a private service needs it.",
        ),
        (
            f"local.prod_like == {str(prod_like).lower()}",
            "Staging must rehearse production isolation.",
        ),
        (
            f"length(azapi_resource.telemetry_lock) == {int(prod_like)}",
            "Production-like stages must lock the stack-owned log workspace.",
        ),
    ]
    if network:
        checks.append(
            (
                f'{zone_keys} == "{",".join(zones)}"',
                "Private DNS zones must match the stage's private services.",
            )
        )
    if data == "postgresql":
        checks.append(
            (
                'local.app_environment.APP_POSTGRES_ENTRA_AUTHENTICATION == "true"',
                "Provisioned PostgreSQL must use keyless authentication.",
            )
        )
    if ai_service == "text":
        checks += [
            (
                f"local.ai_private == {str(private_ai).lower()}",
                "AI must stay private outside dev.",
            ),
            (
                'local.app_environment.APP_AI_ENTRA_AUTHENTICATION == "true"',
                "Provisioned AI must use keyless authentication.",
            ),
        ]
    asserts = "".join(
        f"  assert {{\n    condition     = {condition}\n"
        f'    error_message = "{message}"\n  }}\n'
        for condition, message in checks
    )
    # The private endpoint used in staging and prod needs a Premium registry.
    sku = '\n    registry_sku = "Premium"' if prod_like else ""
    return (
        f'run "{stage}_empty_state" {{\n  command = plan\n'
        f'  variables {{\n    stage = "{stage}"{sku}\n  }}\n{asserts}}}\n'
    )


@pytest.mark.parametrize(
    ("data", "ai_service"),
    [
        ("none", "none"),
        ("postgresql", "none"),
        ("none", "text"),
        ("postgresql", "text"),
    ],
)
def test_terraform_service_matrix_first_plans_all_stages_offline(
    source: Path, tmp_path: Path, data: str, ai_service: str
) -> None:
    root = _render(source, tmp_path / "consumer", "terraform", data, ai_service)
    group = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/app"
    variables: dict[str, object] = {
        "resource_group_id": group,
        "name_prefix": "sample",
        "registry_name": "sampleacr",
        # Public dev and test registries; prod-like runs override it with Premium.
        "registry_sku": "Basic",
        "container_image": "sampleacr.azurecr.io/app@sha256:" + "a" * 64,
        "network_address_prefix": "10.44.0.0/22",
        "alert_action_group_resource_id": (
            f"{group}/providers/Microsoft.Insights/actionGroups/operations"
        ),
    }
    if data == "postgresql":
        variables["postgres_administrator"] = {
            "object_id": "11111111-1111-1111-1111-111111111111",
            "name": "database-admins",
            "type": "Group",
        }
    if ai_service == "text":
        variables["ai_deployment"] = {
            "name": "text",
            "model": "synthetic-model",
            "version": "2026-01-01",
            "sku": "GlobalStandard",
            "capacity": 1,
        }
    assignments = "\n".join(
        f"  {name} = {json.dumps(value)}" for name, value in variables.items()
    )
    # Data sources are read at plan time: the identity lookup needs a client ID and
    # the registry's AcrPush grant needs the deploying principal's object ID.
    mock = (
        'mock_provider "azapi" {\n'
        '  mock_data "azapi_resource" {\n'
        '    defaults = {\n      location = "westeurope"\n'
        '      output = { properties = { clientId = "22222222-2222-2222-2222-222222222222" } }\n'
        "    }\n  }\n"
        '  mock_data "azapi_client_config" {\n'
        '    defaults = { object_id = "33333333-3333-3333-3333-333333333333" }\n'
        "  }\n}\n"
    )
    tests = [
        mock,
        f"variables {{\n{assignments}\n}}\n",
        *(_stage_plan(stage, data, ai_service) for stage in _CLOUD_STAGES),
        *(
            f'run "reject_{stage}_{sku.lower()}_registry" {{\n  command = plan\n'
            f'  variables {{\n    stage = "{stage}"\n    registry_sku = "{sku}"\n  }}\n'
            "  expect_failures = [var.registry_sku]\n}\n"
            for stage, sku in _REGISTRY_SKU_MISMATCHES
        ),
    ]
    owned_names = (
        "APP_ENVIRONMENT",
        *(["APP_POSTGRES_HOST"] if data == "postgresql" else []),
        *(["APP_AI_API_BASE", "APP_AI_API_VERSION"] if ai_service == "text" else []),
    )
    for owned in owned_names:
        tests.append(
            f'run "reject_environment_{owned.lower()}" {{\n  command = plan\n'
            '  variables {\n    stage = "dev"\n'
            f'    environment_variables = {{ {owned.lower()} = "override" }}\n'
            "  }\n  expect_failures = [var.environment_variables]\n}\n"
        )
        tests.append(
            f'run "reject_secret_{owned.lower()}" {{\n  command = plan\n'
            '  variables {\n    stage = "dev"\n'
            '    secret_references = [{ name = "override", '
            f'environment_variable = "{owned}", '
            'key_vault_url = "https://example.vault.azure.net/secrets/override" }]\n'
            "  }\n  expect_failures = [var.secret_references]\n}\n"
        )
    starter_iac._check_first_plans(
        root=root / "infra",
        cases="\n".join(tests),
        expected_runs=len(_CLOUD_STAGES)
        + len(_REGISTRY_SKU_MISMATCHES)
        + 2 * len(owned_names),
    )
