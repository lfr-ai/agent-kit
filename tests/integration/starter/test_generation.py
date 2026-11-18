"""Exercise Copier's APM onboarding foundation without installing capabilities."""

from pathlib import Path
import shutil
import subprocess
import tomllib

from apm_cli.policy.parser import load_policy
from apm_cli.policy.policy_checks import run_policy_checks
from copier import run_copy
import pytest
import yaml

from agent_kit.infrastructure.apm import APM_VERSION

_ROOT = Path(__file__).resolve().parents[3]
_TASK_TIMEOUT_SECONDS = 180


@pytest.fixture(scope="module")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy only generator sources, without Git or repository-local state."""
    source = tmp_path_factory.mktemp("starter-source")
    shutil.copyfile(_ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", source / "packages/starter/template"
    )
    return source


@pytest.mark.parametrize(
    ("kind", "ai", "identity", "iac", "profile"),
    [
        ("library", False, False, "none", "starter-library"),
        ("backend", False, False, "none", "starter-backend"),
        ("frontend", False, True, "bicep", "starter-frontend-identity-bicep"),
        (
            "fullstack",
            True,
            True,
            "terraform",
            "starter-fullstack-ai-identity-terraform",
        ),
    ],
)
def test_starter_declares_one_profile_without_copying_capabilities(
    template_source: Path,
    tmp_path: Path,
    kind: str,
    ai: bool,
    identity: bool,
    iac: str,
    profile: str,
) -> None:
    destination = tmp_path / "consumer"
    run_copy(
        str(template_source),
        destination,
        data={
            "project_name": "example-app",
            "kind": kind,
            "ai": ai,
            "identity": identity,
            "iac": iac,
            "agent_provider": ["copilot", "claude"],
        },
        defaults=True,
        quiet=True,
    )
    manifest = yaml.safe_load((destination / "apm.yml").read_text(encoding="utf-8"))
    assert manifest["license"] == "LicenseRef-Proprietary"
    assert manifest["dependencies"]["apm"] == [
        f"lfr-ai/agent-kit/profiles/starters/{profile.removeprefix('starter-')}#v0.1.0"
    ]
    assert manifest["targets"] == ["copilot", "claude"]
    assert not (destination / "apm.lock.yaml").exists()
    assert not (destination / ".apm").exists()
    assert not (destination / ".agents").exists()
    assert not (destination / ".claude").exists()
    assert not (destination / ".github").exists()
    for scaffold in [".env.example", "src", "tests"]:
        assert not (destination / scaffold).exists()
    project = tomllib.loads(
        (destination / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert project["dependency-groups"]["dev"] == [f"apm-cli=={APM_VERSION}"]
    assert "dependencies" not in project["project"]
    assert "ruff" not in project.get("tool", {})
    taskfile = (destination / "Taskfile.yml").read_text(encoding="utf-8")
    assert "apm install --frozen --target copilot,claude --no-trust-bin" in taskfile
    assert "apm compile --target copilot" in taskfile
    assert "apm compile --target claude" in taskfile
    assert "apm audit --ci --policy ./apm-policy.yml" in taskfile
    assert "--no-policy" not in taskfile
    assert "--force" not in taskfile


@pytest.mark.parametrize(
    "project_name",
    ["../escape", "a;echo", "a b", "CON", "com2", "lpt9", "app\n", "a" * 65, ""],
)
def test_starter_rejects_unsafe_names(
    template_source: Path, tmp_path: Path, project_name: str
) -> None:
    with pytest.raises(ValueError, match="Use a lowercase hyphenated project name"):
        run_copy(
            str(template_source),
            tmp_path / "rejected",
            data={"project_name": project_name},
            defaults=True,
            quiet=True,
        )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"kind": "library", "ai": True}, "AI capabilities require"),
        ({"kind": "frontend", "ai": True}, "AI capabilities require"),
        (
            {"kind": "library", "identity": True},
            "library starter does not select identity",
        ),
        (
            {"kind": "library", "iac": "bicep"},
            "library starter does not select infrastructure",
        ),
        ({"agent_provider": []}, "Select at least one agent target"),
        ({"agent_provider": ["unknown"]}, "Invalid choice"),
    ],
)
def test_starter_rejects_unsupported_combinations(
    template_source: Path,
    tmp_path: Path,
    data: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        run_copy(
            str(template_source),
            tmp_path / "rejected",
            data=data,
            defaults=True,
            quiet=True,
        )


@pytest.mark.parametrize("target", ["copilot", "claude"])
def test_starter_preserves_one_selected_target(
    template_source: Path, tmp_path: Path, target: str
) -> None:
    destination = tmp_path / target
    run_copy(
        str(template_source),
        destination,
        data={"agent_provider": [target]},
        defaults=True,
        quiet=True,
    )
    manifest = yaml.safe_load((destination / "apm.yml").read_text(encoding="utf-8"))
    assert manifest["targets"] == [target]
    taskfile = yaml.safe_load(
        (destination / "Taskfile.yml").read_text(encoding="utf-8")
    )
    for task in ["setup", "ci"]:
        commands = taskfile["tasks"][task]["cmds"]
        compile_commands = [
            command
            for command in commands
            if isinstance(command, str) and "apm compile" in command
        ]
        assert compile_commands == [
            f"uv run --locked --no-sync apm compile --target {target}"
        ]


def test_starter_has_no_generation_scripts() -> None:
    config = yaml.safe_load((_ROOT / "copier.yml").read_text(encoding="utf-8"))
    assert not config.get("_tasks")
    assert not config.get("_migrations")
    assert not config.get("_jinja_extensions")


@pytest.mark.parametrize(
    ("includes", "explicit"),
    [([], True), (None, False), ("auto", False)],
)
@pytest.mark.parametrize(
    "relative",
    [
        "packages/starter/template/apm-policy.yml.jinja",
        ".apm/skills/kit-apm-adopt/assets/apm-policy.yml.template",
    ],
)
def test_consumer_policy_requires_explicit_consent_not_local_source(
    tmp_path: Path, includes: object, explicit: bool, relative: str
) -> None:
    policy, warnings = load_policy(_ROOT / relative)
    assert not warnings
    manifest: dict[str, object] = {
        "name": "consumer",
        "version": "0.1.0",
        "license": "LicenseRef-Proprietary",
        "dependencies": {},
        "executables": {},
    }
    if includes is not None:
        manifest["includes"] = includes
    (tmp_path / "apm.yml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    result = run_policy_checks(tmp_path, policy, fail_fast=False)
    checks = {check.name: check.passed for check in result.checks}
    assert checks["required-manifest-fields"]
    assert checks["explicit-includes"] is explicit
    assert result.passed is explicit


def test_starter_task_commands_parse_without_installing(
    template_source: Path, tmp_path: Path
) -> None:
    executable = shutil.which("task")
    if executable is None:
        pytest.skip("Task is unavailable")
    destination = tmp_path / "consumer"
    run_copy(str(template_source), destination, defaults=True, quiet=True)
    before = {
        path.relative_to(destination): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }
    for task in ["setup", "ci"]:
        result = subprocess.run(  # noqa: S603 - resolved Task; fixed dry-run arguments
            [executable, "--dry", task],
            cwd=destination,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TASK_TIMEOUT_SECONDS,
        )
        assert result.returncode == 0, result.stderr
        assert "apm install" in result.stdout + result.stderr
        assert "apm audit --ci --policy ./apm-policy.yml" in (
            result.stdout + result.stderr
        )
    after = {
        path.relative_to(destination): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert after == before
