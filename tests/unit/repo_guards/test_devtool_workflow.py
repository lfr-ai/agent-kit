"""Keep developer entry points small without dropping repository checks."""

from collections.abc import Callable
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time
import tomllib

from identify.identify import tags_from_filename
from pre_commit.clientlib import load_config
import pytest
import scripts.checks.conventions as conventions_module
import scripts.verify as verify_module
import yaml

_ROOT = Path(__file__).resolve().parents[3]


def test_delivery_composite_has_native_schema_validation() -> None:
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "check-github-actions"
    )
    assert re.search(hook["files"], "packages/delivery/actions/python-check/action.yml")


def test_pull_request_commit_gate_uses_a_nonempty_commit_range() -> None:
    workflow = yaml.safe_load((_ROOT / ".github/workflows/toolkit-ci.yml").read_text())
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Conventional Commit messages in the pull request"
    )

    assert "git merge-base" in step["run"]
    assert "git rev-list --max-count=1" in step["run"]
    assert 'if [ -z "$commits" ]' in step["run"]


def test_ci_runs_every_hook_stage_on_all_files() -> None:
    workflow = yaml.safe_load((_ROOT / ".github/workflows/toolkit-ci.yml").read_text())
    commands = {
        shlex.join(shlex.split(step["run"]))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "pre-commit run" in step.get("run", "")
    }

    assert commands == {
        "uv run --locked pre-commit run --all-files --show-diff-on-failure",
        "uv run --locked pre-commit run --all-files --hook-stage pre-push",
    }
    push = next(
        step
        for step in workflow["jobs"]["precommit"]["steps"]
        if "--hook-stage pre-push" in step.get("run", "")
    )
    # Only the gate the verify matrix already runs may be skipped.
    assert push["env"] == {"SKIP": "toolkit-static"}
    commit = next(
        step
        for step in workflow["jobs"]["precommit"]["steps"]
        if "--show-diff-on-failure" in step.get("run", "")
    )
    # Dependency hooks run once in the audit job and the verify matrix instead.
    assert set(commit["env"]["SKIP"].split(",")) == {
        "no-commit-to-branch",
        "uv-lock",
        "dependency-audit",
        "dependency-licenses",
    }


def test_ci_verifies_each_branch_once_through_its_pull_request() -> None:
    """A pushed branch with an open pull request must not run the matrix twice."""
    workflow = yaml.safe_load((_ROOT / ".github/workflows/toolkit-ci.yml").read_text())
    triggers = workflow[True]

    assert triggers["push"] == {"branches": ["main"]}
    assert {"pull_request", "merge_group", "workflow_call"} <= triggers.keys()


@pytest.mark.parametrize(
    "path",
    [
        ".agents/skills/kit-example/SKILL.md",
        ".claude/skills/kit-example/assets/check.py",
        ".claude/rules/kit-example.md",
        ".claude/agents/kit-example.md",
        ".github/agents/kit-example.agent.md",
        ".github/instructions/kit-example.instructions.md",
        "profiles/native/copilot/.apm/agents/kit-example.agent.md",
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
    ("path", "excluded"),
    [
        ("uv.lock", True),
        ("bun.lock", True),
        ("apm.lock.yaml", True),
        ("fixtures/uv.lock", False),
        (".agents/agentic-setup/native-lock.json", True),
        (".agents/agentic-setup/profile-lock.json", True),
        ("packages/delivery/catalog.json", True),
        ("packages/delivery/catalog.json.bak", False),
        ("fixtures/packages/delivery/catalog.json", False),
        ("fixtures/.agents/agentic-setup/profile-lock.json", False),
        ("packages/delivery/azure-devops/extends/azure-deploy.yml", False),
        (".agents/agentic-setup/native-lock.json.tmp", False),
        ("tests/unit/runtime/test_ai.py", False),
    ],
)
def test_secret_scan_exclusions_have_one_narrow_owner(
    path: str, *, excluded: bool
) -> None:
    """Only hash-only generated files skip the scan, decided by the baseline alone."""
    baseline = json.loads((_ROOT / ".secrets.baseline").read_text(encoding="utf-8"))
    patterns = next(
        item["pattern"]
        for item in baseline["filters_used"]
        if item["path"] == "detect_secrets.filters.regex.should_exclude_file"
    )
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "detect-secrets"
    )

    assert any(re.search(pattern, path) for pattern in patterns) is excluded
    assert hook.get("exclude", "^$") == "^$"


@pytest.mark.parametrize(
    "path",
    [
        ".apm/skills/kit-example/SKILL.md",
        "packages/backend/.apm/skills/kit-example/assets/check.py",
        ".github/workflows/toolkit-ci.yml",
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
        "uv run --no-project python scripts/audit_dependencies.py"
    )
    assert hooks["dependency-audit"]["files"] == (
        r"^(pyproject\.toml|uv\.lock|package\.json|bun\.lock)$"
    )
    assert "zizmor" in hooks
    static = hooks["toolkit-static"]
    assert static["entry"] == (
        "uv run --locked --no-sync python scripts/verify.py static"
    )
    assert static["always_run"] is True
    assert static["pass_filenames"] is False
    assert "pre-push" in config["default_install_hook_types"]
    repository_wide = {"toolkit-static", "jscpd", "lychee-docker"}
    assert {
        name for name, hook in hooks.items() if hook.get("stages") == ["pre-push"]
    } == repository_wide
    # Repository-wide type and import checks are covered once per push by the
    # static gate instead of once per commit.
    assert "ty" not in hooks
    assert "toolkit-architecture" not in hooks
    assert {"types", "architecture", "pins"} <= set(verify_module._CHECKS)


def test_dependency_audit_precedes_the_only_syncing_local_hook() -> None:
    """A changed lock is audited before the one hook that installs it through uv run."""
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    local = next(repo for repo in config["repos"] if repo["repo"] == "local")
    hooks = local["hooks"]
    entries = [hook["entry"] for hook in hooks]
    audit = entries.index("uv run --no-project python scripts/audit_dependencies.py")
    syncing = [
        index
        for index, entry in enumerate(entries)
        if entry.startswith("uv run")
        and "--no-sync" not in entry
        and "--no-project" not in entry
    ]
    # Every other hook reuses the bootstrapped environment and never installs.
    assert [hooks[index]["id"] for index in syncing] == ["dependency-licenses"]
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
        assert re.search(hook["files"], ".github/workflows/toolkit-ci.yml")
        assert not re.search(hook["files"], "docs/example.yaml")
        assert hook["pass_filenames"] is False
    assert hooks["zizmor"]["args"] == ["--no-progress", "."]
    assert hooks["actionlint"]["language_version"] == "1.27.3"


def test_actionlint_keeps_only_reviewed_source_reference_exceptions() -> None:
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
        "-ignore",
        (
            r'^specifying action "\$/packages/delivery/actions/python-check" '
            r"in invalid format because ref is missing\."
        ),
    ]
    message = 'reusable workflow call "{}" at "uses" is not following the format'
    assert re.search(
        hook["args"][1], message.format("$/.github/workflows/toolkit-ci.yml")
    )
    assert not re.search(hook["args"][1], message.format("unapproved/action@main"))
    action_message = 'specifying action "{}" in invalid format because ref is missing.'
    assert re.search(
        hook["args"][3],
        action_message.format("$/packages/delivery/actions/python-check"),
    )
    for reference in (
        "./packages/delivery/actions/python-check",
        "$/packages/delivery/actions/unreviewed",
        "$/packages/delivery/actions/python-check@main",
    ):
        assert not re.search(hook["args"][3], action_message.format(reference))


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
    """ty runs once per push through the static gate with ty.toml as its only config."""
    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    hooks = {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}
    assert "toolkit-static" in hooks
    assert "ty" not in hooks
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
        "bootstrap:azure",
        "checkout:register",
        "lint",
        "format",
        "typecheck",
        "test",
        "check",
        "test:matrix",
        "verify",
        "precommit",
        "commit",
        "version:preview",
        "version:prepare",
        "release:build",
        "release:publish",
        "capabilities:build",
        "profiles:build",
        "apm:smoke",
    }
    assert tasks["profiles:build"]["cmds"] == [
        "uv run --locked python scripts/build_profiles.py --write"
    ]
    check = tasks["check"]["cmds"]
    assert check[0] == {"task": "format"}
    # The inner loop skips integration by path (not even imported) and slow tests.
    assert "pytest tests/unit tests/property " in check[-1]
    assert '-m "not slow"' in check[-1]
    assert "{{.CLI_ARGS}}" in tasks["verify"]["cmds"][0]
    assert tasks["default"]["cmds"] == ["{{.TASK_EXE}} --list"]
    assert all(task.get("desc") for task in tasks.values())
    assert [check["sh"] for check in tasks["bootstrap"]["preconditions"]] == [
        "uv --version",
        "bun --version",
    ]
    bootstrap = tasks["bootstrap"]["cmds"]
    assert bootstrap.index(
        "uv run --no-project python scripts/audit_dependencies.py"
    ) < bootstrap.index("uv sync --locked")
    assert bootstrap[0] == "uv run --no-project python scripts/audit_dependencies.py"
    assert all("--only-group audit" not in str(command) for command in bootstrap)
    assert bootstrap[-1] == {
        "cmd": '"{{.TASK_EXE}}" checkout:register',
        "platforms": ["windows"],
    }
    azure = tasks["bootstrap:azure"]
    assert azure["cmds"] == [
        "uv run --locked --no-sync python packages/delivery/scripts/bootstrap_azure.py {{.CLI_ARGS}}"
    ]
    assert not ({"deps", "preconditions"} & azure.keys())
    assert "--apply" not in str(azure["cmds"])
    editor = json.loads((_ROOT / ".vscode/tasks.json").read_text())["tasks"]
    assert all(task["args"][0] in tasks for task in editor)
    assert len(editor) == len({task["args"][0] for task in editor})


def test_task_verification_never_syncs_before_dependency_audit() -> None:
    tasks = yaml.safe_load((_ROOT / "Taskfile.yml").read_text())["tasks"]
    command = shlex.split(tasks["verify"]["cmds"][0])

    assert command[:5] == ["uv", "run", "--locked", "--no-sync", "python"]
    assert command[5:] == ["scripts/verify.py", "{{.CLI_ARGS}}"]
    workflow = yaml.safe_load((_ROOT / ".github/workflows/toolkit-ci.yml").read_text())
    steps = workflow["jobs"]["verify"]["steps"]
    gate = next(
        step
        for step in steps
        if step.get("name") == "Same check-only gate as task verify"
    )
    assert gate["uses"] == "$/packages/delivery/actions/python-check"
    assert gate.get("with", {}).get("task") in (None, "verify")
    action = yaml.safe_load(
        (_ROOT / "packages/delivery/actions/python-check/action.yml").read_text()
    )
    assert action["inputs"]["task"]["default"] == "verify"
    steps = action["runs"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Run task")
    assert shlex.split(gate["run"]) == [
        "uv",
        "run",
        "--locked",
        "--no-sync",
        "task",
        "$TASK_NAME",
    ]
    assert gate["env"]["TASK_NAME"] == "${{ inputs.task }}"
    assert next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "uv sync --locked"
    ) < steps.index(gate)


_GateResult = tuple[int, str]


def _fake_gates(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    gate: Callable[[list[str], dict[str, str]], _GateResult],
) -> None:
    def run_gate(
        _name: str, resolved: list[str], env: dict[str, str], *, capture: bool
    ) -> _GateResult:
        del capture
        return gate(resolved, env)

    monkeypatch.setattr(verify_module.sys, "argv", ["verify.py", *argv])
    monkeypatch.setattr(verify_module.shutil, "which", lambda name: name)
    monkeypatch.setattr(verify_module, "_run_gate", run_gate)


@pytest.mark.parametrize("lock_exit", [0, 1])
def test_full_verification_checks_lock_before_other_gates(
    monkeypatch: pytest.MonkeyPatch, lock_exit: int
) -> None:
    calls: list[list[str]] = []

    def gate(command: list[str], _env: dict[str, str]) -> _GateResult:
        calls.append(command)
        return (lock_exit if command == ["uv", "lock", "--check"] else 0), ""

    _fake_gates(monkeypatch, [], gate)

    assert verify_module.main() == lock_exit
    assert calls[0] == ["uv", "lock", "--check"]
    expected = 1 if lock_exit else len(verify_module._CHECKS)
    assert len(calls) == expected
    assert not any(command[-1] == "scripts/audit_dependencies.py" for command in calls)


def test_full_verification_reports_every_static_gate_and_skips_tests_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    def gate(command: list[str], _env: dict[str, str]) -> _GateResult:
        calls.append(command)
        code = 3 if command == list(verify_module._CHECKS["lint"]) else 0
        return code, "lint output\n"

    _fake_gates(monkeypatch, [], gate)

    assert verify_module.main() == 3
    assert list(verify_module._CHECKS["tests"]) not in calls
    assert len(calls) == len(verify_module._CHECKS) - 1
    summary = capsys.readouterr().out.split("Summary:", 1)[1]
    assert "lint" in summary
    assert "FAIL (3)" in summary
    assert "docs" in summary


def test_static_pseudo_gate_runs_neither_lock_nor_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-push hook runs the static registry without syncing or testing."""
    calls: list[list[str]] = []

    def gate(command: list[str], _env: dict[str, str]) -> _GateResult:
        calls.append(command)
        return 0, ""

    _fake_gates(monkeypatch, ["static"], gate)

    assert verify_module.main() == 0
    assert list(verify_module._CHECKS["lock"]) not in calls
    assert list(verify_module._CHECKS["tests"]) not in calls
    assert len(calls) == len(verify_module._CHECKS) - 2


@pytest.mark.parametrize("capture", [False, True])
def test_gate_timeout_kills_grandchildren_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capture: bool
) -> None:
    """A grandchild holding the output pipe must die with its timed-out gate."""
    heartbeat = tmp_path / "heartbeat"
    beater = (
        "import pathlib, time\n"
        f"path = pathlib.Path({str(heartbeat)!r})\n"
        "count = 0\n"
        "while True:\n"
        "    count += 1\n"
        "    path.write_text(str(count))\n"
        "    time.sleep(0.1)\n"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {beater!r}]); time.sleep(120)"
    )
    # Leaves room for two interpreter start-ups on a loaded Windows runner while a
    # surviving grandchild would still overrun timeout + drain.
    timeout = 6
    monkeypatch.setattr(verify_module, "_timeout", lambda _name: timeout)
    started = time.monotonic()

    code, output = verify_module._run_gate(
        "docs", [sys.executable, "-c", parent], dict(os.environ), capture=capture
    )

    # A surviving grandchild would hold the pipe until the drain deadline.
    assert time.monotonic() - started < timeout + verify_module._DRAIN_SECONDS - 1
    assert code == 1
    assert f"docs: timed out after {timeout} s" in output
    assert heartbeat.exists(), "the grandchild never started; raise the timeout"
    time.sleep(0.5)
    before = heartbeat.read_text()
    time.sleep(1)
    assert heartbeat.read_text() == before, "the grandchild outlived its gate"


def test_captured_gate_output_is_utf8_from_python_children() -> None:
    """Captured Python gates write UTF-8, not the locale code page."""
    code, output = verify_module._run_gate(
        "docs",
        [sys.executable, "-c", "print('caf\\u00e9 \\u2013 x')"],
        dict(os.environ),
        capture=True,
    )

    assert code == 0
    assert output.strip() == "caf\u00e9 \u2013 x"


def test_gate_start_failure_is_reported_with_gate_and_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_start(*_args: object, **_kwargs: object) -> None:
        message = "not found"
        raise FileNotFoundError(message)

    monkeypatch.setattr(verify_module.subprocess, "Popen", fail_start)

    code, output = verify_module._run_gate(
        "docs", ["missing-gate"], dict(os.environ), capture=True
    )

    assert code == 1
    assert output == "docs: unable to start missing-gate: not found\n"


def test_network_audit_does_not_run_installation_or_other_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def gate(command: list[str], env: dict[str, str]) -> _GateResult:
        calls.append(command)
        assert env["APM_NO_SCRIPTS"] == "1"
        assert env["APM_NON_INTERACTIVE"] == "1"
        return 7, ""

    _fake_gates(monkeypatch, ["dependencies"], gate)

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
    """The pre-push static gate runs the same conventions command as the Task."""
    assert verify_module._CHECKS["conventions"] == (
        verify_module._PYTHON,
        "-m",
        "scripts.checks.conventions",
    )
    assert "conventions" not in {verify_module._FIRST, verify_module._LAST}


def test_suppression_gate_uses_one_always_run_implementation() -> None:
    assert verify_module._CHECKS["suppressions"] == (
        verify_module._PYTHON,
        "-m",
        "scripts.checks.suppressions",
    )
    assert "suppressions" not in {verify_module._FIRST, verify_module._LAST}
    facade = (_ROOT / ".agents/guard/verify_agent_config.py").read_text(
        encoding="utf-8"
    )
    assert '"suppressions",' in facade


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


@pytest.mark.parametrize(
    "relative",
    [
        "packages/example/assets/check.py",
        "packages/example/assets/service.py.template",
    ],
)
def test_conventions_gate_enforces_docstring_contract_in_assets(
    tmp_path: Path, relative: str
) -> None:
    root = _conventions_root(tmp_path)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    signature = '"""Module."""\n\n\ndef pair(first: int, second: int) -> int:\n'
    path.write_text(
        f'{signature}    """Add two counts.\n\n    Args:\n'
        "        first (str): Left operand.\n        second (int): Right operand.\n"
        '    """\n    return first + second\n',
        encoding="utf-8",
    )

    assert conventions_module.run(root) == 1
    path.write_text(
        f'{signature}    """Add two counts.\n\n    Args:\n'
        "        first (int): Left operand.\n        second (int): Right operand.\n"
        '    """\n    return first + second\n',
        encoding="utf-8",
    )
    assert conventions_module.run(root) == 0


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
    path.write_text('"""Module."""\n\n_TIMEOUT = 30\nwait = 30\n', encoding="utf-8")

    assert conventions_module.run(root) == 1
    path.write_text(
        '"""Module."""\n\n_TIMEOUT = 30\nwait = _TIMEOUT\n', encoding="utf-8"
    )
    assert conventions_module.run(root) == 0


def test_conventions_gate_keeps_literal_test_expectations(tmp_path: Path) -> None:
    root = _conventions_root(tmp_path)
    (root / "tests/test_values.py").write_text(
        "def test_size() -> None:\n    assert len([1, 2]) == 2\n", encoding="utf-8"
    )

    assert conventions_module.run(root) == 0
