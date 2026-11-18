"""Native installed-tool proof, using no providers, modules, state or resources."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from delivery_tools.catalog import ROOT

pytestmark = pytest.mark.integration


def local_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    if name == "bicep":
        candidate = Path.home() / ".azure/bin/bicep.exe"
        if candidate.is_file():
            return str(candidate)
    pytest.skip(f"Installed {name} unavailable; no install or download is attempted")


def invoke(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed tools and resource-free fixture args
        command,
        cwd=cwd,
        env={
            **os.environ,
            "CHECKPOINT_DISABLE": "1",
            "TF_IN_AUTOMATION": "1",
            "TF_DATA_DIR": str(cwd / ".terraform"),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_terraform_native_validation_without_init(tmp_path: Path) -> None:
    executable = local_tool("terraform")
    shutil.copyfile(ROOT / "fixtures/terraform/main.tf", tmp_path / "main.tf")
    result = invoke([executable, "fmt", "-check", "-diff"], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    # No init is needed: the fixture declares no providers, modules or backend.
    result = invoke([executable, "validate", "-json"], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["valid"] is True
    assert not list(tmp_path.glob("*.tfstate*"))


def test_bicep_native_compile_and_parameters_without_restore(tmp_path: Path) -> None:
    executable = local_tool("bicep")
    for path in (ROOT / "fixtures/bicep").iterdir():
        shutil.copyfile(path, tmp_path / path.name)
    result = invoke([executable, "format", "main.bicep", "--stdout"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (tmp_path / "main.bicep").read_text(encoding="utf-8")
    for command in ("lint", "build"):
        args = [executable, command, "main.bicep", "--no-restore"]
        if command == "build":
            args.append("--stdout")
        result = invoke(args, tmp_path)
        assert result.returncode == 0, result.stderr
    compiled = json.loads(result.stdout)
    assert compiled["resources"] == []
    result = invoke(
        [executable, "build-params", "main.bicepparam", "--no-restore", "--stdout"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "ci" in result.stdout


def test_caller_owned_bicepparam_compiles_without_a_template(tmp_path: Path) -> None:
    # The deploy workflow compiles `using none` files with build-params --outfile.
    executable = local_tool("bicep")
    shutil.copyfile(
        ROOT / "fixtures/bicep/deploy.bicepparam", tmp_path / "dev.bicepparam"
    )
    result = invoke(
        [
            executable,
            "build-params",
            "dev.bicepparam",
            "--no-restore",
            "--outfile",
            "params.json",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    compiled = json.loads((tmp_path / "params.json").read_text(encoding="utf-8"))
    assert compiled["parameters"] == {"label": {"value": "ci"}}
