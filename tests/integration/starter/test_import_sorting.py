"""Verify import sections with the actual Ruff binary, including after relocation."""

from pathlib import Path
import shutil
import subprocess
import sys

from copier import run_copy
import pytest

_ROOT = Path(__file__).resolve().parents[3]
_TIMEOUT_SECONDS = 30
_COMMIT = "1234567890abcdef1234567890abcdef12345678"


@pytest.fixture(scope="module")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # A short module-level root keeps long template names under Windows MAX_PATH.
    source = tmp_path_factory.mktemp("source")
    shutil.copyfile(_ROOT / "copier.yml", source / "copier.yml")
    shutil.copytree(
        _ROOT / "packages/starter/template", source / "packages/starter/template"
    )
    return source


@pytest.fixture(scope="module")
def generated_app(
    tmp_path_factory: pytest.TempPathFactory, template_source: Path
) -> Path:
    destination = tmp_path_factory.mktemp("import-sorting-consumer")
    run_copy(
        str(template_source),
        destination,
        data={"service": "api", "kit_commit": _COMMIT},
        defaults=True,
        quiet=True,
    )
    return destination


def _sort(*, root: Path, filename: Path, first_party: str) -> str:
    result = subprocess.run(  # noqa: S603 - installed linter with synthetic stdin
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--ignore",
            "F401",
            "--fix-only",
            "--stdin-filename",
            str(filename),
            "-",
        ],
        cwd=root,
        input=f"import {first_party}\nimport fastapi\nimport json\n",
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize(
    "first_party", ["agent_kit", "platform_kit_runtime", "delivery_tools"]
)
def test_toolkit_imports_have_separate_standard_external_and_local_sections(
    first_party: str,
) -> None:
    assert (
        _sort(
            root=_ROOT,
            filename=_ROOT / "src/agent_kit/import_probe.py",
            first_party=first_party,
        )
        == f"import json\n\nimport fastapi\n\nimport {first_party}\n"
    )


@pytest.mark.parametrize(
    "filename", ["src/app/import_probe.py", "tests/import_probe.py"]
)
def test_generated_app_import_sections_use_src_discovery_after_relocation(
    generated_app: Path, filename: str
) -> None:
    assert (
        _sort(
            root=generated_app,
            filename=generated_app / filename,
            first_party="app",
        )
        == "import json\n\nimport fastapi\n\nimport app\n"
    )


def test_runtime_package_is_external_to_the_generated_app(generated_app: Path) -> None:
    assert (
        _sort(
            root=generated_app,
            filename=generated_app / "src/app/import_probe.py",
            first_party="platform_kit_runtime",
        )
        == "import json\n\nimport fastapi\nimport platform_kit_runtime\n"
    )


@pytest.mark.parametrize("iac", ["bicep", "terraform"])
def test_generated_cloud_scripts_pass_the_projects_own_lint(
    tmp_path: Path, template_source: Path, iac: str
) -> None:
    project = tmp_path / "project"
    run_copy(
        str(template_source),
        project,
        data={
            "service": "api",
            "iac": iac,
            "data": "postgresql",
            "ai_service": "text",
            "kit_commit": _COMMIT,
        },
        defaults=True,
        quiet=True,
    )
    taskfile = (project / "Taskfile.yml").read_text(encoding="utf-8")
    assert "ruff check src tests scripts\n" in taskfile
    assert "ruff format --check src tests scripts\n" in taskfile
    for arguments in (["format", "--check"], ["check"]):
        result = subprocess.run(  # noqa: S603 - installed linter on rendered output
            [sys.executable, "-m", "ruff", *arguments, "--no-cache", "scripts"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
