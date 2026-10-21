"""Keep optional hosted review configs aligned with repository policy."""

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[3]


def _yaml(name: str) -> dict[str, object]:
    value = yaml.safe_load((_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_codecov_statuses_match_the_repository_coverage_policy() -> None:
    config = _yaml(".codecov.yml")
    coverage = config["coverage"]
    assert isinstance(coverage, dict)
    status = coverage["status"]
    assert isinstance(status, dict)
    project = status["project"]
    patch = status["patch"]
    assert isinstance(project, dict)
    assert isinstance(patch, dict)
    assert project["default"] == {"target": "auto", "threshold": "1%"}
    assert patch["default"] == {"target": "90%"}


def test_coderabbit_uses_strict_review_defaults_and_project_guidance() -> None:
    config = _yaml(".coderabbit.yaml")
    reviews = config["reviews"]
    assert isinstance(reviews, dict)
    assert reviews["profile"] == "assertive"
    assert reviews["request_changes_workflow"] is False
    assert reviews["allow_author_approval"] is False
    assert reviews["auto_review"] == {"enabled": True, "drafts": False}
    instructions = reviews["path_instructions"]
    assert isinstance(instructions, list)
    assert {item["path"] for item in instructions} == {"**/*.py", ".vscode/**"}
