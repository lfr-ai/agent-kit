"""Resource depth is a delivery contract, not a skill-name coverage claim."""

import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import sysconfig

import pytest
from scripts import apm_smoke
from scripts.apm_smoke import (
    _SMOKE_SELECTIONS,
    fixture_environment,
    resource_failures,
)
from scripts.check_docs import _local_targets
from scripts.check_resources import check, inventory

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.core.models import CatalogSnapshot, SourceDocument
from agent_kit.core.text import markdown_link_targets
from agent_kit.infrastructure import apm_adapter
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


@pytest.mark.parametrize("marker", ["```", "~~~~"])
def test_code_example_links_do_not_make_assets_discoverable(
    tmp_path: Path, marker: str
) -> None:
    path = _skill(tmp_path)
    guide = path / "references/guide.md"
    guide.write_text(
        f"# Guide\n\n{marker}markdown\n"
        "[example](../assets/case.md.template)\n"
        f"{marker}\n",
        encoding="utf-8",
    )

    assert any("reachable asset" in failure for failure in check(tmp_path))

    with guide.open("a", encoding="utf-8") as stream:
        stream.write("\nUse the [worksheet](../assets/case.md.template).\n")
    assert check(tmp_path) == []


def test_documentation_checker_ignores_fenced_code_not_actual_links() -> None:
    text = (
        "```python\n"
        "def logged[**P, R](function: Callable[P, R]) -> Callable[P, R]: ...\n"
        "[example](missing.md)\n"
        "```\n"
        "[actual](real.md)\n"
    )

    assert list(_local_targets(text)) == ["real.md"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("[empty]()", []),
        ("[page](page.md)\n![image](image.svg)", ["page.md", "image.svg"]),
        ('[page](<a b.md> "title")', ["a b.md"]),
        ("```python\n[fake](missing.md)\n", []),
        ("````python\n```\n[fake](missing.md)\n````\n[real](real.md)", ["real.md"]),
        ("~~~python\n```\n[fake](missing.md)\n~~~\n[real](real.md)", ["real.md"]),
        ("```lang`invalid\n[real](real.md)", ["real.md"]),
        ("````python\n```\n[fake](missing.md)\n", []),
        ("```python\n[fake](missing.md)\n```not-a-close\n[also](missing.md)", []),
        ("~~~python\r\n[fake](missing.md)\r\n~~~~ \t\r\n[real](real.md)", ["real.md"]),
    ],
)
def test_shared_inline_link_scanner_respects_fence_boundaries(
    text: str, expected: list[str]
) -> None:
    assert list(markdown_link_targets(text)) == expected


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


def _smoke_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, platform: str
) -> Path:
    """Model wheel launcher records without depending on the source checkout."""
    environment = tmp_path / "environment"
    if platform == "win32":
        scripts = environment / "Scripts"
        site = environment / "Lib/site-packages"
        launcher = "apm.exe"
        record = "../../Scripts/apm.exe"
    else:
        scripts = environment / "bin"
        site = environment / "lib/python3.13/site-packages"
        launcher = "apm"
        record = "../../../bin/apm"
    scripts.mkdir(parents=True)
    executable = scripts / launcher
    executable.write_bytes(b"approved launcher")
    executable.chmod(0o700)
    metadata = site / "apm_cli-0.33.0.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text(
        "Name: apm-cli\nVersion: 0.33.0\n", encoding="utf-8"
    )
    (metadata / "RECORD").write_text(f"{record},,\n", encoding="utf-8")
    distribution = importlib.metadata.PathDistribution(metadata)
    monkeypatch.setattr(importlib.metadata, "distribution", lambda _name: distribution)
    monkeypatch.setattr(sysconfig, "get_path", lambda _name: str(scripts))
    return executable


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("active_available", [False, True])
def test_smoke_never_invokes_foreign_path_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    platform: str,
    active_available: bool,
) -> None:
    approved = _smoke_installation(tmp_path, monkeypatch, platform=platform)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    for name in ("apm", "apm.exe", "agent-kit", "agent-kit.exe"):
        executable = foreign / name
        executable.write_bytes(b"foreign launcher")
        executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(foreign))
    monkeypatch.setattr(sys, "argv", ["apm-smoke", "--session"])
    if not active_available:
        approved.unlink()
    commands: list[list[str]] = []
    profiles: list[str] = []

    def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        commands.append(command)

    def smoke(
        profile: str,
        features: tuple[str, ...],
        *,
        apm: str,
        toolkit: str,
        env: dict[str, str],
        session_skills: tuple[str, ...],
    ) -> int:
        assert Path(apm) == approved
        assert env["APM_NO_SCRIPTS"] == "1"
        assert env["APM_NON_INTERACTIVE"] == "1"
        assert session_skills == ("kit-python-service",)
        profiles.append(profile)
        return 0

    monkeypatch.setattr(apm_smoke, "run", run)
    monkeypatch.setattr(apm_smoke, "smoke_profile", smoke)
    with monkeypatch.context() as platform_patch:
        platform_patch.setattr(sys, "platform", platform)
        result = apm_smoke.main()
    captured = capsys.readouterr()
    if active_available:
        assert result == 0
        assert len(commands) == 1
        assert profiles == ["backend"]
        assert captured.out == (
            "Released APM smoke passed; no live agent session is certified.\n"
        )
        assert captured.err == ""
    else:
        assert result == 1
        assert commands == []
        assert profiles == []
        assert captured.out == ""
        assert captured.err == "Use the locked toolkit environment.\n"


def test_smoke_uses_shared_approved_launcher_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = str(tmp_path / "approved-launcher")
    calls: list[str] = []

    def resolve() -> str:
        calls.append("resolve")
        return approved

    def which(name: str) -> str:
        assert name == "agent-kit"
        return "toolkit"

    def smoke(
        _profile: str, _features: tuple[str, ...], *, apm: str, **_kwargs: object
    ) -> int:
        assert apm == approved
        calls.append("profile")
        return 0

    monkeypatch.setattr(sys, "argv", ["apm-smoke", "--session"])
    monkeypatch.setattr(apm_adapter, "pinned_apm_executable", resolve)
    monkeypatch.setattr(apm_smoke.shutil, "which", which)
    monkeypatch.setattr(apm_smoke, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(apm_smoke, "smoke_profile", smoke)

    assert apm_smoke.main() == 0
    assert calls == ["resolve", "profile"]


@pytest.mark.parametrize(
    ("issue", "diagnostic"),
    [
        (apm_adapter.ApmAvailabilityIssue.MISSING_PACKAGE, "APM 0.33.0 is required.\n"),
        (
            apm_adapter.ApmAvailabilityIssue.VERSION_MISMATCH,
            "APM 0.33.0 is required.\n",
        ),
        (
            apm_adapter.ApmAvailabilityIssue.MISSING_EXECUTABLE,
            "Use the locked toolkit environment.\n",
        ),
    ],
)
def test_smoke_launcher_availability_errors_preserve_cli_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    issue: apm_adapter.ApmAvailabilityIssue,
    diagnostic: str,
) -> None:
    def unavailable() -> str:
        raise apm_adapter.ApmAvailabilityError(issue)

    monkeypatch.setattr(sys, "argv", ["apm-smoke", "--session"])
    monkeypatch.setattr(apm_adapter, "pinned_apm_executable", unavailable)
    monkeypatch.setattr(
        apm_smoke.shutil,
        "which",
        lambda _name: pytest.fail("tool lookup must follow approved APM discovery"),
    )
    monkeypatch.setattr(
        apm_smoke, "run", lambda *_args, **_kwargs: pytest.fail("must not run")
    )

    assert apm_smoke.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == diagnostic


def test_smoke_missing_toolkit_retains_locked_environment_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["apm-smoke", "--session"])
    monkeypatch.setattr(apm_adapter, "pinned_apm_executable", lambda: "approved")
    monkeypatch.setattr(apm_smoke.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        apm_smoke, "run", lambda *_args, **_kwargs: pytest.fail("must not run")
    )

    assert apm_smoke.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Use the locked toolkit environment.\n"


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


def _declared_roles() -> set[str]:
    return {
        role["id"]
        for path in (_ROOT / "packages").glob("*/.apm/skills/*/assets/agents.json")
        for role in json.loads(path.read_text(encoding="utf-8"))["roles"]
    }


_NATIVE_ROLE_PATHS = ((".github/agents/", ".agent.md"), (".claude/agents/", ".md"))


def _resource_documents(
    snapshot: CatalogSnapshot, bundles: tuple[str, ...]
) -> list[SourceDocument]:
    return [
        document
        for bundle in snapshot.bundles
        if bundle.name in bundles
        for document in bundle.files
        if not document.is_directory
        and any(
            f"/{kind}/" in document.relative_path for kind in ("references", "assets")
        )
    ]


def test_composed_all_stack_delivery_retains_resources_and_complete_role_roster() -> (
    None
):
    """Resource depth and every declared role must reach a budgeted selection."""
    snapshot = FileCatalogAdapter().load(_ROOT)
    delivered: dict[str, set[str]] = {prefix: set() for prefix, _ in _NATIVE_ROLE_PATHS}
    for profile, features in _SMOKE_SELECTIONS:
        plan = CatalogService().compose(
            snapshot, profile, features, ("copilot", "claude"), skills=()
        )
        files = {item.relative_path: item.content for item in plan.files}
        assert json.loads(files["apm.yml"])["compilation"] == {
            "exclude": [".apm/skills", ".agents/skills", ".claude/skills"]
        }
        for document in _resource_documents(snapshot, plan.bundles):
            assert files[f".apm/{document.relative_path}"] == document.content
        for prefix, suffix in _NATIVE_ROLE_PATHS:
            delivered[prefix].update(
                path.rsplit("/", 1)[-1].removesuffix(suffix)
                for path in files
                if path.startswith(prefix)
            )
    baseline = json.loads(
        (_ROOT / ".agents/agentic-setup/coverage.json").read_text(encoding="utf-8")
    )
    roles = _declared_roles()
    assert set(baseline["agents"].values()) <= roles
    assert all(names == roles for names in delivered.values())


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
