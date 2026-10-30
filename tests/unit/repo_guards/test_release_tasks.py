"""Release entry points preserve source review and operator-only publication."""

import json
from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
# Task startup is slow on Windows and under parallel test load.
_TASK_TIMEOUT_SECONDS = 180


def _tasks() -> dict[str, dict[str, object]]:
    return yaml.safe_load((_ROOT / "Taskfile.yml").read_text(encoding="utf-8"))["tasks"]


def test_version_preview_is_read_only() -> None:
    """Preview flags cannot silently become bump, commit, tag or changelog writes."""
    task = _tasks()["version:preview"]

    assert task["cmds"] == [
        "uv run --locked --no-sync cz bump --dry-run --yes",
        "uv run --locked --no-sync cz changelog --dry-run",
    ]
    assert "{{.CLI_ARGS}}" not in str(task)


def test_version_preparation_updates_files_and_lock_without_git_mutation() -> None:
    """Conventional commits choose the version; the operator reviews the edits."""
    task = _tasks()["version:prepare"]
    config = tomllib.loads((_ROOT / ".cz.toml").read_text(encoding="utf-8"))

    assert task["prompt"]
    assert task["interactive"] is True
    assert task["cmds"] == [
        "uv run --locked --no-sync cz bump --version-files-only --yes",
        "uv lock",
    ]
    conditions = task["preconditions"]
    assert isinstance(conditions, list)
    assert "git diff --quiet" in conditions[0]["sh"]
    assert not config["tool"]["commitizen"].get("update_changelog_on_bump", False)
    assert "CHANGELOG.md" not in config["tool"]["commitizen"]["version_files"]


def test_release_build_reuses_the_existing_capability_builder_and_validator() -> None:
    """No cleanup, overwrite switch or second artifact-validation engine is added."""
    assert _tasks()["release:build"]["cmds"] == [
        "uv build --out-dir build/distributions",
        {
            "task": "capabilities:build",
            "vars": {"CLI_ARGS": "--profile fullstack --feature iac"},
        },
        "uv run --locked --no-sync python -m scripts.check_release",
    ]


def test_publication_requires_a_tag_confirmation_and_existing_draft() -> None:
    """Publishing is not tag creation, an admin merge, or direct package upload."""
    task = _tasks()["release:publish"]

    assert task["requires"] == {"vars": ["TAG"]}
    assert task["prompt"]
    assert task["interactive"] is True
    conditions = task["preconditions"]
    assert isinstance(conditions, list)
    assert "regexMatch" in conditions[0]["sh"]
    assert "v[0-9]+[.][0-9]+[.][0-9]+$" in conditions[0]["sh"]
    assert "shellQuote" in conditions[1]["sh"]
    assert "--json isDraft --jq .isDraft" in conditions[1]["sh"]
    assert task["cmds"] == [
        "uv run --locked --no-sync python scripts/check_governance.py --publication",
        "gh release view {{.TAG | shellQuote}} --repo lfr-ai/agent-kit",
        "gh release edit {{.TAG | shellQuote}} --repo lfr-ai/agent-kit --draft=false",
    ]


@pytest.mark.parametrize(
    "name",
    ["version:preview", "version:prepare", "release:build", "release:publish"],
)
def test_release_task_dry_runs_do_not_change_files_or_contact_github(
    tmp_path: Path, name: str
) -> None:
    """The actual pinned Task binary must parse each target before handoff."""
    executable = shutil.which("task")
    if executable is None:
        pytest.skip("Task is unavailable")
    taskfile = tmp_path / "Taskfile.yml"
    source = (_ROOT / "Taskfile.yml").read_bytes()
    taskfile.write_bytes(source)
    result = subprocess.run(  # noqa: S603 - resolved Task with fixed dry-run argv
        [
            executable,
            "--taskfile",
            str(taskfile),
            "--dry",
            "--force",
            name,
            "TAG=v0.1.1",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=_TASK_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, result.stderr
    assert taskfile.read_bytes() == source
    assert list(tmp_path.iterdir()) == [taskfile]


def test_editor_exposes_preview_and_local_preparation_but_not_remote_publish() -> None:
    """The editor keeps literal one-target wrappers; publication needs a CLI tag."""
    editor = json.loads((_ROOT / ".vscode/tasks.json").read_text(encoding="utf-8"))[
        "tasks"
    ]
    targets = {task["args"][0] for task in editor}

    assert {"version:preview", "version:prepare", "release:build"} <= targets
    assert "release:publish" not in targets


@pytest.mark.parametrize("tag", ["", "--help", "v1.2", "v1.2.3;echo injected"])
def test_invalid_publication_tag_stops_before_any_github_command(
    tmp_path: Path, tag: str
) -> None:
    """Actual Task preconditions reject empty, option-like and shell input."""
    executable = shutil.which("task")
    if executable is None:
        pytest.skip("Task is unavailable")
    taskfile = tmp_path / "Taskfile.yml"
    taskfile.write_bytes((_ROOT / "Taskfile.yml").read_bytes())
    result = subprocess.run(  # noqa: S603 - fixed task, hostile tag is a single argv
        [
            executable,
            "--taskfile",
            str(taskfile),
            "--yes",
            "release:publish",
            f"TAG={tag}",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=_TASK_TIMEOUT_SECONDS,
    )

    assert result.returncode != 0
    assert "numeric release tag" in result.stderr
    assert "injected\n" not in result.stdout
