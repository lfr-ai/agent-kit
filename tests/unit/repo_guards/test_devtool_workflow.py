"""Keep developer entry points small without dropping repository checks."""

import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml
from identify.identify import tags_from_filename
from pre_commit.clientlib import load_config

_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "path",
    [
        ".agents/skills/kit-example/SKILL.md",
        ".claude/skills/kit-example/assets/check.py",
        ".claude/rules/kit-example.md",
        ".claude/agents/kit-example.md",
        ".github/agents/kit-example.agent.md",
        ".github/instructions/kit-example.instructions.md",
        "apm.lock.yaml",
        "uv.lock",
    ],
)
def test_owned_outputs_are_read_only_not_globally_exempt(path: str) -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    assert not re.search(config["exclude"], path)
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    mutators = {
        "trailing-whitespace",
        "end-of-file-fixer",
        "mixed-line-ending",
        "fix-byte-order-marker",
    }
    for identifier, hook in hooks.items():
        if identifier in mutators:
            assert re.search(hook["exclude"], path)
        else:
            assert not re.search(hook.get("exclude", "^$"), path), identifier
    assert hooks["uv-lock"]["files"] == r"^(pyproject\.toml|uv\.lock)$"


@pytest.mark.parametrize(
    "path",
    [
        ".apm/skills/kit-example/SKILL.md",
        "packages/backend/.apm/skills/kit-example/assets/check.py",
        ".github/workflows/ci.yml",
        ".claude/settings.json",
        ".agents/skills-extra/handwritten.md",
    ],
)
def test_owned_output_filter_does_not_hide_authored_files(path: str) -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "trailing-whitespace"
    )
    assert not re.search(hook["exclude"], path)


def test_exception_contract_rules_are_selected_without_exemptions() -> None:
    lint = tomllib.loads((_ROOT / "ruff.toml").read_text())["lint"]
    assert "TRY" in lint["extend-select"]
    ignored = [
        *lint.get("ignore", []),
        *lint.get("extend-ignore", []),
        *(
            rule
            for rules in lint.get("per-file-ignores", {}).values()
            for rule in rules
        ),
        *(
            rule
            for rules in lint.get("extend-per-file-ignores", {}).values()
            for rule in rules
        ),
    ]
    assert not any(
        selected.startswith(rule)
        for selected in ("TRY003", "TRY004")
        for rule in ignored
    )


def test_hooks_use_commit_stages_and_bun_without_redundant_defaults() -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    assert config["default_stages"] == ["pre-commit"]
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    assert all("manual" not in hook.get("stages", []) for hook in hooks.values())
    assert hooks["commitizen"]["stages"] == ["commit-msg"]
    assert hooks["jscpd"]["entry"] == "bunx --bun jscpd@5.4.1"
    assert "args" not in hooks["check-added-large-files"]
    assert "args" not in hooks["no-commit-to-branch"]
    assert "args" not in hooks["yamllint"]
    assert "args" not in hooks["cspell"]
    assert hooks["lychee-docker"]["entry"] == "lycheeverse/lychee:0.24.2"
    assert "toolkit-contract" in hooks
    assert "toolkit-drift" in hooks
    assert "toolkit-native-roles" in hooks


def test_task_and_editor_interfaces_only_expose_recurring_workflows() -> None:
    tasks = yaml.safe_load((_ROOT / "Taskfile.yml").read_text())["tasks"]
    assert set(tasks) == {
        "bootstrap",
        "lint",
        "format",
        "typecheck",
        "test",
        "verify",
        "precommit",
        "commit",
        "capabilities:build",
        "apm:smoke",
    }
    assert "{{.CLI_ARGS}}" in tasks["verify"]["cmds"][0]
    editor = json.loads((_ROOT / ".vscode/tasks.json").read_text())["tasks"]
    assert all(task["args"][0] in tasks for task in editor)
    assert len(editor) == len({task["args"][0] for task in editor})


def test_workspace_settings_stay_discoverable_and_strict_json() -> None:
    settings = _ROOT / ".vscode/settings.json"
    assert isinstance(json.loads(settings.read_text()), dict)
    assert "json" in tags_from_filename(str(settings))
    assert "json" not in tags_from_filename("settings.jsonc")
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text())
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "check-json"
    )
    assert "exclude" not in hook
