"""Pinned APM CLI subprocess adapter contracts without the real executable."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import agent_kit.infrastructure.apm_adapter as apm_module
from agent_kit.infrastructure.apm_adapter import ApmCliAdapter, ApmCliError


def test_apm_commands_use_fixed_version_no_scripts_and_explicit_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def run(
        arguments: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, cwd, env.copy()))
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(
        apm_module.importlib.metadata, "version", lambda _name: "0.33.0"
    )
    monkeypatch.setattr(apm_module.shutil, "which", lambda _name: "apm")
    monkeypatch.setattr(apm_module.subprocess, "run", run)

    ApmCliAdapter(timeout_seconds=5).check(tmp_path)

    assert len(calls) == 2
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        apm_module.importlib.metadata, "version", lambda _name: "0.34.0"
    )
    monkeypatch.setattr(
        apm_module.shutil,
        "which",
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
        capture_output: bool,
        text: bool,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments, 9, stdout="credential-value", stderr="credential-value"
        )

    monkeypatch.setattr(
        apm_module.importlib.metadata, "version", lambda _name: "0.33.0"
    )
    monkeypatch.setattr(apm_module.shutil, "which", lambda _name: "apm")
    monkeypatch.setattr(apm_module.subprocess, "run", run)

    with pytest.raises(ApmCliError, match="exit code 9") as error:
        ApmCliAdapter().check(tmp_path)

    assert "credential-value" not in str(error.value)


@pytest.mark.parametrize("timeout", [0, -1.0])
def test_non_positive_timeout_is_rejected(timeout: float) -> None:
    """A zero or negative timeout would disable the process bound."""
    with pytest.raises(ValueError, match="positive"):
        ApmCliAdapter(timeout_seconds=timeout)


def test_missing_apm_distribution_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent pinned distribution fails before any executable lookup."""

    def missing(_name: str) -> str:
        raise apm_module.importlib.metadata.PackageNotFoundError(_name)

    monkeypatch.setattr(apm_module.importlib.metadata, "version", missing)

    with pytest.raises(ApmCliError, match="not installed"):
        ApmCliAdapter().check(Path.cwd())


def test_missing_apm_executable_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """A matching distribution without an executable on PATH fails clearly."""
    monkeypatch.setattr(apm_module.importlib.metadata, "version", lambda _: "0.33.0")
    monkeypatch.setattr(apm_module.shutil, "which", lambda _name: None)

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

    monkeypatch.setattr(apm_module.importlib.metadata, "version", lambda _: "0.33.0")
    monkeypatch.setattr(apm_module.shutil, "which", lambda _name: "apm")
    monkeypatch.setattr(apm_module.subprocess, "run", run)

    with pytest.raises(ApmCliError, match=f"policy status {message}"):
        ApmCliAdapter(timeout_seconds=1).check(tmp_path)
