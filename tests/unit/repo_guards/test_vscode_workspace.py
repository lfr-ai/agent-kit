"""Workspace editor settings match the repository toolchain without hiding source."""

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _json(name: str) -> dict[str, object]:
    value = json.loads((_ROOT / ".vscode" / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_settings_follow_the_documented_section_order() -> None:
    keys = list(_json("settings.json"))
    representatives = [
        "python.defaultInterpreterPath",
        "ruff.nativeServer",
        "editor.formatOnSave",
        "[python]",
        "files.associations",
        "chat.useAgentsMdFile",
        "search.exclude",
    ]
    positions = [keys.index(key) for key in representatives]
    assert positions == sorted(positions)


def test_canonical_sources_and_lockfiles_remain_visible() -> None:
    settings = _json("settings.json")
    for key in ("files.exclude", "search.exclude", "files.watcherExclude"):
        patterns = settings[key]
        assert isinstance(patterns, dict)
        for source in (
            ".apm",
            "packages",
            "src",
            "tests",
            "scripts",
            ".agents/knowledge-base",
            "uv.lock",
            "apm.lock.yaml",
            ".coveragerc",
        ):
            assert not any(
                patterns.get(pattern) is True
                for pattern in (source, f"**/{source}", f"**/{source}/**")
            ), (key, source)
    assert settings["files.readonlyInclude"] == {
        "**/.agents/skills/**": True,
        "**/.claude/skills/**": True,
    }
    for setting in ("files.exclude", "files.watcherExclude"):
        patterns = settings[setting]
        assert isinstance(patterns, dict)
        for tree in (".agents/skills", ".claude/skills"):
            assert patterns.get(f"**/{tree}") is not True
            assert patterns.get(f"**/{tree}/**") is not True


def test_language_formatters_have_a_declared_provider() -> None:
    settings = _json("settings.json")
    extensions = _json("extensions.json")
    recommended = extensions["recommendations"]
    unwanted = extensions["unwantedRecommendations"]
    assert isinstance(recommended, list)
    assert isinstance(unwanted, list)
    assert all(isinstance(name, str) for name in [*recommended, *unwanted])
    assert not set(recommended) & set(unwanted)
    assert "ms-azuretools.vscode-containers" in recommended
    assert {"charliermarsh.ruff", "astral-sh.ty", "ms-python.python"} <= set(
        recommended
    )
    # Ruff and ty own linting, formatting, imports and types; competitors stay off.
    assert {
        "ms-python.black-formatter",
        "ms-python.autopep8",
        "ms-python.flake8",
        "ms-python.isort",
        "ms-python.mypy-type-checker",
        "ms-python.pylint",
        "ms-python.vscode-pylance",
    } <= set(unwanted)
    for language in ("python", "json", "jsonc", "yaml", "toml", "markdown"):
        configuration = settings[f"[{language}]"]
        assert isinstance(configuration, dict)
        formatter = configuration["editor.defaultFormatter"]
        assert isinstance(formatter, str)
        assert formatter.startswith("vscode.") or formatter.casefold() in {
            name.casefold() for name in recommended
        }
    python = settings["[python]"]
    assert isinstance(python, dict)
    assert python["editor.codeActionsOnSave"] == {
        "source.fixAll.ruff": "explicit",
        "source.organizeImports.ruff": "explicit",
    }


def test_workspace_does_not_import_machine_or_legacy_settings() -> None:
    settings = _json("settings.json")
    forbidden = {
        "terminal.integrated.profiles.windows",
        "terminal.integrated.defaultProfile.windows",
        "terminal.external.windowsExec",
        "python-envs.terminal.autoActivationType",
        "chat.agentSkillsLocations",
        "chat.agentFilesLocations",
        "chat.instructionsFilesLocations",
        "chat.promptFilesLocations",
        "chat.hookFilesLocations",
        "chat.mcp.autoStart",
        "chat.enabledPlugins",
        "chat.plugins.marketplaces",
        "git.enableSmartCommit",
        "git.confirmSync",
        "pgsql.connections",
    }
    assert not forbidden & settings.keys()
    associations = settings["files.associations"]
    assert isinstance(associations, dict)
    assert associations["*.json.template"] == "json"


def test_debug_configuration_runs_tests_without_a_public_cli() -> None:
    launch = _json("launch.json")
    configurations = launch["configurations"]
    assert isinstance(configurations, list)
    assert configurations == [
        {
            "name": "Debug current test file",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["${file}", "-p", "no:xdist"],
            "cwd": "${workspaceFolder}",
            "justMyCode": False,
        }
    ]
    assert "inputs" not in launch


def test_editor_tasks_are_manual_unique_wrappers() -> None:
    tasks = _json("tasks.json")["tasks"]
    assert isinstance(tasks, list)
    assert len({task["label"] for task in tasks}) == len(tasks)
    assert all(
        task["type"] == "process" and task["command"] == "task" for task in tasks
    )
    assert all(task["options"] == {"cwd": "${workspaceFolder}"} for task in tasks)
    assert all("runOptions" not in task for task in tasks)
    assert all(len(task["args"]) == 1 for task in tasks)
    assert "bootstrap" in {task["args"][0] for task in tasks}
