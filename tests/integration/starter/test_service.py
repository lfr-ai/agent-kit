"""Exercise the optional starter API scaffold offline, without installing anything."""

import ast
from configparser import ConfigParser
from dataclasses import fields
from importlib.metadata import packages_distributions
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tomllib

from copier import run_copy
import pytest
import yaml

from agent_kit.infrastructure.apm import APM_VERSION
from platform_kit_runtime import RuntimeConfig

_ROOT = Path(__file__).resolve().parents[3]
_PINS = runpy.run_path(
    str(_ROOT / "packages/shared/.apm/skills/kit-verify-change/assets/check_pins.py")
)
_TIMEOUT_SECONDS = 180
_COMMIT = "1234567890abcdef1234567890abcdef12345678"
_STAGES = 2  # locked build stage, then the slim runtime stage
_MODULE = "app"
# Installed capability files that the service checks must not lint or collect.
_UNCHECKED = "import sys\nimport os\ndef test_probe():\n    assert False\n"
_KIT_CI = "lfr-ai/agent-kit/.github/workflows/delivery-python-ci.yml"
_SHA_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_COOLDOWN_DAYS = 14  # documented release-settling window for version updates
_FOUNDATION = {
    ".copier-answers.yml",
    ".gitignore",
    ".vscode/extensions.json",
    "README.md",
    "Taskfile.yml",
    "apm-policy.yml",
    "apm.yml",
    "pyproject.toml",
}
_SCAFFOLD = {
    ".dockerignore",
    ".env.example",
    ".env.dev.example",
    ".env.test.example",
    ".env.staging.example",
    ".env.prod.example",
    ".github/dependabot.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/image.yml",
    ".vscode/launch.json",
    "Dockerfile",
    "compose.yaml",
    "pytest.ini",
    "ruff.toml",
    "src/app/__init__.py",
    "src/app/main.py",
    "src/app/logging.py",
    "src/app/settings.py",
    "tests/test_health.py",
    "tests/test_settings.py",
    "tests/conftest.py",
}
_ENV_PREFIX = "APP_"
_IAC_EXTENSIONS = {"hashicorp.terraform", "ms-azuretools.vscode-bicep"}


@pytest.fixture(scope="module")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy only generator sources, without Git or repository-local state."""
    source = tmp_path_factory.mktemp("starter-source")
    shutil.copyfile(_ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", source / "packages/starter/template"
    )
    return source


def _generate(source: Path, destination: Path, service: str | None) -> Path:
    data: dict[str, object] = {"project_name": "example-app"}
    if service is not None:
        data["service"] = service
        data["kit_commit"] = _COMMIT
    run_copy(str(source), destination, data=data, defaults=True, quiet=True)
    return destination


@pytest.fixture(scope="module")
def foundation(template_source: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _generate(template_source, tmp_path_factory.mktemp("none"), None)


@pytest.fixture(scope="module")
def scaffold(template_source: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _generate(template_source, tmp_path_factory.mktemp("api"), "api")


def _files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }


def _text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _run(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - resolved executables; fixed offline arguments
        arguments,
        cwd=cwd,
        env={
            **os.environ,
            "PYTHONPATH": "src",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DEBUG_TEMPROOT": str(cwd),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )


def test_default_service_keeps_the_onboarding_foundation_unchanged(
    foundation: Path,
) -> None:
    assert _files(foundation) == _FOUNDATION
    answers = yaml.safe_load(_text(foundation, ".copier-answers.yml"))
    assert answers["service"] == "none"
    assert _text(foundation, "pyproject.toml") == (
        "[project]\n"
        'name = "example-app"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.13"\n'
        "\n"
        "[dependency-groups]\n"
        f'dev = ["apm-cli=={APM_VERSION}"]\n'
        "\n"
        "[tool.uv]\n"
        "package = false\n"
        'required-version = ">=0.12.0,<0.14"\n'
    )
    assert _text(foundation, ".gitignore") == (
        ".venv/\napm_modules/\n__pycache__/\n.pytest_cache/\n.ruff_cache/\n"
    )
    taskfile = _text(foundation, "Taskfile.yml")
    assert "--policy ./apm-policy.yml\n\n  ci:\n" in taskfile
    assert taskfile.endswith("\n      - task: verify\n")
    assert "ruff" not in taskfile
    assert "pytest" not in taskfile
    readme = _text(foundation, "README.md")
    assert readme.endswith("hosted on GitHub or Azure DevOps.\n")
    assert "## Application service" not in readme


def test_library_answers_do_not_record_a_service(
    template_source: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "library"
    run_copy(
        str(template_source),
        destination,
        data={"project_name": "example-app", "kind": "library"},
        defaults=True,
        quiet=True,
    )
    answers = yaml.safe_load(_text(destination, ".copier-answers.yml"))
    assert "service" not in answers
    assert _files(destination) == _FOUNDATION


def test_real_environment_files_are_ignored_but_examples_are_trackable(
    scaffold: Path, tmp_path: Path
) -> None:
    git = shutil.which("git")
    assert git is not None
    shutil.copyfile(scaffold / ".gitignore", tmp_path / ".gitignore")
    assert _run([git, "init", "--quiet"], tmp_path).returncode == 0
    working = {
        ".env",
        *(f".env.{stage}" for stage in ("dev", "test", "staging", "prod")),
    }
    examples = {f"{name}.example" for name in working}
    result = _run(
        [git, "check-ignore", "--no-index", *sorted(working | examples)], tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.splitlines()) == working


def test_api_service_adds_only_the_minimal_scaffold(scaffold: Path) -> None:
    assert _files(scaffold) == _FOUNDATION | _SCAFFOLD
    answers = yaml.safe_load(_text(scaffold, ".copier-answers.yml"))
    assert answers["service"] == "api"
    assert _text(scaffold, ".gitignore").endswith(
        ".env\n.env.*\n!.env.example\n!.env.*.example\ncompose.override.yaml\n"
    )
    main = _text(scaffold, "src/app/main.py")
    assert "from app.settings import load_settings" in main
    assert "probes=()" in main
    assert "RuntimeConfig" not in main
    readme = _text(scaffold, "README.md")
    for heading in [
        "### Configuration",
        "### Run locally",
        "### Test",
        "### Build the image",
        "### Deployment boundaries",
    ]:
        assert heading in readme
    assert "uvicorn app.main:app" in readme


@pytest.mark.parametrize("kind", ["backend", "fullstack"])
def test_api_explicit_no_iac_emits_no_infrastructure(
    template_source: Path, tmp_path: Path, kind: str
) -> None:
    destination = tmp_path / "no-iac"
    run_copy(
        str(template_source),
        destination,
        data={"kind": kind, "service": "api", "iac": "none", "kit_commit": _COMMIT},
        defaults=True,
        quiet=True,
    )
    answers = yaml.safe_load(_text(destination, ".copier-answers.yml"))
    assert answers["service"] == "api"
    assert answers["iac"] == "none"
    manifest = yaml.safe_load(_text(destination, "apm.yml"))
    assert manifest["dependencies"]["apm"] == [
        f"lfr-ai/agent-kit/profiles/starters/{kind}#v0.1.0"
    ]
    assert _files(destination) == _FOUNDATION | _SCAFFOLD
    editor = json.loads(_text(destination, ".vscode/extensions.json"))
    assert _IAC_EXTENSIONS.isdisjoint(editor["recommendations"])


def test_api_dependabot_refreshes_every_pin_the_scaffold_ships(
    template_source: Path, scaffold: Path, tmp_path: Path
) -> None:
    config = yaml.safe_load(_text(scaffold, ".github/dependabot.yml"))
    assert config["version"] == 2
    updates = {item["package-ecosystem"]: item for item in config["updates"]}
    assert set(updates) == {"github-actions", "docker", "uv"}
    for item in updates.values():
        assert item["directory"] == "/"
        assert item["schedule"]["interval"] == "weekly"
        assert item["cooldown"]["default-days"] == _COOLDOWN_DAYS
        assert item["groups"]
    # Each ecosystem has a generated pin to maintain at the configured directory.
    assert _DIGEST.search(_text(scaffold, "Dockerfile").split("FROM ")[1].split()[0])
    assert (scaffold / "pyproject.toml").is_file()
    assert _SHA_PINNED.match(
        yaml.safe_load(_text(scaffold, ".github/workflows/image.yml"))["jobs"]["image"][
            "steps"
        ][0]["uses"]
    )

    services = tmp_path / "services"
    run_copy(
        str(template_source),
        services,
        data={
            "service": "api",
            "iac": "none",
            "data": "postgresql",
            "cache": "redis",
            "kit_commit": _COMMIT,
        },
        defaults=True,
        quiet=True,
    )
    compose_images = [
        service["image"]
        for service in yaml.safe_load(_text(services, "compose.yaml"))[
            "services"
        ].values()
        if "image" in service
    ]
    assert len(compose_images) == 2
    assert all(_DIGEST.search(image) for image in compose_images)
    compose = {
        item["package-ecosystem"]: item
        for item in yaml.safe_load(_text(services, ".github/dependabot.yml"))["updates"]
    }["docker-compose"]
    assert compose["directory"] == "/"
    assert compose["cooldown"]["default-days"] == _COOLDOWN_DAYS
    assert compose["groups"]

    azure = tmp_path / "azure"
    run_copy(
        str(template_source),
        azure,
        data={
            "service": "api",
            "ci": "azure-devops",
            "iac": "none",
            "kit_commit": _COMMIT,
            "project_name": "example-app",
        },
        defaults=True,
        quiet=True,
    )
    assert not (azure / ".github").exists()


@pytest.mark.parametrize(
    ("iac", "extension"),
    [
        ("bicep", "ms-azuretools.vscode-bicep"),
        ("terraform", "hashicorp.terraform"),
    ],
)
def test_selected_iac_recommends_only_its_editor_extension(
    template_source: Path, tmp_path: Path, iac: str, extension: str
) -> None:
    destination = tmp_path / "iac-editor"
    run_copy(
        str(template_source),
        destination,
        data={"service": "api", "iac": iac, "kit_commit": _COMMIT},
        defaults=True,
        quiet=True,
    )
    editor = json.loads(_text(destination, ".vscode/extensions.json"))
    assert _IAC_EXTENSIONS.intersection(editor["recommendations"]) == {extension}
    assert _files(destination) >= _FOUNDATION | _SCAFFOLD


def test_api_editor_recommends_only_applicable_tools(scaffold: Path) -> None:
    editor = json.loads(_text(scaffold, ".vscode/extensions.json"))
    recommended = set(editor["recommendations"])
    assert {
        "charliermarsh.ruff",
        "github.vscode-github-actions",
        "ms-azuretools.vscode-containers",
        "ms-python.python",
    } <= recommended
    assert _IAC_EXTENSIONS.isdisjoint(recommended)
    assert {"ms-playwright.playwright", "vitest.explorer"}.isdisjoint(recommended)
    assert "ms-azuretools.vscode-docker" in editor["unwantedRecommendations"]


def test_api_has_one_debug_launch_matching_the_dev_task(scaffold: Path) -> None:
    (launch,) = json.loads(_text(scaffold, ".vscode/launch.json"))["configurations"]
    assert (launch["type"], launch["module"]) == ("debugpy", "uvicorn")
    assert launch["args"][0] == f"{_MODULE}.main:app"
    assert " ".join(launch["args"]) in _text(scaffold, "Taskfile.yml")


def test_api_tools_use_dedicated_configuration_files(scaffold: Path) -> None:
    project = tomllib.loads(_text(scaffold, "pyproject.toml"))
    assert set(project["tool"]) == {"uv"}
    ruff = tomllib.loads(_text(scaffold, "ruff.toml"))
    assert {"ANN", "D", "FBT", "PL", "S"} <= set(ruff["lint"]["extend-select"])
    assert ruff["lint"]["pydocstyle"] == {"convention": "google"}
    assert ruff["lint"]["per-file-ignores"] == {"tests/**": ["D", "PLR2004", "S101"]}
    pytest_config = ConfigParser()
    pytest_config.read_string(_text(scaffold, "pytest.ini"))
    assert pytest_config.sections() == ["pytest"]
    assert dict(pytest_config["pytest"]) == {
        "strict": "true",
        "filterwarnings": "error",
        "testpaths": "tests",
    }


def test_api_test_task_passes_selectors(scaffold: Path) -> None:
    task = shutil.which("task")
    if task is None:
        pytest.skip("Task is required to verify generated selector forwarding.")
    result = _run(
        [task, "--dry", "test", "--", "tests/test_health.py", "-k", "live"],
        scaffold,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "pytest tests/test_health.py -k live" in output
    assert "pytest tests tests/test_health.py" not in output


def test_api_settings_map_every_runtime_field_to_one_documented_variable(
    scaffold: Path,
) -> None:
    module = ast.parse(_text(scaffold, "src/app/settings.py"))
    settings = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    declared = {
        statement.target.id: ast.unparse(statement.value)
        for statement in settings.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.value is not None
    }
    runtime = [field.name for field in fields(RuntimeConfig)]
    assert list(declared) == runtime
    assert declared == {name: f"_RUNTIME_DEFAULTS.{name}" for name in runtime}
    assert f'env_prefix="{_ENV_PREFIX}"' in _text(scaffold, "src/app/settings.py")
    documented = [
        line.removeprefix("# ").partition("=")[0]
        for line in _text(scaffold, ".env.example").splitlines()
        if line.startswith(f"# {_ENV_PREFIX}")
    ]
    assert documented == [f"{_ENV_PREFIX}{name.upper()}" for name in runtime]
    readme = _text(scaffold, "README.md")
    configuration = readme.partition("### Configuration\n")[2].partition("\n### ")[0]
    runtime_project = tomllib.loads(_text(_ROOT, "packages/runtime/pyproject.toml"))
    extras = runtime_project["project"]["optional-dependencies"]
    assert extras
    assert all(f"`{extra}`" in configuration for extra in extras)
    for phrase in [".env.example", "platform-kit-runtime[<extra>]", "then `.env`"]:
        assert phrase in configuration


def test_api_project_pins_the_runtime_release_and_reviewed_tools(
    scaffold: Path,
) -> None:
    project = tomllib.loads(_text(scaffold, "pyproject.toml"))
    runtime = tomllib.loads(_text(_ROOT, "packages/runtime/pyproject.toml"))
    repository = tomllib.loads(_text(_ROOT, "pyproject.toml"))
    assert project["project"]["dependencies"][0] == (
        f"platform-kit-runtime>={runtime['project']['version']},<0.2"
    )
    assert [
        requirement.partition(">=")[0]
        for requirement in project["project"]["dependencies"]
    ] == ["platform-kit-runtime", "pydantic-settings", "uvicorn"]
    assert project["tool"]["uv"]["sources"]["platform-kit-runtime"] == {
        "git": "https://github.com/lfr-ai/agent-kit",
        "subdirectory": "packages/runtime",
        "rev": _COMMIT,
    }
    assert "package" not in project["tool"]["uv"]
    assert project["build-system"]["build-backend"] == "uv_build"
    assert project["tool"]["uv"]["build-backend"] == {"module-name": _MODULE}
    assert _MODULE not in sys.stdlib_module_names
    assert _MODULE not in packages_distributions()
    reviewed = set(repository["dependency-groups"]["dev"])
    development = set(project["dependency-groups"]["dev"])
    assert f"apm-cli=={APM_VERSION}" in development
    assert {"go-task-bin", "httpx", "pytest", "ruff"} <= {
        requirement.partition("==")[0] for requirement in development
    }
    assert development <= reviewed
    assert _PINS["scan"](scaffold) == []


def test_api_dockerfile_is_locked_multistage_and_non_root(scaffold: Path) -> None:
    dockerfile = _text(scaffold, "Dockerfile")
    instructions = [
        line.split(maxsplit=1)
        for line in dockerfile.splitlines()
        if line and not line.startswith((" ", "#"))
    ]
    bases = [rest.split()[0] for keyword, rest in instructions if keyword == "FROM"]
    assert len(bases) == _STAGES
    assert all(_DIGEST.search(base) for base in bases)
    runtime_stage = dockerfile.rpartition("\nFROM ")[2]
    assert "USER 10001:10001" in runtime_stage
    assert "EXPOSE 8080" in runtime_stage
    assert "COPY --from=builder /app/.venv /app/.venv" in runtime_stage
    assert '"app.main:app"' in runtime_stage
    assert '"--port", "8080"' in runtime_stage
    assert "uv sync --locked --no-dev --no-install-project" in dockerfile
    assert "uv sync --locked --no-dev --no-editable" in dockerfile
    assert "ADD " not in dockerfile
    patterns = [
        line
        for line in _text(scaffold, ".dockerignore").splitlines()
        if line and not line.startswith("#")
    ]
    assert patterns == [
        "*",
        "!pyproject.toml",
        "!uv.lock",
        "!src/",
        "**/__pycache__",
        "**/*.py[co]",
    ]
    hadolint = shutil.which("hadolint")
    if hadolint is None:
        return
    result = _run([hadolint, "--no-color", "Dockerfile"], scaffold)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_compose_is_local_and_optional(scaffold: Path) -> None:
    text = _text(scaffold, "compose.yaml")
    services = yaml.safe_load(_text(scaffold, "compose.yaml"))["services"]
    assert isinstance(services, dict)
    assert set(services) == {"app"}
    assert "profiles" not in services["app"]
    assert services["app"]["env_file"] == [{"path": ".env", "required": False}]
    for service in services.values():
        assert all(port.startswith("127.0.0.1:") for port in service["ports"])
    assert "azure" not in text.lower()


@pytest.mark.parametrize("env_file", ["", "APP_TRACING=true\n"])
def test_api_compose_is_valid_for_docker(
    scaffold: Path, tmp_path: Path, env_file: str
) -> None:
    docker = shutil.which("docker")
    if docker is None or _run([docker, "compose", "version"], scaffold).returncode:
        pytest.skip("Docker Compose is unavailable")
    project = tmp_path / "project"
    shutil.copytree(scaffold, project)
    if env_file:
        (project / ".env").write_text(env_file, encoding="utf-8")
    result = _run(
        [
            docker,
            "compose",
            "--profile",
            "redis",
            "--profile",
            "postgres",
            "config",
            "--format",
            "json",
        ],
        project,
    )
    assert result.returncode == 0, result.stderr
    app = json.loads(result.stdout)["services"]["app"]
    assert app.get("environment", {}) == ({"APP_TRACING": "true"} if env_file else {})


def test_api_ci_calls_the_reusable_check_with_catalog_inputs(scaffold: Path) -> None:
    workflow = yaml.safe_load(_text(scaffold, ".github/workflows/ci.yml"))
    catalog = json.loads(_text(_ROOT, "packages/delivery/catalog.json"))
    contract = catalog["github"]["delivery-python-ci"]
    assert workflow["permissions"] == {}
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert list(jobs) == ["check"]
    job = jobs["check"]
    assert job["uses"] == f"{_KIT_CI}@{_COMMIT}"
    assert job["permissions"] == contract["permissions"]
    supplied = job["with"]
    assert set(supplied) <= set(contract["inputs"])
    required = {name for name, item in contract["inputs"].items() if item["required"]}
    assert required <= set(supplied)
    taskfile = yaml.safe_load(_text(scaffold, "Taskfile.yml"))
    assert supplied["task"] in taskfile["tasks"]


def test_api_image_workflow_is_pinned_least_privilege_and_attested(
    scaffold: Path,
) -> None:
    workflows = scaffold / ".github/workflows"
    assert {path.name for path in workflows.iterdir()} == {"ci.yml", "image.yml"}
    workflow = yaml.safe_load(_text(scaffold, ".github/workflows/image.yml"))
    assert workflow["permissions"] == {}
    triggers = workflow[True]
    assert isinstance(triggers, dict)
    assert "pull_request_target" not in triggers
    assert "image" in triggers["workflow_call"]["outputs"]
    job = workflow["jobs"]["image"]
    assert job["permissions"] == {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
    }
    steps = job["steps"]
    for step in steps:
        assert "uses" in step or "${{" not in step["run"]
        if "uses" in step:
            assert _SHA_PINNED.match(step["uses"]), step["uses"]
    by_action = {
        step["uses"].partition("@")[0]: step for step in steps if "uses" in step
    }
    assert by_action["actions/checkout"]["with"]["persist-credentials"] is False
    build = by_action["docker/build-push-action"]["with"]
    assert build["push"] is True
    assert build["provenance"] == "mode=max"
    assert build["sbom"] is True
    attest = by_action["actions/attest"]["with"]
    assert attest["subject-digest"] == "${{ steps.build.outputs.digest }}"
    assert attest["push-to-registry"] is True


def test_api_generated_project_passes_its_own_checks_offline(
    scaffold: Path, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    shutil.copytree(scaffold, project)
    for installed in [".agents", ".claude", ".github", "apm_modules"]:
        probe = project / installed / "skills/probe/test_probe.py"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(_UNCHECKED, encoding="utf-8")
    taskfile = _text(project, "Taskfile.yml")
    for command in ["ruff format --check src tests", "ruff check src tests"]:
        assert f"uv run --locked --no-sync {command}\n" in taskfile
    assert taskfile.endswith("uv run --locked --no-sync pytest {{.CLI_ARGS}}\n")
    assert yaml.safe_load(taskfile)["tasks"]["check"]["cmds"] == [
        "uv run --locked --no-sync ruff format src tests",
        "uv run --locked --no-sync ruff check --fix src tests",
        {"task": "test"},
    ]
    # Ruff and pytest discover the project's own dedicated configuration files.
    for arguments in [
        ["-m", "ruff", "format", "--check", "--no-cache", "src", "tests"],
        ["-m", "ruff", "check", "--no-cache", "src", "tests"],
        ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "error"],
    ]:
        result = _run([sys.executable, *arguments], project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No Python files found" not in result.stdout + result.stderr
    task = shutil.which("task")
    if task is None:
        return
    result = _run([task, "--dry", "ci"], scaffold)
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "ruff check" in output
    assert "pytest" in output


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"kind": "library", "service": "api"}, "api scaffold requires a backend"),
        ({"kind": "frontend", "service": "api"}, "api scaffold requires a backend"),
        ({"service": "web"}, "Invalid choice"),
    ],
)
def test_api_service_rejects_unsupported_answers(
    template_source: Path, tmp_path: Path, data: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_copy(
            str(template_source),
            tmp_path / "rejected",
            data=data,
            defaults=True,
            quiet=True,
        )
