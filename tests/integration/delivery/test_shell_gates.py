"""Integration checks of imported Bash using local stubs, never live services."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Final, override
import zipfile

import pytest

from delivery_tools.catalog import ROOT, nodes
from delivery_tools.documents import read_yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration
WORKFLOW_ROOT: Final[Path] = ROOT.parents[1] / ".github/workflows"
DEPLOY: Final[str] = "workflows/delivery-azure-deploy.yml"
ADO_DEPLOY: Final[str] = "azure-devops/steps/azure-deploy.yml"
DIGEST: Final[str] = "registry.example/app@sha256:" + "a" * 64
GUID: Final[str] = "00000000-0000-4000-8000-000000000001"


@pytest.fixture
def bash() -> str:
    if os.name == "nt":
        path = Path(os.environ["PROGRAMFILES"]) / "Git/bin/bash.exe"
        assert path.is_file(), "Git Bash is required for delivery shell tests"
        return str(path)
    executable = shutil.which("bash")
    assert executable, "Bash is required for delivery shell tests"
    return executable


def script(relative: str, name: str) -> str:
    source = (
        WORKFLOW_ROOT / relative.removeprefix("workflows/")
        if relative.startswith("workflows/")
        else ROOT / relative
    )
    for node in nodes(read_yaml(source, workflow=True)):
        if node.get("name", node.get("displayName")) == name:
            inline = node.get("inputs")
            body = node.get(
                "run",
                node.get(
                    "bash",
                    inline.get("inlineScript") if isinstance(inline, dict) else None,
                ),
            )
            assert isinstance(body, str)
            return body
    pytest.fail(f"Missing imported script: {relative} / {name}")


def run(
    bash: str, body: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed bash, local stubs, no network
        [bash, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", body],
        cwd=cwd,
        env={**os.environ, "BASH_ENV": "", **(env or {})},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    ("relative", "name", "tool"),
    [
        ("actions/python-check/action.yml", "Install locked dependencies", "uv"),
        ("actions/python-check/action.yml", "Run task", "uv"),
        ("workflows/delivery-bun-ci.yml", "Install locked dependencies", "bun"),
        ("workflows/delivery-bun-ci.yml", "Run script", "bun"),
        ("azure-devops/jobs/python-task.yml", "Install locked dependencies", "uv"),
        ("azure-devops/extends/bun-ci.yml", "Install locked dependencies", "bun"),
        ("azure-devops/steps/terraform-check.yml", "Terraform format", "terraform"),
        (
            "azure-devops/steps/terraform-check.yml",
            "Terraform init without backend",
            "terraform",
        ),
        ("azure-devops/steps/terraform-check.yml", "Terraform validate", "terraform"),
    ],
)
def test_gate_failures_propagate(
    bash: str, tmp_path: Path, relative: str, name: str, tool: str
) -> None:
    result = run(
        bash,
        f"{tool}() {{ return 17; }}\n" + script(relative, name),
        tmp_path,
        {"TASK_NAME": "verify", "SCRIPT_NAME": "check"},
    )
    assert result.returncode == 17, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["python", "bun"])
def test_user_command_is_a_single_inert_argument(
    bash: str, tmp_path: Path, kind: str
) -> None:
    tool, step, variable = (
        ("uv", "Run task", "TASK_NAME")
        if kind == "python"
        else ("bun", "Run script", "SCRIPT_NAME")
    )
    value = "gate; touch SHOULD_NOT_EXIST"
    result = run(
        bash,
        f'{tool}() {{ printf "<%s>\\n" "$@"; }}\n'
        + script(
            "actions/python-check/action.yml"
            if kind == "python"
            else "workflows/delivery-bun-ci.yml",
            step,
        ),
        tmp_path,
        {variable: value},
    )
    assert result.returncode == 0, result.stderr
    assert f"<{value}>" in result.stdout
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


@pytest.mark.parametrize(
    ("relative", "error"),
    [
        ("actions/python-check/action.yml", "::error::Expected"),
        ("azure-devops/jobs/python-task.yml", "type=error]Expected"),
    ],
)
@pytest.mark.parametrize(
    ("python", "uv", "task", "valid"),
    [
        ("3.13", "0.13.3", "verify", True),
        ("3.14.1", "0.13.3", "ci:verify", True),
        ("", "0.13.3", "verify", False),
        ("3.x", "0.13.3", "verify", False),
        ("3.13", "", "verify", False),
        ("3.13", "latest", "verify", False),
        ("3.13", "0.13.3", "", False),
        ("3.13", "0.13.3", "--list", False),
        ("3.13", "0.13.3", "verify help", False),
        ("3.13", "0.13.3", "verify; touch SHOULD_NOT_EXIST", False),
    ],
)
def test_python_gates_reject_missing_versions_and_non_task_inputs(
    bash: str,
    tmp_path: Path,
    relative: str,
    error: str,
    python: str,
    uv: str,
    task: str,
    valid: bool,
) -> None:
    result = run(
        bash,
        script(relative, "Validate version and Task inputs"),
        tmp_path,
        {"PYTHON_VERSION": python, "UV_VERSION": uv, "TASK_NAME": task},
    )
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    if not valid:
        assert error in result.stdout
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


@pytest.mark.parametrize(
    ("relative", "name"),
    [
        ("workflows/delivery-bicep-check.yml", "Format, lint and build"),
        ("azure-devops/steps/bicep-check.yml", "Bicep format, lint and build"),
    ],
)
def test_bicep_empty_tree_and_compile_failure(
    bash: str, tmp_path: Path, relative: str, name: str
) -> None:
    body = script(relative, name)
    env = {"IAC_PATH": ".", "BICEP_VERSION": "0.48.1"}
    result = run(bash, "az() { return 0; }\n" + body, tmp_path, env)
    assert result.returncode != 0
    assert "No .bicep files found" in result.stdout
    (tmp_path / "space name.bicep").write_text("param label string\n", encoding="utf-8")
    stub = """az() {
      if [[ "$2" == format ]]; then cat "$4";
      elif [[ "$2" == build ]]; then return 19;
      else return 0; fi
    }\n"""
    result = run(bash, stub + body, tmp_path, env)
    assert result.returncode == 19, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("digest_kind", "success"), [("valid", True), ("mismatch", False), ("bad", False)]
)
def test_terraform_installer_checks_archive_without_network(
    bash: str, tmp_path: Path, digest_kind: str, success: bool
) -> None:
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("terraform", "#!/usr/bin/env bash\necho synthetic-tool\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest_kind != "valid":
        digest = "0" * 64 if digest_kind == "mismatch" else "bad"
    stub = """curl() {
      local output=""
      while (($#)); do
        if [[ "$1" == --output ]]; then output="$2"; shift; fi
        shift
      done
      cp "$FIXTURE_ARCHIVE" "$output"
    }\n"""
    result = run(
        bash,
        stub
        + script(
            "azure-devops/steps/setup-terraform.yml",
            "Set up Terraform ${{ parameters.terraformVersion }}",
        ),
        tmp_path,
        {
            "TERRAFORM_VERSION": "1.16.5",
            "TERRAFORM_SHA256": digest,
            "TERRAFORM_DIR": (tmp_path / "tool").as_posix(),
            "FIXTURE_ARCHIVE": archive.as_posix(),
        },
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    assert (tmp_path / "tool/bin/terraform").exists() is success


@pytest.mark.parametrize(
    ("digest_kind", "cached", "success"),
    [
        ("valid", False, True),
        ("valid", True, True),
        ("mismatch", False, False),
        ("mismatch", True, False),
        ("bad", False, False),
    ],
)
def test_bun_installer_verifies_downloaded_and_cached_archives(
    bash: str, tmp_path: Path, digest_kind: str, cached: bool, success: bool
) -> None:
    fixture = tmp_path / "fixture.zip"
    with zipfile.ZipFile(fixture, "w") as bundle:
        bundle.writestr(
            "bun-linux-x64-baseline/bun", "#!/usr/bin/env bash\necho 1.3.5\n"
        )
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    if digest_kind != "valid":
        digest = "0" * 64 if digest_kind == "mismatch" else "bad"
    install = tmp_path / "bun-home"
    archive = install / "bun-v1.3.5-linux-x64-baseline.zip"
    if cached:
        install.mkdir()
        shutil.copyfile(fixture, archive)
    stub = """curl() {
      echo DOWNLOAD
      local output=""
      while (($#)); do
        if [[ "$1" == --output ]]; then output="$2"; shift; fi
        shift
      done
      cp "$FIXTURE_ARCHIVE" "$output"
    }\n"""
    result = run(
        bash,
        stub
        + script(
            "azure-devops/steps/setup-bun.yml",
            "Set up Bun ${{ parameters.bunVersion }}",
        ),
        tmp_path,
        {
            "BUN_INSTALL": install.as_posix(),
            "BUN_EXTRACT_DIR": (tmp_path / "extract").as_posix(),
            "BUN_VERSION": "1.3.5",
            "BUN_SHA256": digest,
            "FIXTURE_ARCHIVE": fixture.as_posix(),
        },
    )
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    assert ("DOWNLOAD" in result.stdout) is (not cached and digest_kind != "bad")
    assert (install / "bin/bun").exists() is success
    assert archive.exists() is success


@pytest.mark.parametrize("version", ["latest", "1.16", "1.16.5/../x", ""])
def test_terraform_rejects_inexact_pin_before_download(
    bash: str, tmp_path: Path, version: str
) -> None:
    result = run(
        bash,
        "curl() { echo UNEXPECTED_DOWNLOAD; return 99; }\n"
        + script(
            "azure-devops/steps/setup-terraform.yml",
            "Set up Terraform ${{ parameters.terraformVersion }}",
        ),
        tmp_path,
        {"TERRAFORM_VERSION": version, "TERRAFORM_SHA256": "0" * 64},
    )
    assert result.returncode == 1, result.stderr
    assert "exact version" in result.stdout
    assert "UNEXPECTED_DOWNLOAD" not in result.stdout


REPOSITORY: Final[str] = "owner/repo"
FAKE_BEARER: Final[str] = "synthetic-token-value"
TERRAFORM_ROOT: Final[dict[str, str]] = {
    "IAC": "terraform",
    "WORKING_DIRECTORY": ".",
    "RESOURCE_GROUP": "",
}
# Records every call; writes --outfile targets; FAIL_ON makes a matching call fail.
AZ_STUB: Final[str] = r"""az() {
  printf '%s\n' "$*" >> "$TOOL_LOG"
  local previous=""
  for argument in "$@"; do
    if [[ "$previous" == --outfile ]]; then printf 'compiled\n' > "$argument"; fi
    previous="$argument"
  done
  if [[ -n "${FAIL_ON:-}" && "$*" == *"$FAIL_ON"* ]]; then return 23; fi
  return 0
}
"""
# Records calls and exported ARM_* values; init writes a backend of type $BACKEND.
TERRAFORM_STUB: Final[str] = r"""terraform() {
  printf '%s\n' "$*" >> "$TOOL_LOG"
  if [[ "$1" == init ]]; then
    env | grep '^ARM_' > "${ARM_LOG:-/dev/null}" || true
    if [[ -n "$BACKEND" ]]; then
      mkdir -p .terraform
      printf '{\n    "backend": {\n        "type": "%s"\n    }\n}\n' "$BACKEND" \
        > .terraform/terraform.tfstate
    fi
  fi
  return "${TOOL_STATUS:-0}"
}
"""


@pytest.fixture
def deploy_tree(tmp_path: Path) -> Path:
    """Caller repository with Bicep, nested Bicep and root Terraform layouts."""
    root = tmp_path / "repo"
    for relative in (
        "infra/main.bicep",
        "infra/dev.bicepparam",
        "infra/test.bicepparam",
        "infra/prod.bicepparam",
        "infra/dev.tfvars",
        "nomain/dev.bicepparam",
        "stacks/app/main.bicep",
        "stacks/app/params/dev.json",
        ".terraform.lock.hcl",
        "dev.tfvars",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return root


def deploy_inputs(output: Path, changes: dict[str, str]) -> dict[str, str]:
    return {
        "ENVIRONMENT": "dev",
        "IAC": "bicep",
        "WORKING_DIRECTORY": "infra",
        "PARAMETERS": "",
        "RESOURCE_GROUP": "rg-app",
        "IMAGE": "",
        "HEALTH_URL": "",
        "PROTECTED": "false",
        "BICEP_VERSION": "0.48.1",
        "TERRAFORM_VERSION": "1.16.7",
        "TFSTATE_STORAGE_ACCOUNT": "stdeliverystate",
        "TFSTATE_CONTAINER": "tfstate",
        "EVENT_NAME": "push",
        "HEAD_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY": REPOSITORY,
        "SYSTEM_PULLREQUEST_ISFORK": "False",
        "BUILD_REASON": "Manual",
        "SYSTEM_PULLREQUEST_PULLREQUESTID": "",
        "DEPLOY_BRANCH": "",
        "GITHUB_OUTPUT": output.as_posix(),
        **changes,
    }


@pytest.mark.parametrize(
    ("changes", "parameters", "protected", "artifact", "state_key"),
    [
        pytest.param(
            {},
            "dev.bicepparam",
            "false",
            "dev-infra",
            "infra/dev.tfstate",
            id="bicep-defaults",
        ),
        pytest.param(
            {"ENVIRONMENT": "prod"},
            "prod.bicepparam",
            "true",
            "prod-infra",
            "infra/prod.tfstate",
            id="prod-always-protected",
        ),
        pytest.param(
            {"ENVIRONMENT": "test", "PROTECTED": "true"},
            "test.bicepparam",
            "true",
            "test-infra",
            "infra/test.tfstate",
            id="explicitly-protected",
        ),
        pytest.param(
            {
                "WORKING_DIRECTORY": "stacks/app",
                "PARAMETERS": "params/dev.json",
                "IMAGE": DIGEST,
            },
            "params/dev.json",
            "false",
            "dev-stacks-app",
            "stacks/app/dev.tfstate",
            id="nested-json-and-image",
        ),
        pytest.param(
            TERRAFORM_ROOT,
            "dev.tfvars",
            "false",
            "dev-root",
            "dev.tfstate",
            id="terraform-root",
        ),
    ],
)
def test_deploy_inputs_resolve_defaults_on_both_platforms(
    bash: str,
    deploy_tree: Path,
    tmp_path: Path,
    changes: dict[str, str],
    parameters: str,
    protected: str,
    artifact: str,
    state_key: str,
) -> None:
    output = tmp_path / "github-output"
    env = deploy_inputs(output, changes)
    result = run(bash, script(DEPLOY, "Validate inputs"), deploy_tree, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_text(encoding="utf-8").splitlines() == [
        f"parameters={parameters}",
        f"protected={protected}",
        f"artifact=delivery-azure-deploy-{artifact}",
        f"state-key={state_key}",
    ]
    result = run(
        bash, script(ADO_DEPLOY, "Validate deployment inputs"), deploy_tree, env
    )
    assert result.returncode == 0, result.stdout + result.stderr
    prefix = "##vso[task.setvariable variable="
    assert [line for line in result.stdout.splitlines() if prefix in line] == [
        f"{prefix}deployParameters;isreadonly=true]{parameters}",
        f"{prefix}deployStateKey;isreadonly=true]{state_key}",
    ]


@pytest.mark.parametrize("mode", ["preview", "deploy"])
def test_ado_deploy_mode_accepts_only_the_deploy_branch(
    bash: str, deploy_tree: Path, tmp_path: Path, mode: str
) -> None:
    """The step guard passes both modes from the configured branch outside a PR."""
    env = deploy_inputs(
        tmp_path / "github-output",
        {
            "MODE": mode,
            "DEPLOY_BRANCH": "refs/heads/main",
            "BUILD_SOURCEBRANCH": "refs/heads/main",
            "BUILD_REASON": "IndividualCI",
        },
    )
    result = run(
        bash, script(ADO_DEPLOY, "Validate deployment inputs"), deploy_tree, env
    )
    assert result.returncode == 0, result.stdout + result.stderr


_BOTH = ("github", "ado")
_INPUT_FAILURES = [
    ("uppercase-environment", {"ENVIRONMENT": "Dev"}, "environment must be", _BOTH),
    ("missing-environment", {"ENVIRONMENT": ""}, "environment must be", _BOTH),
    ("long-environment", {"ENVIRONMENT": "a" * 33}, "environment must be", _BOTH),
    (
        "injected-environment",
        {"ENVIRONMENT": "dev;touch SHOULD_NOT_EXIST"},
        "environment must be",
        _BOTH,
    ),
    ("unknown-iac", {"IAC": "arm"}, "iac must be bicep or terraform", _BOTH),
    (
        "parent-directory",
        {"WORKING_DIRECTORY": "../infra"},
        "repository-relative",
        _BOTH,
    ),
    (
        "absolute-directory",
        {"WORKING_DIRECTORY": "/infra"},
        "repository-relative",
        _BOTH,
    ),
    ("trailing-slash", {"WORKING_DIRECTORY": "infra/"}, "repository-relative", _BOTH),
    ("parent-parameters", {"PARAMETERS": "../dev.tfvars"}, "must be relative", _BOTH),
    ("wrong-extension", {"PARAMETERS": "dev.tfvars"}, ".bicepparam/.json", _BOTH),
    ("missing-parameters", {"ENVIRONMENT": "qa"}, "Parameters file not found", _BOTH),
    ("missing-template", {"WORKING_DIRECTORY": "nomain"}, "template not found", _BOTH),
    ("missing-resource-group", {"RESOURCE_GROUP": ""}, "required for Bicep", _BOTH),
    (
        "invalid-resource-group",
        {"RESOURCE_GROUP": "rg-app."},
        "required for Bicep",
        _BOTH,
    ),
    ("floating-bicep", {"BICEP_VERSION": "latest"}, "exact version", _BOTH),
    (
        "terraform-resource-group",
        TERRAFORM_ROOT | {"RESOURCE_GROUP": "rg-app"},
        "is Bicep-only",
        _BOTH,
    ),
    (
        "missing-lock-file",
        {"IAC": "terraform", "RESOURCE_GROUP": ""},
        "Commit the provider lock file",
        _BOTH,
    ),
    ("tag-image", {"IMAGE": "registry.example/app:1.0"}, "image must be", _BOTH),
    (
        "short-digest",
        {"IMAGE": "registry.example/app@sha256:abc"},
        "image must be",
        _BOTH,
    ),
    (
        "registry-less-image",
        {"IMAGE": "app@sha256:" + "a" * 64},
        "image must be",
        _BOTH,
    ),
    (
        "plain-http-health-url",
        {"HEALTH_URL": "http://app.example.com/health/ready"},
        "must be an HTTPS URL",
        _BOTH,
    ),
    (
        "spaced-health-url",
        {"HEALTH_URL": "https://app.example.com/health ready"},
        "must be an HTTPS URL",
        _BOTH,
    ),
    (
        "floating-terraform",
        TERRAFORM_ROOT | {"TERRAFORM_VERSION": "1.16"},
        "exact version",
        ("github",),
    ),
    (
        "pull-request-target",
        {"EVENT_NAME": "pull_request_target"},
        "pull_request_target runs must not deploy",
        ("github",),
    ),
    ("github-fork", {"HEAD_REPOSITORY": "fork/repo"}, "Runs started from", ("github",)),
    ("ado-fork", {"SYSTEM_PULLREQUEST_ISFORK": "True"}, "Runs started from", ("ado",)),
    (
        "ado-pull-request-deploy",
        {"MODE": "deploy", "BUILD_REASON": "PullRequest"},
        "Pull-request builds must not preview or deploy",
        ("ado",),
    ),
    (
        "ado-pull-request-preview",
        {"MODE": "preview", "BUILD_REASON": "PullRequest"},
        "Pull-request builds must not preview or deploy",
        ("ado",),
    ),
    (
        "ado-pull-request-id-preview",
        {"MODE": "preview", "SYSTEM_PULLREQUEST_PULLREQUESTID": "42"},
        "Pull-request builds must not preview or deploy",
        ("ado",),
    ),
    (
        "ado-other-branch-deploy",
        {
            "MODE": "deploy",
            "DEPLOY_BRANCH": "refs/heads/main",
            "BUILD_SOURCEBRANCH": "refs/heads/feature",
        },
        "Only refs/heads/main may preview or deploy",
        ("ado",),
    ),
    (
        "ado-other-branch-preview",
        {
            "MODE": "preview",
            "DEPLOY_BRANCH": "refs/heads/main",
            "BUILD_SOURCEBRANCH": "refs/heads/feature",
        },
        "Only refs/heads/main may preview or deploy",
        ("ado",),
    ),
    (
        "ado-malformed-deploy-branch",
        {
            "MODE": "deploy",
            "DEPLOY_BRANCH": "main",
            "BUILD_SOURCEBRANCH": "main",
        },
        "deployBranch must be a full ref",
        ("ado",),
    ),
    (
        "missing-state-account",
        TERRAFORM_ROOT | {"TFSTATE_STORAGE_ACCOUNT": ""},
        "tfstateStorageAccount is required",
        ("ado",),
    ),
    (
        "invalid-state-container",
        TERRAFORM_ROOT | {"TFSTATE_CONTAINER": "-state"},
        "tfstateContainer is not a valid",
        ("ado",),
    ),
]


@pytest.mark.parametrize(
    ("platform", "changes", "error"),
    [
        pytest.param(platform, changes, error, id=f"{platform}-{name}")
        for name, changes, error, platforms in _INPUT_FAILURES
        for platform in platforms
    ],
)
def test_deploy_inputs_fail_closed_before_any_output(
    bash: str,
    deploy_tree: Path,
    tmp_path: Path,
    platform: str,
    changes: dict[str, str],
    error: str,
) -> None:
    output = tmp_path / "github-output"
    relative, name, marker = (
        (DEPLOY, "Validate inputs", "::error::")
        if platform == "github"
        else (ADO_DEPLOY, "Validate deployment inputs", "##vso[task.logissue")
    )
    result = run(
        bash, script(relative, name), deploy_tree, deploy_inputs(output, changes)
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert marker in result.stdout
    assert error in result.stdout
    assert not output.exists()
    assert "setvariable" not in result.stdout
    assert not (deploy_tree / "SHOULD_NOT_EXIST").exists()


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        pytest.param({"TFSTATE_STORAGE_ACCOUNT": ""}, None, id="bicep-needs-no-state"),
        pytest.param({"IAC": "terraform"}, None, id="terraform"),
        pytest.param({"PREVIEWED_SUBSCRIPTION": GUID}, None, id="same-subscription"),
        pytest.param({"ARM_CLIENT_ID": ""}, "AZURE_CLIENT_ID", id="missing-client"),
        pytest.param({"ARM_TENANT_ID": "tenant"}, "AZURE_TENANT_ID", id="bad-tenant"),
        pytest.param(
            {"ARM_SUBSCRIPTION_ID": ""},
            "AZURE_SUBSCRIPTION_ID",
            id="missing-subscription",
        ),
        pytest.param(
            {"PREVIEWED_SUBSCRIPTION": GUID[:-1] + "2"},
            "changed after the preview",
            id="switched-subscription",
        ),
        pytest.param(
            {"IAC": "terraform", "TFSTATE_STORAGE_ACCOUNT": ""},
            "TFSTATE_STORAGE_ACCOUNT",
            id="missing-state-account",
        ),
        pytest.param(
            {"IAC": "terraform", "TFSTATE_STORAGE_ACCOUNT": "State-Account"},
            "TFSTATE_STORAGE_ACCOUNT",
            id="invalid-state-account",
        ),
        pytest.param(
            {"IAC": "terraform", "TFSTATE_CONTAINER": "st"},
            "TFSTATE_CONTAINER",
            id="short-container",
        ),
        pytest.param(
            {"IAC": "terraform", "TFSTATE_CONTAINER": "a--b"},
            "TFSTATE_CONTAINER",
            id="double-hyphen-container",
        ),
    ],
)
def test_environment_variables_are_checked_before_login(
    bash: str, tmp_path: Path, changes: dict[str, str], error: str | None
) -> None:
    github_env = tmp_path / "github-env"
    env = {
        "ENVIRONMENT": "dev",
        "IAC": "bicep",
        "ARM_CLIENT_ID": GUID,
        "ARM_TENANT_ID": GUID,
        "ARM_SUBSCRIPTION_ID": GUID,
        "PREVIEWED_SUBSCRIPTION": "",
        "TFSTATE_STORAGE_ACCOUNT": "stdeliverystate",
        "TFSTATE_CONTAINER": "tfstate",
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_ENV": github_env.as_posix(),
        **changes,
    }
    result = run(bash, script(DEPLOY, "Check environment configuration"), tmp_path, env)
    if error is None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert github_env.read_text(encoding="utf-8") == (
            f"AZURE_CONFIG_DIR={tmp_path.as_posix()}/azure-cli\n"
        )
    else:
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::" in result.stdout
        assert error in result.stdout
        assert not github_env.exists()


@pytest.mark.parametrize(
    ("backend", "status", "returncode"),
    [
        pytest.param("azurerm", "0", 0, id="azurerm"),
        pytest.param("local", "0", 1, id="local-backend"),
        pytest.param("", "0", 1, id="no-backend"),
        pytest.param("azurerm", "17", 17, id="init-failure"),
    ],
)
def test_github_terraform_requires_remote_state_and_applies_saved_plan(
    bash: str, tmp_path: Path, backend: str, status: str, returncode: int
) -> None:
    log = tmp_path / "terraform.log"
    plan = f"{tmp_path.as_posix()}/delivery-azure-deploy/tfplan"
    env = {
        "TFSTATE_STORAGE_ACCOUNT": "stdeliverystate",
        "TFSTATE_CONTAINER": "tfstate",
        "STATE_KEY": "infra/dev.tfstate",
        "PARAMETERS": "dev.tfvars",
        "IMAGE": DIGEST,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "TOOL_LOG": log.as_posix(),
        "BACKEND": backend,
        "TOOL_STATUS": status,
    }
    body = TERRAFORM_STUB + script(DEPLOY, "Initialize Terraform state")
    result = run(bash, body, tmp_path, env)
    assert result.returncode == returncode, result.stdout + result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        (
            "init -input=false -lockfile=readonly"
            " -backend-config=storage_account_name=stdeliverystate"
            " -backend-config=container_name=tfstate"
            " -backend-config=key=infra/dev.tfstate"
        )
    ]
    if returncode == 1:
        assert 'backend "azurerm"' in result.stdout
    if returncode:
        return
    for name in ("Terraform plan", "Apply saved plan"):
        result = run(bash, TERRAFORM_STUB + script(DEPLOY, name), tmp_path, env)
        assert result.returncode == 0, result.stdout + result.stderr
    assert log.read_text(encoding="utf-8").splitlines()[1:] == [
        f"plan -input=false -var-file=dev.tfvars -out={plan} -var=container_image={DIGEST}",
        f"apply -input=false {plan}",
    ]


@pytest.mark.parametrize("parameters", ["dev.bicepparam", "dev.json"])
@pytest.mark.parametrize("image", ["", DIGEST], ids=["no-image", "image"])
def test_github_bicep_deploys_exactly_the_compiled_preview(
    bash: str, tmp_path: Path, parameters: str, image: str
) -> None:
    (tmp_path / "dev.json").write_text('{"parameters": {}}\n', encoding="utf-8")
    log = tmp_path / "az.log"
    out = f"{tmp_path.as_posix()}/delivery-azure-deploy"
    env = {
        "ENVIRONMENT": "prod",
        "PARAMETERS": parameters,
        "RESOURCE_GROUP": "rg-app",
        "IMAGE": image,
        "BICEP_VERSION": "0.48.1",
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_RUN_ID": "42",
        "GITHUB_RUN_ATTEMPT": "2",
        "TOOL_LOG": log.as_posix(),
    }
    override = f" --parameters containerImage={image}" if image else ""
    for name in ("Compile and what-if", "Deploy previewed template"):
        result = run(bash, AZ_STUB + script(DEPLOY, name), tmp_path, env)
        assert result.returncode == 0, result.stdout + result.stderr
    compile_parameters = (
        [f"bicep build-params --file dev.bicepparam --outfile {out}/params.json"]
        if parameters.endswith(".bicepparam")
        else []
    )
    files = f" --template-file {out}/template.json --parameters {out}/params.json"
    assert log.read_text(encoding="utf-8").splitlines() == [
        "bicep install --version v0.48.1",
        f"bicep build --file main.bicep --outfile {out}/template.json",
        *compile_parameters,
        f"deployment group what-if --resource-group rg-app{files}{override}",
        (
            "deployment group create --resource-group rg-app --name delivery-prod-42-2"
            f"{files}{override} --query properties.provisioningState --output tsv"
        ),
    ]
    expected = "compiled\n" if compile_parameters else '{"parameters": {}}\n'
    assert (tmp_path / "delivery-azure-deploy/params.json").read_text(
        encoding="utf-8"
    ) == expected


@pytest.mark.parametrize(
    ("mode", "fail_on", "returncode"),
    [
        pytest.param("preview", "", 0, id="preview"),
        pytest.param("preview", "what-if", 23, id="what-if-failure"),
        pytest.param("deploy", "", 0, id="deploy"),
        pytest.param("deploy", "group create", 23, id="deploy-failure"),
    ],
)
def test_ado_bicep_preview_and_deploy_share_one_artifact(
    bash: str, tmp_path: Path, mode: str, fail_on: str, returncode: int
) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "stale.json").write_text("{}", encoding="utf-8")
    log = tmp_path / "az.log"
    env = {
        "MODE": mode,
        "ENVIRONMENT": "dev",
        "ARTIFACT": artifact.as_posix(),
        "PARAMETERS": "dev.bicepparam",
        "RESOURCE_GROUP": "rg-app",
        "IMAGE": DIGEST,
        "BICEP_VERSION": "0.48.1",
        "BUILD_BUILDID": "7",
        "SYSTEM_JOBATTEMPT": "1",
        "TOOL_LOG": log.as_posix(),
        "FAIL_ON": fail_on,
    }
    body = AZ_STUB + script(
        ADO_DEPLOY, "Bicep ${{ parameters.mode }} ${{ parameters.environment }}"
    )
    result = run(bash, body, tmp_path, env)
    assert result.returncode == returncode, result.stdout + result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    files = (
        f" --template-file {artifact.as_posix()}/template.json"
        f" --parameters {artifact.as_posix()}/params.json"
        f" --parameters containerImage={DIGEST}"
    )
    if mode == "preview":
        assert not (artifact / "stale.json").exists()
        assert calls[0] == "bicep install --version v0.48.1"
        assert calls[-1] == f"deployment group what-if --resource-group rg-app{files}"
    else:
        assert (artifact / "stale.json").exists()
        assert calls == [
            (
                "deployment group create --resource-group rg-app --name delivery-dev-7-1"
                f"{files} --query properties.provisioningState --output tsv"
            )
        ]


@pytest.mark.parametrize(
    ("mode", "connection", "backend", "returncode"),
    [
        pytest.param("preview", "connection-id", "azurerm", 0, id="preview"),
        pytest.param("deploy", "connection-id", "azurerm", 0, id="deploy"),
        pytest.param("preview", "connection-id", "local", 1, id="local-backend"),
        pytest.param("preview", "", "azurerm", 1, id="no-connection-id"),
    ],
)
def test_ado_terraform_uses_the_service_connection_identity(
    bash: str,
    tmp_path: Path,
    mode: str,
    connection: str,
    backend: str,
    returncode: int,
) -> None:
    artifact = f"{tmp_path.as_posix()}/artifact"
    log = tmp_path / "terraform.log"
    arm = tmp_path / "arm.log"
    account = r"""az() {
      case "$4" in
        user.name) echo client-from-connection ;;
        tenantId) echo tenant-from-connection ;;
        id) echo subscription-from-connection ;;
      esac
    }
    """
    env = {
        "MODE": mode,
        "ARTIFACT": artifact,
        "PARAMETERS": "dev.tfvars",
        "STATE_KEY": "infra/dev.tfstate",
        "IMAGE": "",
        "TFSTATE_STORAGE_ACCOUNT": "stdeliverystate",
        "TFSTATE_CONTAINER": "tfstate",
        "AZURESUBSCRIPTION_SERVICE_CONNECTION_ID": connection,
        "TOOL_LOG": log.as_posix(),
        "ARM_LOG": arm.as_posix(),
        "BACKEND": backend,
    }
    body = (
        account
        + TERRAFORM_STUB
        + script(
            ADO_DEPLOY, "Terraform ${{ parameters.mode }} ${{ parameters.environment }}"
        )
    )
    result = run(bash, body, tmp_path, env)
    assert result.returncode == returncode, result.stdout + result.stderr
    if not connection:
        assert "service connection ID" in result.stdout
        assert not log.exists()
        return
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls[0].startswith("init -input=false -lockfile=readonly ")
    assert calls[0].endswith(" -backend-config=key=infra/dev.tfstate")
    assert set(arm.read_text(encoding="utf-8").splitlines()) >= {
        "ARM_CLIENT_ID=client-from-connection",
        "ARM_TENANT_ID=tenant-from-connection",
        "ARM_SUBSCRIPTION_ID=subscription-from-connection",
        "ARM_OIDC_AZURE_SERVICE_CONNECTION_ID=connection-id",
    }
    if returncode:
        assert 'backend "azurerm"' in result.stdout
        assert len(calls) == 1
    elif mode == "preview":
        assert calls[1:] == [
            f"plan -input=false -var-file=dev.tfvars -out={artifact}/tfplan"
        ]
    else:
        assert calls[1:] == [f"apply -input=false {artifact}/tfplan"]


@dataclass(kw_only=True, slots=True)
class FakeGitHub:
    """One canned GitHub REST response and the requests that reached it.

    A mutable test double, not a record: each test sets the canned response after
    the loopback server has started.
    """

    url: str = ""
    status: int = 200
    body: bytes = b"{}"
    requests: list[tuple[str, str]] = field(default_factory=list)


@pytest.fixture
def github_api() -> Iterator[FakeGitHub]:
    api = FakeGitHub()

    class Environment(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            """Keep request logs out of test output."""

        def do_GET(self) -> None:
            api.requests.append((self.path, self.headers.get("Authorization", "")))
            self.send_response(api.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(api.body)))
            self.end_headers()
            self.wfile.write(api.body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Environment)
    api.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield api
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


_REVIEWERS = {"type": "User", "reviewer": {"login": "approver"}}
_RESTRICTED = {"protected_branches": True, "custom_branch_policies": False}


def _protection(
    *,
    prevent_self_review: bool = True,
    can_admins_bypass: bool | None = False,
    branches: dict[str, bool] | None = _RESTRICTED,
) -> dict[str, object]:
    """Return reviewed environment settings with one protection changed."""
    settings: dict[str, object] = {
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": prevent_self_review,
                "reviewers": [_REVIEWERS],
            }
        ],
        "deployment_branch_policy": branches,
    }
    if can_admins_bypass is not None:
        settings["can_admins_bypass"] = can_admins_bypass
    return settings


@pytest.mark.parametrize(
    ("protected", "status", "settings", "returncode", "messages"),
    [
        pytest.param(
            "true",
            200,
            {
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "prevent_self_review": True,
                        "reviewers": [_REVIEWERS],
                    }
                ],
                "can_admins_bypass": False,
                "deployment_branch_policy": {"protected_branches": True},
            },
            0,
            ("requires reviewers",),
            id="reviewed",
        ),
        pytest.param(
            "true",
            200,
            {
                "protection_rules": [
                    {"type": "required_reviewers", "reviewers": [_REVIEWERS]}
                ],
                "can_admins_bypass": True,
                "deployment_branch_policy": None,
            },
            1,
            ("Prevent self-review", "bypass", "Restrict deployment branches"),
            id="reviewed-with-every-gap",
        ),
        pytest.param(
            "true",
            200,
            _protection(prevent_self_review=False),
            1,
            ("Prevent self-review",),
            id="self-review-allowed",
        ),
        pytest.param(
            "true",
            200,
            _protection(can_admins_bypass=True),
            1,
            ("Allow administrators to bypass",),
            id="admin-bypass",
        ),
        pytest.param(
            "true",
            200,
            _protection(can_admins_bypass=None),
            1,
            ("Allow administrators to bypass",),
            id="admin-bypass-unreported",
        ),
        pytest.param(
            "true",
            200,
            _protection(branches=None),
            1,
            ("Restrict deployment branches",),
            id="any-branch",
        ),
        pytest.param(
            "true",
            200,
            _protection(
                branches={"protected_branches": False, "custom_branch_policies": False}
            ),
            1,
            ("Restrict deployment branches",),
            id="no-branch-rule",
        ),
        pytest.param(
            "true",
            200,
            _protection(
                branches={"protected_branches": False, "custom_branch_policies": True}
            ),
            0,
            ("requires reviewers",),
            id="selected-branches",
        ),
        pytest.param(
            "false",
            200,
            {
                "protection_rules": [],
                "can_admins_bypass": True,
                "deployment_branch_policy": None,
            },
            0,
            ("reviewer rules: 0",),
            id="unprotected-dev-stays-usable",
        ),
        pytest.param(
            "true",
            200,
            {"protection_rules": []},
            1,
            ("no required reviewers",),
            id="no-rules",
        ),
        pytest.param(
            "true",
            200,
            {"protection_rules": [{"type": "wait_timer", "wait_timer": 30}]},
            1,
            ("no required reviewers",),
            id="wait-timer-only",
        ),
        pytest.param(
            "true",
            200,
            {"protection_rules": [{"type": "required_reviewers", "reviewers": []}]},
            1,
            ("no required reviewers",),
            id="empty-reviewers",
        ),
        pytest.param(
            "false", 200, {}, 0, ("reviewer rules: 0",), id="unprotected-exists"
        ),
        pytest.param(
            "false", 404, {}, 1, ("does not exist", "GitHub Enterprise"), id="missing"
        ),
        pytest.param("true", 403, {}, 1, ("HTTP 403", "actions: read"), id="forbidden"),
        pytest.param("true", 200, None, 1, ("Cannot verify",), id="invalid-json"),
    ],
)
def test_protected_environment_requires_reviewers_or_fails_closed(
    tmp_path: Path,
    github_api: FakeGitHub,
    protected: str,
    status: int,
    settings: dict[str, object] | None,
    returncode: int,
    messages: tuple[str, ...],
) -> None:
    github_api.status = status
    github_api.body = b"not json" if settings is None else json.dumps(settings).encode()
    result = reviewer_check(tmp_path, github_api.url, protected)
    assert result.returncode == returncode, result.stdout + result.stderr
    for message in messages:
        assert message in result.stdout
    assert github_api.requests == [
        (f"/repos/{REPOSITORY}/environments/prod", f"Bearer {FAKE_BEARER}")
    ]
    assert FAKE_BEARER not in result.stdout + result.stderr


def test_unreachable_environment_api_fails_closed(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    result = reviewer_check(tmp_path, f"http://127.0.0.1:{port}", "true")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Cannot verify environment 'prod'" in result.stdout
    assert "GitHub Enterprise" in result.stdout
    assert FAKE_BEARER not in result.stdout + result.stderr


def reviewer_check(
    tmp_path: Path, api_url: str, protected: str
) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "require_reviewers.py"
    source.write_text(
        script(DEPLOY, "Require a reviewed environment"), encoding="utf-8"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.lower().endswith("_proxy")
    }
    return subprocess.run(  # noqa: S603 - this interpreter, a loopback stub only
        [sys.executable, "-I", str(source)],
        cwd=tmp_path,
        env={
            **env,
            "NO_PROXY": "*",
            "GITHUB_API_URL": api_url,
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_TOKEN": FAKE_BEARER,
            "ENVIRONMENT": "prod",
            "PROTECTED": protected,
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
