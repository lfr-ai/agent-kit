"""Pinned APM CLI subprocess adapter contracts without the real executable."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import subprocess
import sysconfig

import pytest

import agent_kit.infrastructure.apm_adapter as apm_module
from agent_kit.infrastructure.apm_adapter import (
    ApmAvailabilityError,
    ApmCliAdapter,
    ApmCliError,
    InvalidApmTimeoutError,
)


def _installed_apm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    launcher: str | None = None,
) -> Path:
    """Describe a recorded launcher in a synthetic, relocated environment."""
    environment = tmp_path / "active"
    scripts = environment / "scripts"
    scripts.mkdir(parents=True)
    executable = scripts / (launcher or ("apm.exe" if os.name == "nt" else "apm"))
    executable.write_bytes(b"synthetic launcher")
    executable.chmod(0o700)
    metadata = environment / "site-packages/apm_cli-0.33.0.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text(
        "Name: apm-cli\nVersion: 0.33.0\n", encoding="utf-8"
    )
    (metadata / "RECORD").write_text(
        f"../scripts/{executable.name},,\n", encoding="utf-8"
    )
    distribution = importlib.metadata.PathDistribution(metadata)
    monkeypatch.setattr(
        apm_module.importlib.metadata, "distribution", lambda _name: distribution
    )
    monkeypatch.setattr(sysconfig, "get_path", lambda _name: str(scripts))
    return executable


@pytest.mark.parametrize("active_available", [False, True])
def test_foreign_path_launcher_is_never_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, active_available: bool
) -> None:
    """Matching metadata cannot authorize a launcher from another installation."""
    approved = _installed_apm(tmp_path, monkeypatch)
    foreign = tmp_path / "foreign" / approved.name
    foreign.parent.mkdir()
    foreign.write_bytes(b"foreign launcher")
    foreign.chmod(0o700)
    monkeypatch.setenv("PATH", str(foreign.parent))
    if not active_available:
        approved.unlink()
    calls: list[list[str]] = []

    def run(
        arguments: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments)
        assert Path(arguments[0]) == approved
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(apm_module.subprocess, "run", run)
    if active_available:
        ApmCliAdapter().check(tmp_path)
        assert len(calls) == 2
    else:
        with pytest.raises(ApmAvailabilityError, match="unavailable"):
            ApmCliAdapter().check(tmp_path)
        assert not calls


@pytest.mark.parametrize(
    ("platform", "launcher"), [("linux", "apm"), ("win32", "apm.exe")]
)
def test_recorded_environment_launcher_runs_without_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    launcher: str,
) -> None:
    approved = _installed_apm(tmp_path, monkeypatch, launcher=launcher)
    monkeypatch.setenv("PATH", "")
    calls: list[list[str]] = []

    def run(
        arguments: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments)
        assert Path(arguments[0]) == approved
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(apm_module.subprocess, "run", run)
    with monkeypatch.context() as platform_patch:
        platform_patch.setattr(apm_module.sys, "platform", platform)
        ApmCliAdapter().check(tmp_path)
    assert len(calls) == 2


@pytest.mark.parametrize("record", [None, "", "../../foreign/apm.exe,,\n"])
def test_version_metadata_alone_cannot_authorize_environment_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: str | None
) -> None:
    approved = _installed_apm(tmp_path, monkeypatch)
    record_path = (
        approved.parent.parent / "site-packages/apm_cli-0.33.0.dist-info/RECORD"
    )
    if record is None:
        record_path.unlink()
    else:
        record_path.write_text(record, encoding="utf-8")
    monkeypatch.setattr(
        apm_module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("must not run"),
    )

    with pytest.raises(ApmAvailabilityError, match="unavailable"):
        ApmCliAdapter().check(tmp_path)


@pytest.mark.parametrize(
    ("timeout_seconds", "expected_timeout"), [(None, 300.0), (5.0, 5.0)]
)
def test_apm_commands_use_fixed_version_no_scripts_and_explicit_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timeout_seconds: float | None,
    expected_timeout: float,
) -> None:
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def run(
        arguments: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: int,
        stderr: int,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        assert stdout == subprocess.DEVNULL
        assert stderr == subprocess.DEVNULL
        assert timeout == expected_timeout
        calls.append((arguments, cwd, env.copy()))
        return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

    approved = _installed_apm(tmp_path, monkeypatch)
    monkeypatch.setattr(apm_module.subprocess, "run", run)

    adapter = (
        ApmCliAdapter()
        if timeout_seconds is None
        else ApmCliAdapter(timeout_seconds=timeout_seconds)
    )
    adapter.check(tmp_path)

    assert len(calls) == 2
    assert all(Path(call[0][0]) == approved for call in calls)
    assert calls[0][0][1:] == [
        "policy",
        "status",
        "--policy-source",
        "./apm-policy.yml",
        "--check",
        "--json",
    ]
    assert calls[1][0][1:] == [
        "audit",
        "--ci",
        "--policy",
        "./apm-policy.yml",
        "--no-fail-fast",
    ]
    assert all(call[1] == tmp_path for call in calls)
    assert all(call[2]["APM_NO_SCRIPTS"] == "1" for call in calls)
    assert all(call[2]["APM_NON_INTERACTIVE"] == "1" for call in calls)


def test_apm_version_mismatch_fails_before_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved = _installed_apm(tmp_path, monkeypatch)
    metadata = (
        approved.parent.parent / "site-packages/apm_cli-0.33.0.dist-info/METADATA"
    )
    metadata.write_text("Name: apm-cli\nVersion: 0.34.0\n", encoding="utf-8")
    monkeypatch.setattr(
        sysconfig,
        "get_path",
        lambda _name: pytest.fail("executable lookup must not run"),
    )

    with pytest.raises(ApmCliError, match="does not match"):
        ApmCliAdapter().check(Path.cwd())


def test_apm_nonzero_error_does_not_echo_process_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(
        arguments: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: int,
        stderr: int,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            arguments, 9, stdout=b"credential-value", stderr=b"credential-value"
        )

    _installed_apm(tmp_path, monkeypatch)
    monkeypatch.setattr(apm_module.subprocess, "run", run)

    with pytest.raises(ApmCliError, match="exit code 9") as error:
        ApmCliAdapter().check(tmp_path)

    assert "credential-value" not in str(error.value)


@pytest.mark.parametrize(
    "timeout", [float("nan"), float("inf"), -float("inf"), 0, -1.0]
)
def test_non_finite_or_non_positive_timeout_is_rejected(timeout: float) -> None:
    """Only a finite positive timeout bounds process execution."""
    with pytest.raises(InvalidApmTimeoutError, match="positive"):
        ApmCliAdapter(timeout_seconds=timeout)


def test_missing_apm_distribution_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent pinned distribution fails before any executable lookup."""

    def missing(_name: str) -> importlib.metadata.Distribution:
        raise apm_module.importlib.metadata.PackageNotFoundError(_name)

    monkeypatch.setattr(apm_module.importlib.metadata, "distribution", missing)

    with pytest.raises(ApmCliError, match="not installed"):
        ApmCliAdapter().check(Path.cwd())


def test_missing_apm_executable_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A matching distribution without its recorded executable fails clearly."""
    _installed_apm(tmp_path, monkeypatch).unlink()

    with pytest.raises(ApmCliError, match="unavailable"):
        ApmCliAdapter().check(Path.cwd())


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (subprocess.TimeoutExpired(["apm"], 1), "timed out"),
        (OSError("exec format error"), "could not start"),
    ],
)
def test_process_failures_become_adapter_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    message: str,
) -> None:
    """Timeouts and spawn failures map to one error type with a safe message."""

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise failure

    _installed_apm(tmp_path, monkeypatch)
    monkeypatch.setattr(apm_module.subprocess, "run", run)

    with pytest.raises(ApmCliError, match=f"policy status {message}"):
        ApmCliAdapter(timeout_seconds=1).check(tmp_path)
