"""Locked dependency and license audit contracts."""

from collections.abc import Callable
from pathlib import Path
import runpy
import subprocess

import pytest
import scripts.audit_dependencies as audit
import scripts.verify as verify_module

_ROOT = Path(__file__).resolve().parents[3]
_GUARD = runpy.run_path(
    str(_ROOT / "packages/shared/.apm/skills/kit-agent-runtime/assets/license_guard.py")
)
_WHEELED_LOCK = """
[[package]]
name = "wheeled"
version = "1.0"
source = { registry = "https://pypi.org/simple" }
wheels = [{ url = "https://example.org/wheeled-1.0-py3-none-any.whl" }]

[[package]]
name = "project"
version = "0.1.0"
source = { editable = "." }
"""


def _write_lock(root: Path, text: str) -> None:
    (root / "uv.lock").write_text(text, encoding="utf-8")


def _recorder(
    calls: list[list[str]], *, export_code: int = 0, audit_code: int = 0
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        code = export_code if "export" in command else audit_code
        return subprocess.CompletedProcess(command, code)

    return run


def test_source_only_registry_packages_are_rejected_before_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(
        tmp_path,
        _WHEELED_LOCK
        + '\n[[package]]\nname = "builds"\nversion = "2.0"\n'
        + 'source = { registry = "https://pypi.org/simple" }\n'
        + 'sdist = { url = "https://example.org/builds-2.0.tar.gz" }\n',
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.subprocess, "run", _recorder(calls))

    assert audit.run(tmp_path) == 1
    assert calls == []


def test_lock_is_exported_with_hashes_and_audited_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(audit.subprocess, "run", _recorder(calls, audit_code=1))

    assert audit.run(tmp_path) == 1
    export, scan = calls
    assert export[:2] == ["uv", "export"]
    assert {"--locked", "--all-groups", "--no-emit-project"} <= set(export)
    assert "--no-hashes" not in export
    assert scan[1:3] == ["-m", "pip_audit"]
    assert {"--require-hashes", "--disable-pip", "--strict", "--cache-dir"} <= set(scan)
    assert "--vulnerability-service" not in scan


def test_export_failure_stops_before_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(audit.subprocess, "run", _recorder(calls, export_code=2))

    assert audit.run(tmp_path) == 2
    assert len(calls) == 1


@pytest.mark.parametrize("lock", [None, "not = [valid"])
def test_missing_uv_or_unreadable_lock_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lock: str | None
) -> None:
    _write_lock(tmp_path, lock or _WHEELED_LOCK)
    monkeypatch.setattr(audit.shutil, "which", lambda _name: None)

    assert audit.run(tmp_path) == 1


def test_bun_lock_is_audited_after_the_python_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    (tmp_path / "bun.lock").write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 3 if command[0] == "bun" else 0)

    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(audit.subprocess, "run", run)

    assert audit.run(tmp_path) == 3
    assert calls[-1] == ["bun", "audit"]


def test_bun_lock_without_bun_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    (tmp_path / "bun.lock").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        audit.shutil, "which", lambda name: None if name == "bun" else name
    )
    monkeypatch.setattr(audit.subprocess, "run", _recorder([]))

    assert audit.run(tmp_path) == 1


def test_repository_license_policy_is_closed_and_time_boxed() -> None:
    allowlist = _GUARD["load_allowlist"](_ROOT / "license-allowlist.json")

    assert allowlist.exceptions
    assert all(item.expires is not None for item in allowlist.exceptions.values())
    assert {"agpl-3.0-only", "gpl-3.0-only", "sspl-1.0"} <= allowlist.denied


def test_dependency_and_license_audits_are_verification_gates() -> None:
    assert "dependencies" not in verify_module._CHECKS
    assert verify_module._NETWORK_CHECKS["dependencies"][-1] == (
        "scripts/audit_dependencies.py"
    )
    assert verify_module._CHECKS["licenses"][-2:] == (
        "--allowlist",
        "license-allowlist.json",
    )
