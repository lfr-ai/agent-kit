"""Explicit-input backend checkers reject their actual negative contracts."""

import json
from pathlib import Path
import subprocess
import sys

_SKILLS = Path(__file__).resolve().parents[3] / "packages/backend/.apm/skills"


def _run(
    skill: str, filename: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed first-party scripts, synthetic inputs
        [sys.executable, str(_SKILLS / skill / "assets" / filename), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_response_model_checker_reports_redundancy_not_ordinary_annotations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "api.py"
    path.write_text(
        "@router.get('/items')\ndef endpoint() -> Widget:\n    return value\n",
        encoding="utf-8",
    )
    assert (
        _run(
            "kit-api-contracts", "check_response_model_redundancy.py", str(path)
        ).returncode
        == 0
    )
    path.write_text(
        "@router.get('/items', response_model=Widget)\n"
        "def endpoint() -> Widget:\n    return value\n",
        encoding="utf-8",
    )
    result = _run("kit-api-contracts", "check_response_model_redundancy.py", str(path))
    assert result.returncode == 1, result.stderr
    assert "response_model" in result.stdout


def test_openapi_checker_distinguishes_stable_and_removed_paths(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    document = {
        "openapi": "3.1.0",
        "info": {"title": "Synthetic API", "version": "1"},
        "paths": {"/items": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }
    old.write_text(json.dumps(document), encoding="utf-8")
    new.write_text(json.dumps(document), encoding="utf-8")
    arguments = (str(old), str(new))
    assert _run("kit-api-contracts", "compare_openapi.py", *arguments).returncode == 0
    document["paths"] = {}
    new.write_text(json.dumps(document), encoding="utf-8")
    result = _run("kit-api-contracts", "compare_openapi.py", *arguments)
    assert result.returncode == 1, result.stderr
    assert "breaking" in result.stdout
    assert "/items" in result.stdout


def test_openapi_checker_rejects_non_object_paths(tmp_path: Path) -> None:
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text('{"paths":{}}', encoding="utf-8")
    new.write_text('{"paths":null}', encoding="utf-8")
    result = _run("kit-api-contracts", "compare_openapi.py", str(old), str(new))
    assert result.returncode == 2
    assert "cannot compare" in result.stderr
    assert result.stdout == ""


def test_port_checker_requires_an_adapter_with_all_members(tmp_path: Path) -> None:
    core = tmp_path / "core"
    adapters = tmp_path / "adapters"
    core.mkdir()
    adapters.mkdir()
    (core / "ports.py").write_text(
        "from typing import Protocol\nclass WidgetPort(Protocol):\n"
        "    def save(self) -> None: ...\n",
        encoding="utf-8",
    )
    adapter = adapters / "widgets.py"
    adapter.write_text(
        "class WidgetAdapter:\n    def save(self) -> None:\n        pass\n",
        encoding="utf-8",
    )
    arguments = ("--core", str(core), "--adapters", str(adapters))
    assert (
        _run("kit-domain-model", "check_port_adapter_binding.py", *arguments).returncode
        == 0
    )
    adapter.write_text("class WidgetAdapter:\n    pass\n", encoding="utf-8")
    result = _run("kit-domain-model", "check_port_adapter_binding.py", *arguments)
    assert result.returncode == 1, result.stderr
    assert "WidgetPort" in result.stdout
