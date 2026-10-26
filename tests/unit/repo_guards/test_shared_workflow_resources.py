"""Shared workflow skill checkers and templates behave on synthetic inputs."""

import ast
from collections.abc import Callable, Sequence
import json
from pathlib import Path
import re
import runpy
import tomllib

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SKILLS = _ROOT / "packages/shared/.apm/skills"
_OWNED = (
    "kit-refactor",
    "kit-parallel-work",
    "kit-editor",
    "kit-context-onboarding",
    "kit-documentation",
    "kit-release",
    "kit-create-skill",
    "kit-change-plan",
)
_TASKFILE = """version: "3"

includes:
  docs: ./docs/Taskfile.yml

tasks:
  default:
    cmds:
      - task --list
  verify:
    desc: Completion gate
    cmds:
      - echo verify
  "test:unit":
    cmds: [echo unit]
  lint: echo lint

vars:
  NOT_A_TASK: value
"""


def _load(skill: str, name: str) -> dict[str, object]:
    return runpy.run_path(str(_SKILLS / skill / "assets" / name))


def _main(namespace: dict[str, object]) -> Callable[[list[str]], int]:
    main = namespace["main"]
    assert callable(main)

    def invoke(arguments: list[str]) -> int:
        result = main(arguments)
        assert isinstance(result, int)
        return result

    return invoke


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _workspace(tmp_path: Path, tasks: str) -> tuple[Path, Path]:
    return (
        _write(tmp_path / ".vscode/tasks.json", tasks),
        _write(tmp_path / "Taskfile.yml", _TASKFILE),
    )


def test_task_wiring_accepts_declared_targets_with_jsonc(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks, taskfile = _workspace(
        tmp_path,
        """{
  // Thin wrappers only.
  "version": "2.0.0",
  "tasks": [
    {"label": "Verify", "type": "process", "command": "task", "args": ["verify"],},
    {"label": "Unit", "type": "shell", "command": "task test:unit"},
    /* The default target needs no argument. */
    {"label": "Default", "type": "process", "command": "task"},
    {"label": "Docs", "type": "process", "command": "task", "args": ["docs:build"]},
    {"label": "Npm", "type": "npm", "script": "build"},
  ],
}
""",
    )
    main = _main(_load("kit-editor", "check_task_wiring.py"))
    assert main(["--tasks", str(tasks), "--taskfile", str(taskfile)]) == 0
    assert "are declared" in capsys.readouterr().out


def test_task_wiring_reports_missing_and_dynamic_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks, taskfile = _workspace(
        tmp_path,
        """{"version": "2.0.0", "tasks": [
{"label": "Deploy", "type": "process", "command": "task", "args": ["-d", "x", "deploy"]},
{"label": "Pick", "type": "process", "command": "task", "args": ["${input:target}"]},
{"label": "Lint", "type": "process", "command": "task", "args": ["lint", "MODE=fast"],
 "windows": {"command": "task.exe", "args": ["lint:win"]}}
]}
""",
    )
    main = _main(_load("kit-editor", "check_task_wiring.py"))
    assert main(["--tasks", str(tasks), "--taskfile", str(taskfile)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert lines[0].endswith(
        ":2: task 'Deploy' targets 'deploy', which the Taskfile does not declare"
    )
    assert ":3: task 'Pick' passes unverifiable argument" in lines[1]
    assert lines[2].endswith(
        ":4: task 'Lint' targets 'lint:win', which the Taskfile does not declare"
    )


def test_task_wiring_include_namespaces_can_be_strict(tmp_path: Path) -> None:
    tasks, taskfile = _workspace(
        tmp_path,
        '{"tasks": [{"label": "Docs", "command": "task", "args": ["docs:build"]}]}\n',
    )
    main = _main(_load("kit-editor", "check_task_wiring.py"))
    args = ["--tasks", str(tasks), "--taskfile", str(taskfile)]
    assert main(args) == 0
    assert main([*args, "--verify-includes"]) == 1


def test_task_wiring_parses_only_top_level_task_keys() -> None:
    parse = _load("kit-editor", "check_task_wiring.py")["parse_taskfile"]
    assert callable(parse)
    parsed = parse(_TASKFILE)
    assert getattr(parsed, "tasks", None) == frozenset(
        {"default", "verify", "test:unit", "lint"}
    )
    assert getattr(parsed, "includes", None) == frozenset({"docs"})


def test_task_wiring_unreadable_input_is_an_error(tmp_path: Path) -> None:
    main = _main(_load("kit-editor", "check_task_wiring.py"))
    tasks = _write(tmp_path / "tasks.json", "{not json")
    taskfile = _write(tmp_path / "Taskfile.yml", _TASKFILE)
    assert main(["--tasks", str(tasks), "--taskfile", str(taskfile)]) == 2
    assert (
        main(["--tasks", str(tmp_path / "absent.json"), "--taskfile", str(taskfile)])
        == 2
    )


def test_task_wiring_accepts_the_shipped_tasks_template(tmp_path: Path) -> None:
    assets = _SKILLS / "kit-editor/assets"
    taskfile = _write(
        tmp_path / "Taskfile.yml",
        'version: "3"\ntasks:\n'
        + "".join(
            f"  {name}:\n    cmds: [echo {name}]\n"
            for name in ("verify", "test", "lint", "format", "build", "docs")
        ),
    )
    main = _main(_load("kit-editor", "check_task_wiring.py"))
    for name in ("tasks.json.template", "user-tasks.json.template"):
        assert (
            main(["--tasks", str(assets / name), "--taskfile", str(taskfile)]) == 0
        ), name


def test_worktree_dry_run_prints_commands_without_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    main = _main(_load("kit-parallel-work", "new_worktree.py"))
    assert (
        main(["--repo", str(repo), "--branch", "agent/orders-api", "--base", "HEAD~1"])
        == 0
    )
    out = capsys.readouterr().out
    assert "worktree add -b agent/orders-api --" in out
    assert "repo-agent-orders-api" in out
    assert not (tmp_path / "repo-agent-orders-api").exists()


@pytest.mark.parametrize(
    "branch", ["-delete", "bad..name", "has space", "end.lock", "trailing/", "a~1"]
)
def test_worktree_rejects_unsafe_branch_names(
    tmp_path: Path, branch: str, capsys: pytest.CaptureFixture[str]
) -> None:
    main = _main(_load("kit-parallel-work", "new_worktree.py"))
    assert main(["--repo", str(tmp_path), f"--branch={branch}"]) == 1
    assert "Refusing" in capsys.readouterr().err


def test_worktree_rejects_paths_inside_repo_or_nonempty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "nested").mkdir(parents=True)
    occupied = _write(tmp_path / "occupied/file.txt", "x").parent
    main = _main(_load("kit-parallel-work", "new_worktree.py"))
    base = ["--repo", str(repo), "--branch", "agent/x"]
    assert main([*base, "--path", str(repo / "nested")]) == 1
    assert main([*base, "--path", str(occupied)]) == 1
    assert main([*base, "--path", str(tmp_path / "free")]) == 0


def test_worktree_execution_stops_at_first_failure(tmp_path: Path) -> None:
    namespace = _load("kit-parallel-work", "new_worktree.py")
    build_plan = namespace["build_plan"]
    execute = namespace["execute"]
    assert callable(build_plan)
    assert callable(execute)
    plan = build_plan(
        repository=tmp_path / "repo", branch="agent/x", base="HEAD", path=None
    )
    calls: list[Sequence[str]] = []

    def runner(command: Sequence[str]) -> int:
        calls.append(command)
        return 0 if len(calls) < 2 else 128

    result = execute(plan, runner=runner)
    assert isinstance(result, tuple)
    assert len(result) == 2
    status, failed = result
    assert status == 128
    assert "rev-parse" in failed
    assert len(calls) == 2
    assert all(isinstance(command, tuple) for command in calls)


def _freshness_main() -> Callable[[list[str]], int]:
    """Return the canonical memory checker in its lenient freshness mode."""
    main = _main(_load("kit-project-memory", "check_memory_files.py"))

    def invoke(arguments: list[str]) -> int:
        return main([*arguments, "--freshness-only"])

    return invoke


def test_memory_freshness_flags_stale_future_and_broken_links(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / "docs/guide.md", "# Guide\n")
    memory = _write(
        tmp_path / "memories/lessons.md",
        "# Lessons\n\n"
        "## 2026-01-05 Fresh lesson\n\nSee [guide](../docs/guide.md).\n\n"
        "## 2025-01-01 Stale lesson\n\nSee [gone](../docs/removed.md).\n\n"
        "## 2024-01-01 Old but verified\n\n- Last verified: 2026-01-10\n\n"
        "## 2023-01-01 Retired\n\n- Status: superseded\n\n"
        "## 2026-12-31 Future lesson\n\n[outside](../../elsewhere.md)\n",
    )
    main = _freshness_main()
    args = [str(memory), "--root", str(tmp_path), "--today", "2026-02-01"]
    assert main([*args, "--max-age-days", "90"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert re.findall(r"\.md:(\d+): ", "\n".join(lines)) == [
        "7",
        "9",
        "19",
        "21",
    ]
    assert "Stale lesson" in lines[0]
    assert "missing file" in lines[1]
    assert "in the future" in lines[2]
    assert "leaves the checked root" in lines[3]


def test_memory_freshness_passes_fresh_directory(tmp_path: Path) -> None:
    _write(tmp_path / "memories/a.md", "## 2026-01-20 Recent\n\nNo links.\n")
    _write(tmp_path / "memories/nested/b.md", "# Notes without dates\n")
    main = _freshness_main()
    args = [
        str(tmp_path / "memories"),
        "--root",
        str(tmp_path),
        "--today",
        "2026-02-01",
    ]
    assert main(args) == 0
    assert main([*args, "--max-age-days", "5"]) == 1


def test_memory_freshness_missing_path_is_an_error(tmp_path: Path) -> None:
    main = _freshness_main()
    assert main([str(tmp_path / "absent"), "--today", "2026-02-01"]) == 2


@pytest.mark.parametrize(
    "path",
    sorted(
        path
        for skill in _OWNED
        for path in (_SKILLS / skill / "assets").glob("*.template")
        if path.name.endswith(
            (
                ".json.template",
                ".yml.template",
                ".yaml.template",
                ".toml.template",
                ".py.template",
            )
        )
    ),
    ids=lambda path: f"{path.parent.parent.name}/{path.name}",
)
def test_structured_templates_parse(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    name = path.name.removesuffix(".template")
    if name.endswith(".json"):
        assert isinstance(json.loads(text), (dict, list))
    elif name.endswith((".yml", ".yaml")):
        assert isinstance(yaml.safe_load(text), dict)
    elif name.endswith(".toml"):
        assert tomllib.loads(text)
    else:
        ast.parse(text)


def test_editor_integration_catalog_stays_inactive() -> None:
    catalog = json.loads(
        (_SKILLS / "kit-editor/assets/integration-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    assert catalog["default_active"] == []


@pytest.mark.parametrize("skill", _OWNED)
def test_owned_skill_files_are_lf_utf8_with_final_newline(skill: str) -> None:
    for path in sorted((_SKILLS / skill).rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), path
        assert b"\r\n" not in data, path
        assert data.endswith(b"\n"), path
