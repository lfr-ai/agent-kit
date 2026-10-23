"""Resource depth is a delivery contract, not a skill-name coverage claim."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import apm_smoke
from scripts.apm_smoke import (
    _SMOKE_SELECTIONS,
    fixture_environment,
    resource_failures,
)
from scripts.check_resources import check, inventory

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_ROOT = Path(__file__).resolve().parents[3]
_SELF_CHECKS = sorted(
    path
    for path in (_ROOT / "packages").glob("*/.apm/skills/*/assets/**/*.py")
    if path.name
    not in {
        "check_python.py",  # Covered by test_convention_asset.py.
        "check_backend_wiring.py",  # Explicit-input CLI regressions below.
        "check_method_ordering.py",
        "check_response_model_redundancy.py",  # test_portable_backend_cli.py.
        "compare_openapi.py",
        "check_port_adapter_binding.py",
        "verify_stream_events.py",  # Dedicated test_ai_resources.py contracts.
        "verify_queue_messages.py",
        "__init__.py",
    }
)


def _skill(root: Path) -> Path:
    path = root / "packages/example/.apm/skills/kit-example"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        "---\nname: kit-example\ndescription: Use when testing.\nlicense: MIT\n---\n"
        "1. Read [guide](references/guide.md).\n",
        encoding="utf-8",
    )
    (path / "references").mkdir()
    (path / "references/guide.md").write_text(
        "# Guide\n\nUse the [worksheet](../assets/case.md.template).\n",
        encoding="utf-8",
    )
    (path / "assets").mkdir()
    (path / "assets/case.md.template").write_text(
        "# Case\n\n- Expected behavior:\n- Actual evidence:\n", encoding="utf-8"
    )
    return path


def test_transitively_linked_resources_are_deliverable(tmp_path: Path) -> None:
    _skill(tmp_path)
    assert check(tmp_path) == []
    assert inventory(tmp_path)[0]["references"] == ["references/guide.md"]
    assert inventory(tmp_path)[0]["assets"] == ["assets/case.md.template"]


def test_checklist_only_skill_fails(tmp_path: Path) -> None:
    path = _skill(tmp_path)
    (path / "references/guide.md").unlink()
    (path / "assets/case.md.template").unlink()
    failures = check(tmp_path)
    assert any("reference" in failure for failure in failures)
    assert any("asset" in failure for failure in failures)


def test_unlinked_decorative_resource_does_not_satisfy_gate(tmp_path: Path) -> None:
    path = _skill(tmp_path)
    (path / "references/guide.md").write_text("# No asset link\n", encoding="utf-8")
    assert any("reachable asset" in failure for failure in check(tmp_path))


def test_invalid_python_resource_is_rejected_without_execution(
    tmp_path: Path,
) -> None:
    path = _skill(tmp_path)
    (path / "assets/check.py").write_text("if :\n", encoding="utf-8")
    assert any("Python syntax" in failure for failure in check(tmp_path))


def test_nested_skill_template_is_not_an_authored_capability(tmp_path: Path) -> None:
    path = _skill(tmp_path)
    (path / "assets/SKILL.md.template").write_text("Example only\n", encoding="utf-8")
    assert len(inventory(tmp_path)) == 1


def test_empty_resource_tree_is_not_success(tmp_path: Path) -> None:
    assert check(tmp_path) == ["no canonical skills found"]


def test_real_delivery_check_detects_missing_and_changed_resource_bytes(
    tmp_path: Path,
) -> None:
    relative = "kit-example/assets/check.py"
    expected = {relative: b"original"}
    assert resource_failures(expected, destination=tmp_path) == [relative]
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"altered")
    assert resource_failures(expected, destination=tmp_path) == [relative]
    target.write_bytes(b"original")
    assert resource_failures(expected, destination=tmp_path) == []
    unexpected = target.parent / "AGENTS.md"
    unexpected.write_bytes(b"unexpected always-on context")
    assert resource_failures(expected, destination=tmp_path) == [
        "kit-example/assets/AGENTS.md"
    ]


def test_apm_fixture_home_is_local_and_does_not_mutate_parent_environment(
    tmp_path: Path,
) -> None:
    parent = {"HOME": "original", "USERPROFILE": "original", "PATH": "tool-path"}
    isolated = fixture_environment(parent, home=tmp_path)
    assert isolated["HOME"] == str(tmp_path)
    assert isolated["USERPROFILE"] == str(tmp_path)
    assert isolated["APM_HOME"] == str(tmp_path / ".apm")
    assert isolated["PATH"] == "tool-path"
    assert parent == {
        "HOME": "original",
        "USERPROFILE": "original",
        "PATH": "tool-path",
    }


def test_apm_command_timeout_remains_an_actionable_system_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeout errors keep the bounded command context and retain their cause."""
    command = ["toolkit", "compose", "backend"]
    timeout = subprocess.TimeoutExpired(command, timeout=5)

    def fail_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise timeout

    monkeypatch.setattr(apm_smoke.subprocess, "run", fail_run)
    with pytest.raises(
        SystemExit, match=r"Timed out after .*s: compose backend"
    ) as error:
        apm_smoke.run(command, cwd=tmp_path, env={})

    assert error.value.__cause__ is timeout


@pytest.mark.parametrize(
    "script", _SELF_CHECKS, ids=lambda path: f"{path.parent.parent.name}/{path.name}"
)
def test_portable_checkers_retain_runnable_self_checks(script: Path) -> None:
    """Run trusted source regressions, never consumer code or external services."""
    result = subprocess.run(  # noqa: S603 - repository-owned explicit checkers
        [sys.executable, str(script), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=script.parent,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "self" in result.stdout.casefold(), result.stdout + result.stderr


@pytest.mark.parametrize(
    ("filename", "relative", "arguments", "valid", "invalid", "diagnostic"),
    [
        (
            "check_backend_wiring.py",
            "demo/presentation/api.py",
            ("--package", "demo"),
            "from demo.application import services\n",
            "from demo.infrastructure import storage\n",
            "forbidden layer 'infrastructure'",
        ),
        (
            "check_method_ordering.py",
            "helpers.py",
            (),
            "def entry():\n    return _helper()\n\ndef _helper():\n    return 1\n",
            "def _helper():\n    return 1\n\ndef entry():\n    return _helper()\n",
            "defined before its sole caller",
        ),
    ],
)
def test_explicit_input_python_checkers_have_behavioral_cli_regressions(
    tmp_path: Path,
    filename: str,
    relative: str,
    arguments: tuple[str, ...],
    valid: str,
    invalid: str,
    diagnostic: str,
) -> None:
    """Check actual valid/invalid results without adding a self-test-only CLI flag."""
    script = _ROOT / "packages/backend/.apm/skills/kit-python-service/assets" / filename
    source = tmp_path / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    for text, expected in ((valid, 0), (invalid, 1)):
        source.write_text(text, encoding="utf-8")
        result = subprocess.run(  # noqa: S603 - first-party checker, synthetic input
            [sys.executable, str(script), str(tmp_path), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        if expected:
            assert diagnostic in result.stdout


def test_composed_all_stack_delivery_retains_resources_and_complete_role_roster() -> (
    None
):
    """Resource depth and all 24 baseline roles must reach the selected package."""
    snapshot = FileCatalogAdapter().load(_ROOT)
    plan = CatalogService().compose(
        snapshot,
        "fullstack",
        ("iac", "workflows", "ai"),
        ("copilot", "claude"),
        skills=(),
    )
    files = {item.relative_path: item.content for item in plan.files}
    assert json.loads(files["apm.yml"])["compilation"] == {
        "exclude": [".apm/skills", ".agents/skills", ".claude/skills"]
    }
    for bundle in snapshot.bundles:
        if bundle.name not in plan.bundles:
            continue
        for document in bundle.files:
            if not document.is_directory and any(
                f"/{kind}/" in document.relative_path
                for kind in ("references", "assets")
            ):
                assert files[f".apm/{document.relative_path}"] == document.content
    baseline = json.loads(
        (_ROOT / ".agents/agentic-setup/coverage.json").read_text(encoding="utf-8")
    )
    roles = set(baseline["agents"].values())
    for prefix, suffix in (
        (".github/agents/", ".agent.md"),
        (".claude/agents/", ".md"),
    ):
        native_paths = [path for path in files if path.startswith(prefix)]
        assert len(native_paths) == len(roles)
        actual = {path.rsplit("/", 1)[-1].removesuffix(suffix) for path in native_paths}
        assert actual == roles


def test_bounded_smoke_matrix_covers_every_portable_bundle() -> None:
    """Split runtime work, never reduce the checked library to fit timeouts."""
    snapshot = FileCatalogAdapter().load(_ROOT)
    selected: set[str] = set()
    for profile, features in _SMOKE_SELECTIONS:
        plan = CatalogService().compose(snapshot, profile, features, (), skills=())
        selected.update(plan.bundles)
    assert selected == {
        bundle.name for bundle in snapshot.bundles if bundle.kind == "portable"
    }
