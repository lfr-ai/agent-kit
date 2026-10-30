"""Keep developer entry points small without dropping repository checks."""

import json
from pathlib import Path
import re
import shlex
import subprocess
import tomllib

from identify.identify import tags_from_filename
from pre_commit.clientlib import load_config
import pytest
import scripts.check_conventions as conventions_module
import scripts.verify as verify_module
import yaml

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
    assert hooks["jscpd"]["entry"] == "bun run --bun jscpd"
    assert "args" not in hooks["check-added-large-files"]
    assert "args" not in hooks["no-commit-to-branch"]
    assert "args" not in hooks["yamllint"]
    assert "args" not in hooks["cspell"]
    assert hooks["lychee-docker"]["entry"].startswith(
        "lycheeverse/lychee:0.24.2@sha256:"
    )
    assert hooks["dependency-audit"]["entry"] == (
        "uv run --locked --no-sync python scripts/audit_dependencies.py"
    )
    assert hooks["dependency-audit"]["files"] == (
        r"^(pyproject\.toml|uv\.lock|package\.json|bun\.lock)$"
    )
    assert "zizmor" in hooks
    assert hooks["version-pins"]["always_run"] is True
    assert "toolkit-contract" in hooks
    assert "toolkit-drift" in hooks
    assert "toolkit-native-roles" in hooks


def test_dependency_audit_precedes_every_syncing_local_hook() -> None:
    """A changed lock is audited before any hook installs it through uv run."""
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    local = next(repo for repo in config["repos"] if repo["repo"] == "local")
    entries = [hook["entry"] for hook in local["hooks"]]
    audit = entries.index(
        "uv run --locked --no-sync python scripts/audit_dependencies.py"
    )
    syncing = [
        index
        for index, entry in enumerate(entries)
        if entry.startswith("uv run") and "--no-sync" not in entry
    ]
    assert syncing
    assert audit < min(syncing)


def test_hook_repositories_are_pinned_to_full_commits() -> None:
    """Moving a hook tag cannot change the code run on every commit."""
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    remote = [repo for repo in config["repos"] if repo["repo"] not in {"local", "meta"}]
    assert remote
    assert all(re.fullmatch(r"[0-9a-f]{40}", repo["rev"]) for repo in remote)


def test_scanner_config_edits_recheck_actual_workflows() -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    for identifier, filename in (
        ("actionlint", ".pre-commit-config.yaml"),
        ("zizmor", ".github/zizmor.yml"),
    ):
        hook = hooks[identifier]
        assert re.search(hook["files"], filename)
        assert re.search(hook["files"], ".github/workflows/ci.yml")
        assert not re.search(hook["files"], "docs/example.yaml")
        assert hook["pass_filenames"] is False
    assert hooks["zizmor"]["args"] == ["--no-progress", "."]
    assert hooks["actionlint"]["language_version"] == "1.27.3"


def test_actionlint_keeps_only_the_narrow_hook_compatibility_exception() -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "actionlint"
    )
    assert not (_ROOT / ".github/actionlint.yaml").exists()
    assert hook["args"] == [
        "-ignore",
        (
            r'reusable workflow call "\$/\.github/workflows/[a-z0-9-]+\.yml" '
            r'at "uses" is not following the format'
        ),
    ]
    message = 'reusable workflow call "{}" at "uses" is not following the format'
    assert re.search(hook["args"][1], message.format("$/.github/workflows/ci.yml"))
    assert not re.search(hook["args"][1], message.format("unapproved/action@main"))


def test_zizmor_policy_only_overrides_the_dependabot_cooldown() -> None:
    policy = yaml.safe_load((_ROOT / ".github/zizmor.yml").read_text())
    assert policy == {"rules": {"dependabot-cooldown": {"config": {"days": 14}}}}
    template = (
        _ROOT
        / "packages/iac/.apm/skills/kit-ci-review/assets/templates/zizmor.yml.template"
    )
    assert yaml.safe_load(template.read_text()) == policy


@pytest.mark.parametrize(
    "relative",
    [
        ".github/dependabot.yml",
        "packages/iac/.apm/skills/kit-ci-review/assets/templates/dependabot.yml.template",
    ],
)
def test_dependabot_version_updates_use_fourteen_day_cooldown(relative: str) -> None:
    config = yaml.safe_load((_ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    updates = config["updates"]
    assert isinstance(updates, list)
    assert updates
    for update in updates:
        assert isinstance(update, dict)
        assert update["cooldown"] == {"default-days": 14}


def test_ruff_complexity_limits_are_enforced_without_file_exemptions() -> None:
    lint = tomllib.loads((_ROOT / "ruff.toml").read_text())["lint"]
    assert lint["mccabe"]["max-complexity"] == 6
    assert lint["pylint"] == {
        "max-args": 8,
        "max-branches": 8,
        "max-returns": 6,
        "max-statements": 40,
    }
    ignored = [
        *lint.get("ignore", []),
        *(rule for rules in lint["per-file-ignores"].values() for rule in rules),
    ]
    assert not any(
        selected.startswith(rule)
        for selected in ("C901", "PLR0911", "PLR0912", "PLR0915")
        for rule in ignored
    )


def test_output_and_namespace_rules_have_no_source_exemptions() -> None:
    lint = tomllib.loads((_ROOT / "ruff.toml").read_text())["lint"]
    assert {"T20", "INP"} <= set(lint["extend-select"])
    source_exemptions = [
        *lint.get("ignore", []),
        *lint.get("extend-ignore", []),
        *(
            rule
            for pattern, rules in {
                **lint.get("per-file-ignores", {}),
                **lint.get("extend-per-file-ignores", {}),
            }.items()
            if pattern != "tests/**"
            for rule in rules
        ),
    ]
    assert not any(
        selected.startswith(rule)
        for selected in ("T201", "T203", "INP001")
        for rule in source_exemptions
    )
    assert not any(
        selected.startswith(rule)
        for selected in ("T201", "T203")
        for rule in lint["per-file-ignores"]["tests/**"]
    )


def test_ty_uses_the_same_configuration_in_hook_and_verifier() -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hook = next(
        hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == "ty"
    )
    assert hook["entry"] == "uv run --locked ty check"
    assert hook["pass_filenames"] is False
    assert hook["types"] == ["file"]
    for name in ("ty.toml", "pyproject.toml", "uv.lock", "src/mod.py", "src/mod.pyi"):
        assert re.search(hook["files"], name)
    assert not re.search(hook["files"], "README.md")
    assert verify_module._CHECKS["types"][-2:] == ("ty", "check")
    ty = tomllib.loads((_ROOT / "ty.toml").read_text())
    assert ty["terminal"]["error-on-warning"] is True
    assert set(ty["src"]["include"]) == {
        "src",
        "tests",
        "scripts",
        ".agents/guard",
        "packages",
    }


def test_task_and_editor_interfaces_only_expose_recurring_workflows() -> None:
    tasks = yaml.safe_load((_ROOT / "Taskfile.yml").read_text())["tasks"]
    assert set(tasks) == {
        "default",
        "bootstrap",
        "checkout:register",
        "lint",
        "format",
        "typecheck",
        "test",
        "test:matrix",
        "verify",
        "precommit",
        "commit",
        "version:preview",
        "version:prepare",
        "release:build",
        "release:publish",
        "capabilities:build",
        "apm:smoke",
    }
    assert "{{.CLI_ARGS}}" in tasks["verify"]["cmds"][0]
    assert tasks["default"]["cmds"] == ["{{.TASK_EXE}} --list"]
    assert all(task.get("desc") for task in tasks.values())
    assert [check["sh"] for check in tasks["bootstrap"]["preconditions"]] == [
        "uv --version",
        "bun --version",
    ]
    bootstrap = tasks["bootstrap"]["cmds"]
    assert bootstrap.index(
        "uv run --locked --no-sync python scripts/audit_dependencies.py"
    ) < bootstrap.index("uv sync --locked")
    assert bootstrap[0] == "uv sync --locked --inexact --only-group audit"
    assert bootstrap[-1] == {
        "cmd": '"{{.TASK_EXE}}" checkout:register',
        "platforms": ["windows"],
    }
    editor = json.loads((_ROOT / ".vscode/tasks.json").read_text())["tasks"]
    assert all(task["args"][0] in tasks for task in editor)
    assert len(editor) == len({task["args"][0] for task in editor})


def test_task_verification_never_syncs_before_dependency_audit() -> None:
    tasks = yaml.safe_load((_ROOT / "Taskfile.yml").read_text())["tasks"]
    command = shlex.split(tasks["verify"]["cmds"][0])

    assert command[:5] == ["uv", "run", "--locked", "--no-sync", "python"]
    assert command[5:] == ["scripts/verify.py", "{{.CLI_ARGS}}"]
    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["verify"]["steps"]
    gate = next(
        step
        for step in steps
        if step.get("name") == "Same check-only gate as task verify"
    )
    assert shlex.split(gate["run"]) == command[:-1]
    assert next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "uv sync --locked"
    ) < steps.index(gate)


@pytest.mark.parametrize("lock_exit", [0, 1])
def test_full_verification_checks_lock_before_other_gates(
    monkeypatch: pytest.MonkeyPatch, lock_exit: int
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        code = lock_exit if command == ["uv", "lock", "--check"] else 0
        return subprocess.CompletedProcess(command, code)

    monkeypatch.setattr(verify_module.sys, "argv", ["verify.py"])
    monkeypatch.setattr(verify_module.shutil, "which", lambda name: name)
    monkeypatch.setattr(verify_module.subprocess, "run", run)

    assert verify_module.main() == lock_exit
    assert calls[0] == ["uv", "lock", "--check"]
    expected = 1 if lock_exit else len(verify_module._CHECKS)
    assert len(calls) == expected
    assert not any(command[-1] == "scripts/audit_dependencies.py" for command in calls)


def test_network_audit_does_not_run_installation_or_other_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(
        command: list[str], *, env: dict[str, str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert env["APM_NO_SCRIPTS"] == "1"
        assert env["APM_NON_INTERACTIVE"] == "1"
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(verify_module.sys, "argv", ["verify.py", "dependencies"])
    monkeypatch.setattr(verify_module.shutil, "which", lambda name: name)
    monkeypatch.setattr(verify_module.subprocess, "run", run)

    assert verify_module.main() == 7
    assert calls == [[verify_module._PYTHON, "scripts/audit_dependencies.py"]]


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


def test_python_docstring_conventions_run_in_task_and_precommit() -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    hook = hooks["toolkit-python-conventions"]

    assert "conventions" in verify_module._CHECKS
    assert hook["entry"] == "uv run --locked python scripts/check_conventions.py"
    assert hook["always_run"] is True
    assert hook["pass_filenames"] is False


def test_conventions_gate_checks_packaged_python_docstrings(tmp_path: Path) -> None:
    """The committed gate rejects a single-quoted code token in a skill asset."""
    for relative in ("src", "scripts", "tests", ".agents/guard", ".apm"):
        (tmp_path / relative).mkdir(parents=True)
    asset = tmp_path / "packages/example/assets/check.py"
    asset.parent.mkdir(parents=True)
    asset.write_text('"""Use \'name\'."""\n', encoding="utf-8")

    assert conventions_module.run(tmp_path) == 1


def _conventions_root(tmp_path: Path) -> Path:
    for relative in ("src", "scripts", "tests", ".agents/guard", ".apm", "packages"):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_conventions_gate_treats_terminated_checker_as_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = iter((-9, 0, 0, 0))
    calls: list[tuple[str, ...]] = []

    def run_checker(paths: tuple[Path, ...], *, options: tuple[str, ...] = ()) -> int:
        calls.append(options)
        return next(results)

    monkeypatch.setattr(conventions_module, "_run_checker", run_checker)
    assert conventions_module.run(tmp_path) == 1
    assert len(calls) == 4


@pytest.mark.parametrize(
    "relative",
    [
        "src/mod.py",
        "packages/example/assets/check.py",
        "packages/example/assets/settings.py.template",
    ],
)
def test_conventions_gate_rejects_magic_numbers_in_production_and_assets(
    tmp_path: Path, relative: str
) -> None:
    root = _conventions_root(tmp_path)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('"""Module."""\n\nTIMEOUT = 30\nwait = 30\n', encoding="utf-8")

    assert conventions_module.run(root) == 1
    path.write_text('"""Module."""\n\nTIMEOUT = 30\nwait = TIMEOUT\n', encoding="utf-8")
    assert conventions_module.run(root) == 0


def test_conventions_gate_keeps_literal_test_expectations(tmp_path: Path) -> None:
    root = _conventions_root(tmp_path)
    (root / "tests/test_values.py").write_text(
        "def test_size() -> None:\n    assert len([1, 2]) == 2\n", encoding="utf-8"
    )

    assert conventions_module.run(root) == 0
