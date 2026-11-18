"""Keep the mirrored GitHub and Azure DevOps deploy input validation equal.

Both hosts keep the Bash inline: the reusable workflow checks out only the caller and
consumers reference the Azure DevOps template repository without checking it out, so a
shared script file would not be on disk. This test replaces that shared file.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from delivery_tools.catalog import ROOT
from delivery_tools.documents import read_yaml

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.unit
GITHUB: Final[Path] = ROOT.parents[1] / ".github/workflows/delivery-azure-deploy.yml"
ADO: Final[Path] = ROOT / "azure-devops/steps/azure-deploy.yml"
SHARED: Final[tuple[str, ...]] = (
    "name_pattern",
    "path_pattern",
    "group_pattern",
    "image_pattern",
)
_ASSIGNMENT = re.compile(r"^\s*(\w+_pattern)='([^']*)'\s*$")


def _walk(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _script(path: Path, name: str, key: str) -> str:
    doc = read_yaml(path, workflow=True)
    (script,) = (
        str(node[key])
        for node in _walk(doc)
        if node.get("name", node.get("displayName")) == name and key in node
    )
    return script


def _patterns(script: str) -> dict[str, str]:
    matches = (_ASSIGNMENT.match(line) for line in script.splitlines())
    return {match[1]: match[2] for match in matches if match is not None}


def _relative(script: str) -> str:
    lines = [line.strip() for line in script.splitlines()]
    return lines[lines.index("relative() {") + 1]


@pytest.fixture(scope="module")
def scripts() -> tuple[str, str]:
    return (
        _script(GITHUB, "Validate inputs", "run"),
        _script(ADO, "Validate deployment inputs", "bash"),
    )


def test_shared_patterns_are_identical(scripts: tuple[str, str]) -> None:
    github, ado = (_patterns(script) for script in scripts)
    assert set(SHARED) <= github.keys()
    assert set(SHARED) <= ado.keys()
    assert {key: github[key] for key in SHARED} == {key: ado[key] for key in SHARED}


def test_relative_path_rule_is_identical(scripts: tuple[str, str]) -> None:
    github, ado = (_relative(script) for script in scripts)
    assert github == ado
    assert "*..*" in github


@pytest.mark.parametrize(
    "rule",
    [
        "fail \"environment must be 1-32 lowercase letters, digits, '-' or '_'\"",
        'bicep) parameters="${PARAMETERS:-${ENVIRONMENT}.bicepparam}" ;;',
        'terraform) parameters="${PARAMETERS:-${ENVIRONMENT}.tfvars}" ;;',
        "bicep:*.bicepparam | bicep:*.json | terraform:*.tfvars | terraform:*.tfvars.json) ;;",
        '[[ -f "${WORKING_DIRECTORY}/.terraform.lock.hcl" ]] ||',
        '[[ "$BICEP_VERSION" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]] ||',
        'if [[ -n "$HEALTH_URL" && ! "$HEALTH_URL" =~ ^https://[^[:space:]]+$ ]]; then',
    ],
)
def test_shared_rules_present_in_both(scripts: tuple[str, str], rule: str) -> None:
    github, ado = ([line.strip() for line in script.splitlines()] for script in scripts)
    assert rule in github
    assert rule in ado


@pytest.mark.parametrize("path", [GITHUB, ADO])
def test_duplication_is_documented_at_both_copies(path: Path) -> None:
    assert "test_pipeline_input_parity.py" in path.read_text(encoding="utf-8")
