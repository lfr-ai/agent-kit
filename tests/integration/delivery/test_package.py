"""Prove the package CLI works without either source checkout and fails on drift."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Final

import pytest

from delivery_tools.catalog import ROOT, WORKFLOW_FILES

pytestmark = pytest.mark.integration
WORKFLOW_ROOT: Final[Path] = ROOT.parents[1] / ".github/workflows"


@pytest.fixture
def package_copy(tmp_path: Path) -> Path:
    return Path(
        shutil.copytree(
            ROOT,
            tmp_path / "delivery",
            ignore=shutil.ignore_patterns("__pycache__", ".ruff_cache"),
        )
    )


def invoke(package_copy: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ""}
    return subprocess.run(  # noqa: S603 - fixed checker copied to a synthetic workspace
        [sys.executable, "-B", str(package_copy / "check.py"), *args],
        cwd=package_copy.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_relocated_package_cli_with_injected_workflows(
    package_copy: Path, tmp_path: Path
) -> None:
    workflows = tmp_path / "canonical-workflows"
    workflows.mkdir()
    for name in WORKFLOW_FILES:
        shutil.copyfile(WORKFLOW_ROOT / name, workflows / name)
    assert not list(package_copy.rglob("delivery-*.yml"))
    args = ("--workflow-root", str(workflows))
    result = invoke(package_copy, *args)
    assert result.returncode == 0, result.stderr
    assert "passed (offline)" in result.stdout
    catalog = (package_copy / "catalog.json").read_bytes()
    (package_copy / "catalog.json").unlink()
    result = invoke(package_copy, *args)
    assert result.returncode == 1
    assert "delivery:" in result.stderr
    result = invoke(package_copy, *args, "--write-catalog")
    assert result.returncode == 0, result.stderr
    assert (package_copy / "catalog.json").read_bytes() == catalog
    (workflows / "delivery-python-ci.yml").unlink()
    result = invoke(package_copy, *args, "--write-catalog")
    assert result.returncode == 1
    assert "Workflow inventory" in result.stderr
    assert (package_copy / "catalog.json").read_bytes() == catalog


def test_relocated_cli_requires_explicit_workflow_root(package_copy: Path) -> None:
    result = invoke(package_copy)
    assert result.returncode == 2
    assert "--workflow-root" in result.stderr
    result = invoke(package_copy, "--workflow-root", "missing")
    assert result.returncode == 1
    assert "Workflow inventory" in result.stderr


@pytest.mark.parametrize(
    ("text", "field"),
    [
        (
            "on: {workflow_call: {inputs: {pin: {type: number, default: bad}}}}",
            "default",
        ),
        ("on: [", "YAML"),
    ],
)
def test_invalid_metadata_cli_preserves_existing_catalog(
    package_copy: Path, tmp_path: Path, text: str, field: str
) -> None:
    workflows = tmp_path / "canonical-workflows"
    workflows.mkdir()
    for name in WORKFLOW_FILES:
        shutil.copyfile(WORKFLOW_ROOT / name, workflows / name)
    (workflows / "delivery-python-ci.yml").write_text(text, encoding="utf-8")
    catalog = package_copy / "catalog.json"
    before = catalog.read_bytes()
    result = invoke(package_copy, "--workflow-root", str(workflows), "--write-catalog")
    assert result.returncode == 1
    assert result.stderr.count("delivery:") == 1
    assert field in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert catalog.read_bytes() == before
