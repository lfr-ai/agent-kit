"""Locked dependency and license audit contracts."""

from collections.abc import Callable
import json
from pathlib import Path
import runpy
import subprocess
import tomllib

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


def _report(
    *, vulnerabilities: int = 0, adverse_statuses: int = 0
) -> dict[str, object]:
    return {
        "schema": {"version": "preview"},
        "summary": {
            "audited_packages": 2,
            "vulnerabilities": vulnerabilities,
            "adverse_statuses": adverse_statuses,
        },
        "vulnerabilities": [
            {"dependency": {"name": "wheeled", "version": "1.0"}, "id": "TEST-1"}
            for _ in range(vulnerabilities)
        ],
        "adverse_statuses": [
            {"name": "wheeled", "status": "deprecated", "reason": None}
            for _ in range(adverse_statuses)
        ],
    }


def _recorder(
    calls: list[list[str]], *, audit_code: int = 0, report: str | None = None
) -> Callable[..., subprocess.CompletedProcess[str]]:
    clean = json.dumps(_report())

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command, audit_code, stdout=clean if report is None else report
        )

    return run


def test_source_only_registry_packages_are_rejected_before_audit(
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


@pytest.mark.parametrize(
    "lock",
    [
        "",
        "package = []",
        'package = "not a package list"',
        'package = ["not a package"]',
        '[[package]]\nname = "example"\n',
        '[[package]]\nname = "example"\nversion = "1.0"\nsource = "registry"\n',
        '[[package]]\nname = "example"\nversion = "1.0"\nsource = {}\n',
        '[[package]]\nname = "example"\nversion = "1.0"\nsource = { registry = 1 }\n',
        (
            '[[package]]\nname = "example"\nversion = "1.0"\n'
            'source = { registry = "https://pypi.org/simple" }\nwheels = "not wheels"\n'
        ),
        (
            '[[package]]\nname = "example"\nversion = "1.0"\n'
            'source = { registry = "https://pypi.org/simple" }\nwheels = [{}]\n'
        ),
    ],
)
def test_malformed_lock_metadata_fails_before_audit_tools_are_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    lock: str,
) -> None:
    _write_lock(tmp_path, lock)
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.subprocess, "run", _recorder(calls))
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)

    assert audit.run(tmp_path) == 1
    assert calls == []
    assert "invalid package metadata" in capsys.readouterr().err


def test_registry_package_without_wheel_records_is_not_accepted() -> None:
    lock = tomllib.loads(
        '[[package]]\nname = "example"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\nwheels = []\n'
    )
    assert audit.source_only_packages(lock) == ["example==1.0"]


def test_invalid_lock_encoding_fails_with_a_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "uv.lock").write_bytes(b"\xff")

    assert audit.run(tmp_path) == 1
    assert "cannot read uv.lock" in capsys.readouterr().err


def test_lock_is_audited_locked_with_the_osv_and_status_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(audit.subprocess, "run", _recorder(calls))

    assert audit.run(tmp_path) == 0
    assert calls == [
        [
            "uv",
            "audit",
            "--locked",
            "--preview-features",
            "audit-command,json-output",
            "--output-format",
            "json",
        ]
    ]


@pytest.mark.parametrize(
    ("audit_code", "counts"),
    [(1, (1, 0)), (0, (0, 1)), (0, (1, 0)), (1, (0, 0))],
    ids=["vulnerable", "adverse-status-only", "vulnerable-exit-zero", "locked-failure"],
)
def test_any_audit_finding_or_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    audit_code: int,
    counts: tuple[int, int],
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    report = json.dumps(_report(vulnerabilities=counts[0], adverse_statuses=counts[1]))
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(
        audit.subprocess, "run", _recorder([], audit_code=audit_code, report=report)
    )

    assert audit.run(tmp_path) == 1
    assert report in capsys.readouterr().err


@pytest.mark.parametrize("report", ["", "not json", "[]", '{"summary": {}}'])
def test_unreadable_audit_report_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, report: str
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    monkeypatch.setattr(audit.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(audit.subprocess, "run", _recorder([], report=report))

    assert audit.run(tmp_path) == 1


@pytest.mark.parametrize(
    "field", ["audited_packages", "vulnerabilities", "adverse_statuses"]
)
@pytest.mark.parametrize("value", [True, False, -1, 0.5, "0", None])
def test_invalid_report_counts_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    report = _report()
    report["summary"] = {
        "audited_packages": 2,
        "vulnerabilities": 0,
        "adverse_statuses": 0,
        field: value,
    }
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        audit.subprocess, "run", _recorder([], report=json.dumps(report))
    )

    assert audit.run(tmp_path) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", None),
        ("schema", {"version": "unknown"}),
        ("summary", []),
        ("vulnerabilities", None),
        ("vulnerabilities", [{}]),
        ("adverse_statuses", {}),
        ("adverse_statuses", "quarantined"),
        ("adverse_statuses", [None]),
        ("errors", ["network failure"]),
        ("error", "status lookup failed"),
    ],
)
def test_malformed_or_contradictory_report_fails_before_bun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    (tmp_path / "bun.lock").write_text("{}", encoding="utf-8")
    report = _report()
    report[field] = value
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        audit.subprocess, "run", _recorder(calls, report=json.dumps(report))
    )

    assert audit.run(tmp_path) == 1
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field", ["schema", "summary", "vulnerabilities", "adverse_statuses"]
)
def test_incomplete_report_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    report = _report()
    del report[field]
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        audit.subprocess, "run", _recorder([], report=json.dumps(report))
    )

    assert audit.run(tmp_path) == 1


@pytest.mark.parametrize(
    "status", ["archived", "deprecated", "quarantined", "unknown", None]
)
def test_status_only_report_blocks_even_when_uv_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str | None
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    report = _report(adverse_statuses=1)
    report["adverse_statuses"] = [{"name": "wheeled", "status": status, "reason": None}]
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        audit.subprocess, "run", _recorder([], report=json.dumps(report))
    )

    assert audit.run(tmp_path) == 1


@pytest.mark.parametrize("audit_code", [1, 2, 7])
def test_uv_network_or_command_error_preserves_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    audit_code: int,
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        audit.subprocess, "run", _recorder([], audit_code=audit_code, report="")
    )

    assert audit.run(tmp_path) == audit_code
    assert f"uv audit exit {audit_code}" in capsys.readouterr().err


@pytest.mark.parametrize("tool", ["uv", "bun"])
@pytest.mark.parametrize(
    "error", [FileNotFoundError(), PermissionError(), UnicodeError()]
)
def test_tool_launch_or_output_failure_has_a_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool: str,
    error: OSError | UnicodeError,
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    (tmp_path / "bun.lock").write_text("{}", encoding="utf-8")
    clean = _recorder([])

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[0] == tool:
            raise error
        return clean(command, **kwargs)

    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(audit.subprocess, "run", run)

    assert audit.run(tmp_path) == 1
    assert "cannot run audit tool" in capsys.readouterr().err


def test_ignore_until_fixed_is_forwarded_only_when_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    calls: list[list[str]] = []
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(audit.subprocess, "run", _recorder(calls))
    monkeypatch.setattr(audit, "_ROOT", tmp_path)
    monkeypatch.setattr(
        audit.sys,
        "argv",
        ["audit_dependencies.py", "--ignore-until-fixed", "TEST-1"],
    )

    assert audit.main() == 0
    assert calls[0][-2:] == ["--ignore-until-fixed", "TEST-1"]


def test_explicit_exception_does_not_hide_reported_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(tmp_path, _WHEELED_LOCK)
    monkeypatch.setattr(audit.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        _recorder([], report=json.dumps(_report(vulnerabilities=1))),
    )

    assert audit.run(tmp_path, ignore_until_fixed=("TEST-1",)) == 1


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
    clean = _recorder([])

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "bun":
            return subprocess.CompletedProcess(command, 3)
        return clean(command, **kwargs)

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
