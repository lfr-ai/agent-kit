"""Repository-scoped checkout discovery and explicit Windows user registration."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]


def test_task_context_uses_the_actual_checkout_not_a_machine_path() -> None:
    """Task defaults to its own root without hard-coding a machine path."""
    taskfile = yaml.safe_load((_ROOT / "Taskfile.yml").read_text(encoding="utf-8"))

    assert taskfile["env"]["AGENT_KIT_DIR"] == "{{.ROOT_DIR}}"
    assert taskfile["tasks"]["checkout:register"]["cmds"] == [
        "powershell -NoProfile -NonInteractive -File scripts/register_checkout.ps1"
    ]


def test_workspace_terminals_and_container_receive_the_checkout_path() -> None:
    """Workspace discovery remains relocatable on every supported platform."""
    settings = json.loads((_ROOT / ".vscode/settings.json").read_text(encoding="utf-8"))
    container = json.loads(
        (_ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")
    )

    for platform in ("windows", "linux", "osx"):
        assert settings[f"terminal.integrated.env.{platform}"] == {
            "AGENT_KIT_DIR": "${workspaceFolder}"
        }
    assert container["remoteEnv"]["AGENT_KIT_DIR"] == "${containerWorkspaceFolder}"


def test_persistent_registration_is_idempotent_and_supports_whatif() -> None:
    """Source checks do not claim a registry mutation was exercised."""
    script = (_ROOT / "scripts/register_checkout.ps1").read_text(encoding="utf-8")

    assert "SupportsShouldProcess" in script
    assert "$PSCmdlet.ShouldProcess" in script
    assert "if ($current -eq $checkout)" in script
    assert "[EnvironmentVariableTarget]::User" in script
    assert "[EnvironmentVariableTarget]::Machine" not in script
    assert "$PSScriptRoot" in script
    assert "setx" not in script


def test_matrix_runs_tox_without_parallel_environment_coverage_writers() -> None:
    """Tox environments run in order, not with concurrent shared reports."""
    taskfile = yaml.safe_load((_ROOT / "Taskfile.yml").read_text(encoding="utf-8"))

    assert taskfile["tasks"]["test:matrix"]["cmds"] == [
        "uv run --locked --no-sync tox {{.CLI_ARGS}}"
    ]


def test_windows_registration_whatif_never_runs_the_registry_write() -> None:
    """Execute the actual dry-run path when Windows PowerShell is available."""
    executable = shutil.which("powershell.exe")
    if executable is None:
        pytest.skip("Windows PowerShell is unavailable")
    result = subprocess.run(  # noqa: S603 - resolved PowerShell, fixed script and argv
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(_ROOT / "scripts/register_checkout.ps1"),
            "-WhatIf",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "AGENT_KIT_DIR" in result.stdout
    assert "Registered AGENT_KIT_DIR=" not in result.stdout
