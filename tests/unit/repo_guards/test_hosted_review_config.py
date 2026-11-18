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
    # Auto review of non-draft pull requests is the CodeRabbit default.
    assert "auto_review" not in reviews
    instructions = reviews["path_instructions"]
    assert isinstance(instructions, list)
    by_path = {item["path"]: item["instructions"] for item in instructions}
    supply_chain = (
        "{.github/**,.pre-commit-config.yaml,Taskfile.yml,pyproject.toml,tox.ini,"
        "package.json,.devcontainer/**,.mcp.json}"
    )
    assert set(by_path) == {"**/*.py", ".vscode/**", supply_chain}
    assert "full commit SHAs" in by_path[supply_chain]
    assert "unlocked installs" in by_path[supply_chain]


def test_hosted_tools_complement_required_local_checks() -> None:
    reviews = _yaml(".coderabbit.yaml")["reviews"]
    assert isinstance(reviews, dict)
    tools = reviews["tools"]
    assert isinstance(tools, dict)
    # Hosted tools are enabled by default; only explicit opt-outs are configured.
    assert tools == {"flake8": {"enabled": False}, "pylint": {"enabled": False}}
    # CodeRabbit has no native ty integration; CI owns type correctness.
    assert "ty" not in tools
