"""Catalog, policy, dependency closure and standalone relocation regressions."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Final

import pytest

import check
from delivery_tools import check_ado_scripts
from delivery_tools.catalog import (
    ROOT,
    WORKFLOW_FILES,
    build,
    nodes,
    parameters,
    workflow_paths,
)
from delivery_tools.check_ado_scripts import discover, shell_source
from delivery_tools.documents import DocumentError, mapping, read_yaml
from delivery_tools.validate import validate

pytestmark = pytest.mark.unit
WORKFLOW_ROOT: Final[Path] = ROOT.parents[1] / ".github/workflows"
# Reviewed independently of ``COMPOSITIONS`` so an unregistered module fails here.
AZURE_COMPOSITIONS: Final[tuple[str, ...]] = (
    "ai-foundry",
    "ai-search",
    "api-management",
    "application-insights",
    "audit-logs",
    "container-apps",
    "container-apps-alerts",
    "container-registry",
    "cosmos-db",
    "document-intelligence",
    "key-vault",
    "managed-redis",
    "network",
    "postgresql",
    "storage-account",
    "terraform-state",
)


@pytest.fixture
def package_copy(tmp_path: Path) -> Path:
    return Path(
        shutil.copytree(
            ROOT,
            tmp_path / "delivery",
            ignore=shutil.ignore_patterns("__pycache__", ".ruff_cache"),
        )
    )


@pytest.fixture
def workflow_copy(tmp_path: Path) -> Path:
    directory = tmp_path / "canonical-workflows"
    directory.mkdir()
    for name in WORKFLOW_FILES:
        shutil.copyfile(WORKFLOW_ROOT / name, directory / name)
    return directory


def test_real_package_contract() -> None:
    validate(workflow_root=WORKFLOW_ROOT)
    catalog = build(workflow_root=WORKFLOW_ROOT)
    assert catalog["schemaVersion"] == 4
    workflows = mapping(catalog["github"])
    assert len(workflows) == 5
    python = mapping(workflows["delivery-python-ci"])
    assert python["permissions"] == {"contents": "read"}
    inputs = mapping(python["inputs"])
    assert mapping(inputs["timeout-minutes"])["default"] == 30
    assert mapping(inputs["uv-version"])["required"] is True
    assert python["path"] == ".github/workflows/delivery-python-ci.yml"
    assert python["sourceRoot"] == "repository"
    assert "integrationPath" not in python
    action = mapping(mapping(catalog["githubActions"])["python-check"])
    assert action["path"] == "actions/python-check/action.yml"
    assert action["sourceRoot"] == "package"
    assert action["reference"] == "$/packages/delivery/actions/python-check"
    assert mapping(mapping(action["inputs"])["task"])["default"] == "verify"


@pytest.mark.parametrize("composition", AZURE_COMPOSITIONS)
def test_catalog_lists_each_azure_composition(composition: str) -> None:
    infrastructure = mapping(build(workflow_root=WORKFLOW_ROOT)["azureInfrastructure"])
    assert set(infrastructure) == set(AZURE_COMPOSITIONS)
    entry = mapping(infrastructure[composition])
    path = f"infra/{composition}"
    assert entry["path"] == path
    assert entry["bicep"] == f"{path}/bicep/main.bicep"
    assert entry["terraform"] == f"{path}/terraform/main.tf"
    files = entry["files"]
    assert isinstance(files, list)
    assert {f"{path}/README.md", f"{path}/REFERENCE.md"} <= set(files)


def test_toolkit_and_delivery_share_the_source_bound_python_check() -> None:
    reference = "$/packages/delivery/actions/python-check"
    for name, job in (("toolkit-ci.yml", "verify"), ("delivery-python-ci.yml", "gate")):
        document = read_yaml(WORKFLOW_ROOT / name, workflow=True)
        steps = mapping(mapping(document["jobs"])[job])["steps"]
        assert isinstance(steps, list)
        calls = [
            mapping(step) for step in steps if mapping(step).get("uses") == reference
        ]
        assert len(calls) == 1
        assert not any(
            str(mapping(step).get("uses", "")).startswith(
                ("actions/setup-python@", "astral-sh/setup-uv@")
            )
            for step in steps
        )
    action = read_yaml(ROOT / "actions/python-check/action.yml", workflow=True)
    assert mapping(action["runs"])["using"] == "composite"
    assert mapping(mapping(action["inputs"])["task"])["default"] == "verify"
    commands = [node["run"] for node in nodes(action) if "run" in node]
    assert len(commands) == 3
    assert commands[-2:] == [
        "uv sync --locked",
        'uv run --locked --no-sync task "$TASK_NAME"',
    ]


def test_deploy_workflow_contract_is_minimal_and_least_privilege() -> None:
    workflows = mapping(build(workflow_root=WORKFLOW_ROOT)["github"])
    deploy = mapping(workflows["delivery-azure-deploy"])
    # Caller grant: union of the job grants, never broader than the jobs need.
    assert deploy["permissions"] == {
        "actions": "read",
        "contents": "read",
        "id-token": "write",
    }
    assert deploy["secrets"] == {}
    inputs = mapping(deploy["inputs"])
    assert [name for name, item in inputs.items() if mapping(item)["required"]] == [
        "environment"
    ]
    assert mapping(inputs["iac"])["default"] == "bicep"
    assert mapping(inputs["protected"])["default"] is False
    assert mapping(inputs["health-url"])["default"] == ""
    for name, workflow in workflows.items():
        if name != "delivery-azure-deploy":
            assert mapping(workflow)["permissions"] == {"contents": "read"}
    document = read_yaml(WORKFLOW_ROOT / "delivery-azure-deploy.yml", workflow=True)
    jobs = mapping(document["jobs"])
    for name, job in jobs.items():
        permissions = mapping(mapping(job)["permissions"])
        assert ("id-token" in permissions) is (name != "preflight")
        assert "secrets" not in mapping(job)


def test_deploy_health_check_is_optional_https_and_injection_safe() -> None:
    document = read_yaml(WORKFLOW_ROOT / "delivery-azure-deploy.yml", workflow=True)
    steps = mapping(mapping(document["jobs"])["deploy"])["steps"]
    assert isinstance(steps, list)
    health = mapping(steps[-1])
    assert health["name"] == "Check health"
    assert health["if"] == "inputs.health-url != ''"
    assert mapping(health["env"]) == {"HEALTH_URL": "${{ inputs.health-url }}"}
    script = health["run"]
    assert isinstance(script, str)
    assert "${{" not in script
    assert "--fail" in script
    assert "--proto '=https'" in script
    assert "^2[0-9][0-9]$" in script
    preflight = mapping(document["jobs"])["preflight"]
    assert 'fail "health-url must be an HTTPS URL"' in str(preflight)
    ado = (ROOT / "azure-devops/steps/azure-deploy.yml").read_text(encoding="utf-8")
    assert "eq(parameters.mode, 'deploy'), ne(parameters.healthUrl, '')" in ado
    assert 'fail "healthUrl must be an HTTPS URL"' in ado
    assert "^2[0-9][0-9]$" in ado
    # The URL reaches shell only through the environment, never template expansion.
    assert ado.count("${{ parameters.healthUrl }}") == 2
    assert ado.count("HEALTH_URL: ${{ parameters.healthUrl }}") == 2


def test_azure_devops_deploy_templates_are_cataloged() -> None:
    azure = mapping(build(workflow_root=WORKFLOW_ROOT)["azureDevOps"])
    extends = mapping(mapping(azure["extends"])["azure-deploy"])
    steps = mapping(mapping(azure["steps"])["azure-deploy"])
    assert extends["path"] == "azure-devops/extends/azure-deploy.yml"
    contract = mapping(extends["parameters"])
    assert [name for name, item in contract.items() if mapping(item)["required"]] == [
        "environments"
    ]
    contract = mapping(steps["parameters"])
    assert {name for name, item in contract.items() if mapping(item)["required"]} == {
        "mode",
        "environment",
        "serviceConnection",
    }
    assert mapping(contract["mode"])["values"] == ["preview", "deploy"]
    document = read_yaml(ROOT / "azure-devops/extends/azure-deploy.yml")
    deployments = [node for node in nodes(document) if "deployment" in node]
    assert len(deployments) == 1
    assert deployments[0]["environment"] == "${{ environment.name }}"
    # Approvals are per stage: preview must not share a stage with the environment.
    stages = [node for node in nodes(document) if "stage" in node]
    assert [str(node["stage"]).split("_")[0] for node in stages] == [
        "preview",
        "deploy",
    ]
    assert not any("deployment" in node for node in nodes(stages[0]))


@pytest.mark.parametrize("name", ["delivery-python-ci", "delivery-bun-ci"])
def test_github_ci_has_no_upload_support(name: str) -> None:
    document = read_yaml(WORKFLOW_ROOT / f"{name}.yml", workflow=True)
    call = mapping(mapping(document["on"])["workflow_call"])
    assert "secrets" not in call
    assert {"upload-coverage", "coverage-file"}.isdisjoint(mapping(call["inputs"]))
    assert document["permissions"] == {"contents": "read"}
    assert not any(
        str(node.get("uses", "")).startswith("codecov/") for node in nodes(document)
    )
    contract = mapping(mapping(build(workflow_root=WORKFLOW_ROOT)["github"])[name])
    assert contract["secrets"] == {}
    assert {"upload-coverage", "coverage-file"}.isdisjoint(mapping(contract["inputs"]))


@pytest.mark.parametrize(
    ("relative", "old", "new", "error"),
    [
        (
            "workflows/delivery-bun-ci.yml",
            "contents: read",
            "contents: write",
            "read-only",
        ),
        ("workflows/delivery-bun-ci.yml", "workflow_call:", "push:", "call-only"),
        (
            "workflows/delivery-bun-ci.yml",
            "0c5077e51419868618aeaa5fe8019c62421857d6",
            "main",
            "Unpinned",
        ),
        (
            "workflows/delivery-bun-ci.yml",
            'bun run "$SCRIPT_NAME"',
            "bun run ${{ inputs.script }}",
            "interpolated",
        ),
        (
            "workflows/delivery-bun-ci.yml",
            "persist-credentials: false",
            "persist-credentials: true",
            "persist credentials",
        ),
        (
            "azure-devops/extends/python-ci.yml",
            "../jobs/python-task.yml",
            "../../../outside.yml",
            "escapes",
        ),
        (
            "azure-devops/extends/python-ci.yml",
            "          name: gate",
            "          unknown: gate",
            "Unknown template",
        ),
        (
            "azure-devops/extends/bicep-check.yml",
            "              bicepVersion: ${{ parameters.bicepVersion }}\n",
            "",
            "Missing required",
        ),
        (
            "azure-devops/extends/bun-ci.yml",
            "parameters.bunVersion",
            "parameters.missing",
            "undeclared",
        ),
        (
            "renovate/default.json",
            '"dependencyDashboardApproval": true',
            '"dependencyDashboardApproval": false',
            "dashboard approval",
        ),
        ("renovate/default.json", '"7 days"', '"0 days"', "Release-age"),
        ("renovate/default.json", '"strict"', '"flexible"', "not strict"),
        ("catalog.json", '"schemaVersion": 4', '"schemaVersion": 5', "stale"),
        (
            "actions/python-check/action.yml",
            "uv sync --locked",
            "uv sync",
            "synchronize the lock",
        ),
        (
            "actions/python-check/action.yml",
            "default: verify",
            "default: help",
            "verification gate",
        ),
        (
            "actions/python-check/action.yml",
            "    - name: Run task",
            "    - name: Run task\n      if: false",
            "must run on success",
        ),
        (
            "actions/python-check/action.yml",
            "TASK_NAME: ${{ inputs.task }}",
            'TASK_NAME: ""',
            "declared action input",
        ),
        (
            "azure-devops/jobs/python-task.yml",
            'uv run --locked --no-sync task "${TASK_NAME}"',
            'uv run --locked task "${TASK_NAME}"',
            "locked Task",
        ),
        (
            "azure-devops/jobs/python-task.yml",
            "          TASK_NAME: ${{ parameters.task }}\n          BASE_URL",
            '          TASK_NAME: ""\n          BASE_URL',
            "declared template parameter",
        ),
        (
            "actions/python-check/action.yml",
            "1c37ad07a6a961277cf70c0d37d6f313000f5884",
            "main",
            "Unpinned",
        ),
        (
            "actions/python-check/action.yml",
            "uv sync --locked",
            "uv sync ${{ inputs.task }}",
            "interpolated",
        ),
        (
            "actions/python-check/action.yml",
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "$/packages/delivery/actions/python-check",
            "Unpinned",
        ),
        (
            "workflows/delivery-python-ci.yml",
            "$/packages/delivery/actions/python-check",
            "./packages/delivery/actions/python-check",
            "Unpinned",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "      actions: read\n",
            "      actions: read\n      id-token: write\n",
            "job preflight needs exactly",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "      actions: read\n",
            "      actions: write\n",
            "job preflight needs exactly",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "    environment: ${{ inputs.environment }}\n",
            "",
            "Deploy must run in the protected environment",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "    needs: [preflight, plan]\n",
            "    needs: preflight\n",
            "Deploy must run in the protected environment",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "      deployment: false\n",
            "",
            "without creating a deployment",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "    timeout-minutes: 5\n",
            "    timeout-minutes: 5\n    environment: ${{ inputs.environment }}\n",
            "before any job references it",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "- name: Require a reviewed environment",
            "- name: Read environment",
            "before any job references it",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "retention-days: 1\n",
            "retention-days: 90\n",
            "retention-days: 1",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "  group: delivery-azure-deploy-${{ inputs.environment }}\n",
            (
                "  group: delivery-azure-deploy-${{ inputs.environment }}\n"
                "  cancel-in-progress: true\n"
            ),
            "never cancel",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "    inputs:\n      environment:\n",
            (
                "    secrets:\n      token:\n        required: false\n"
                "    inputs:\n      environment:\n"
            ),
            "must not accept secrets",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            "a641126d1b8aa4d1fa005f4f92df94a3a4c4c906",
            "v3",
            "Unpinned",
        ),
        (
            "workflows/delivery-azure-deploy.yml",
            '"${RUNNER_TEMP}/delivery-azure-deploy/tfplan"',
            "${{ inputs.working-directory }}/tfplan",
            "interpolated",
        ),
        (
            "azure-devops/extends/azure-deploy.yml",
            "            environment: ${{ environment.name }}\n            timeoutInMinutes",
            "            timeoutInMinutes",
            "must target an environment",
        ),
        (
            "azure-devops/extends/azure-deploy.yml",
            (
                "mode: preview\n"
                "                  environment: ${{ environment.name }}\n"
                "                  serviceConnection: ${{ environment.serviceConnection }}\n"
            ),
            "mode: preview\n                  environment: ${{ environment.name }}\n",
            "Missing required",
        ),
        (
            "azure-devops/extends/azure-deploy.yml",
            "persistCredentials: false",
            "persistCredentials: true",
            "persists credentials",
        ),
        (
            "azure-devops/steps/azure-deploy.yml",
            'terraform apply -input=false "${ARTIFACT}/tfplan"',
            "terraform apply ${{ parameters.workingDirectory }}/tfplan",
            "interpolated",
        ),
    ],
)
def test_contract_regressions_fail(
    package_copy: Path,
    workflow_copy: Path,
    relative: str,
    old: str,
    new: str,
    error: str,
) -> None:
    path = (
        workflow_copy / relative.removeprefix("workflows/")
        if relative.startswith("workflows/")
        else package_copy / relative
    )
    source = path.read_text(encoding="utf-8")
    assert old in source
    path.write_text(source.replace(old, new), encoding="utf-8")
    with pytest.raises(DocumentError, match=error):
        validate(package_copy, workflow_root=workflow_copy)


def test_removing_required_template_fails(
    package_copy: Path, workflow_copy: Path
) -> None:
    (package_copy / "azure-devops/steps/setup-bun.yml").unlink()
    with pytest.raises(DocumentError, match="inventory"):
        validate(package_copy, workflow_root=workflow_copy)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("-lockfile=readonly", "-upgrade"),
        (
            "subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}",
            "subscription-id: ${{ inputs.resource-group }}",
        ),
        ("terraform_wrapper: false", "terraform_wrapper: true"),
        ("container='^", "container='"),
    ],
)
def test_deploy_steps_must_match_their_preview(
    package_copy: Path, workflow_copy: Path, old: str, new: str
) -> None:
    path = workflow_copy / "delivery-azure-deploy.yml"
    head, found, tail = path.read_text(encoding="utf-8").rpartition(old)
    assert found
    path.write_text(head + new + tail, encoding="utf-8")
    with pytest.raises(DocumentError, match="Deploy step differs from its preview"):
        validate(package_copy, workflow_root=workflow_copy)


def test_missing_action_fails_catalog_and_validation(
    package_copy: Path, workflow_copy: Path
) -> None:
    (package_copy / "actions/python-check/action.yml").unlink()
    with pytest.raises(DocumentError, match="action is missing"):
        build(package_copy, workflow_root=workflow_copy)
    with pytest.raises(DocumentError, match="inventory"):
        validate(package_copy, workflow_root=workflow_copy)


def test_unknown_entrypoint_fails(package_copy: Path, workflow_copy: Path) -> None:
    (package_copy / "workflows").mkdir(exist_ok=True)
    (package_copy / "workflows/unreviewed.yml").write_text("{}", encoding="utf-8")
    with pytest.raises(DocumentError, match="inventory"):
        validate(package_copy, workflow_root=workflow_copy)


def test_broken_documentation_link_fails(
    package_copy: Path, workflow_copy: Path
) -> None:
    (package_copy / "README.md").write_text("[missing](missing.md)", encoding="utf-8")
    with pytest.raises(DocumentError, match="broken"):
        validate(package_copy, workflow_root=workflow_copy)


@pytest.mark.parametrize("directory", ["workflows", ".github/workflows", "archive"])
def test_duplicate_package_workflow_fails(
    package_copy: Path, workflow_copy: Path, directory: str
) -> None:
    duplicate = package_copy / directory / "delivery-bun-ci.yml"
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(workflow_copy / duplicate.name, duplicate)
    with pytest.raises(DocumentError, match="Entry point inventory"):
        validate(package_copy, workflow_root=workflow_copy)


@pytest.mark.parametrize("name", WORKFLOW_FILES)
def test_missing_canonical_workflow_fails_catalog_and_validation(
    package_copy: Path, workflow_copy: Path, name: str
) -> None:
    (workflow_copy / name).unlink()
    with pytest.raises(DocumentError, match="Workflow inventory"):
        build(package_copy, workflow_root=workflow_copy)
    with pytest.raises(DocumentError, match="Workflow inventory"):
        validate(package_copy, workflow_root=workflow_copy)


@pytest.mark.parametrize(
    "relative",
    ["delivery-deploy.yml", "delivery-python-ci.yaml", "nested/delivery-bun-ci.yml"],
)
def test_extra_or_nested_delivery_workflows_fail(
    workflow_copy: Path, relative: str
) -> None:
    path = workflow_copy / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(DocumentError, match="Workflow inventory"):
        workflow_paths(workflow_copy)


def test_unrelated_root_workflows_are_not_owned(workflow_copy: Path) -> None:
    (workflow_copy / "toolkit-ci.yml").write_text("not delivery YAML", encoding="utf-8")
    assert {path.name for path in workflow_paths(workflow_copy)} == set(WORKFLOW_FILES)


def test_missing_or_empty_explicit_workflow_root_fails(tmp_path: Path) -> None:
    with pytest.raises(DocumentError, match="Workflow inventory"):
        workflow_paths(tmp_path / "missing")
    with pytest.raises(DocumentError, match="Workflow inventory"):
        workflow_paths(tmp_path)


def test_duplicate_parameters_fail() -> None:
    item = {"name": "pin", "type": "string"}
    with pytest.raises(DocumentError, match="Duplicate"):
        parameters({"parameters": [item, item]})


def test_shellcheck_discovery_and_macro_neutralization() -> None:
    scripts = discover(ROOT)
    assert len(scripts) >= 13
    deploy = [script for script in scripts if script.template.stem == "azure-deploy"]
    # Input validation, both AzureCLI@2 inline scripts and the health check.
    assert len(deploy) == 4
    assert "ado_macro" in shell_source("echo $(Agent.TempDirectory)")
    assert "$(python --version)" in shell_source("echo $(python --version)")


def test_shellcheck_failures_name_the_package_relative_template(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "SC2086 finding\n", "")

    monkeypatch.setattr(check_ado_scripts.shutil, "which", lambda _: "shellcheck")
    monkeypatch.setattr(check_ado_scripts.subprocess, "run", failing)
    assert check_ado_scripts.main(root=ROOT) == 1
    assert "azure-devops/steps/setup-bun.yml: SC2086 finding" in capsys.readouterr().err


def test_check_reports_a_missing_field_by_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(**_: object) -> None:
        field = "runs"
        raise KeyError(field)

    monkeypatch.setattr(check, "validate", missing)
    monkeypatch.setattr(sys, "argv", ["check.py", "--workflow-root", "workflows"])
    assert check.main() == 1
    assert capsys.readouterr().err == "delivery: missing required field: runs\n"
