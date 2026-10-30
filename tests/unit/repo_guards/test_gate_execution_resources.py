"""Portable gate evidence retains every command outcome without provisioning."""

from collections.abc import Iterator, Sequence
import json
from pathlib import Path
import re
import runpy
import subprocess
from types import SimpleNamespace

import pytest
import yaml

_ASSET = (
    Path(__file__).resolve().parents[3]
    / "packages/shared/.apm/skills/kit-verify-change/assets/run_gate.py.template"
)


@pytest.fixture
def gate() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(_ASSET)))


def _stub_run(
    gate: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    outcomes: Iterator[tuple[str, int]],
) -> None:
    def run(command: Sequence[str], *, timeout: float) -> tuple[str, int]:
        assert command in (("fix",), ("check",))
        assert timeout == 1.0
        return next(outcomes)

    monkeypatch.setitem(gate.run_gate.__globals__, "_run", run)


@pytest.mark.parametrize("status", ["failed", "unavailable", "timeout"])
def test_failed_fixer_is_retained_when_check_passes(
    gate: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: str,
) -> None:
    outcomes = iter([(status, 1), ("passed", 0)])
    _stub_run(gate, monkeypatch, outcomes)
    monkeypatch.setitem(gate.write_report.__globals__, "_git_revision", lambda: "test")
    step = gate.Step(name="lint", check=("check",), fix=("fix",))
    results = gate.run_gate([step], fix=True, keep_going=False, timeout=1.0)
    report = tmp_path / "gate.json"
    gate.write_report(report, results, mode="fix")
    document = json.loads(report.read_text(encoding="utf-8"))

    assert [(result.phase, result.status) for result in results] == [
        ("fix", status),
        ("check", "passed"),
    ]
    assert document["passed"] is False
    assert len(document["steps"]) == 2


@pytest.mark.parametrize("keep_going", [False, True])
def test_failed_attempt_controls_later_steps(
    gate: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, keep_going: bool
) -> None:
    outcomes = iter([("failed", 1), ("passed", 0), ("passed", 0)])
    _stub_run(gate, monkeypatch, outcomes)
    steps = [
        gate.Step(name="first", check=("check",), fix=("fix",)),
        gate.Step(name="second", check=("check",)),
    ]

    results = gate.run_gate(steps, fix=True, keep_going=keep_going, timeout=1.0)

    assert [result.status for result in results] == [
        "failed",
        "passed",
        "passed" if keep_going else "skipped",
    ]


@pytest.mark.parametrize("keep_going", [False, True])
def test_failed_check_controls_later_steps(
    gate: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, keep_going: bool
) -> None:
    outcomes = iter([("failed", 1), ("passed", 0)])
    _stub_run(gate, monkeypatch, outcomes)
    steps = [gate.Step(name=name, check=("check",)) for name in ("first", "second")]

    results = gate.run_gate(steps, fix=False, keep_going=keep_going, timeout=1.0)

    assert [result.status for result in results] == [
        "failed",
        "passed" if keep_going else "skipped",
    ]


@pytest.mark.parametrize(
    "error", [FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired("x", 1)]
)
def test_launch_and_timeout_failures_are_explicit(
    gate: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(gate.shutil, "which", lambda command: command)

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(gate.subprocess, "run", fail)

    expected = (
        "timeout" if isinstance(error, subprocess.TimeoutExpired) else "unavailable"
    )
    assert gate._run(("check",), timeout=1.0) == (expected, None)


@pytest.mark.parametrize("timeout", ["nan", "inf", "0", "-1"])
def test_invalid_timeout_is_a_usage_error(
    gate: SimpleNamespace, capsys: pytest.CaptureFixture[str], timeout: str
) -> None:
    assert gate.main(["--only", "lint", "--timeout", timeout]) == 2
    assert "timeout" in capsys.readouterr().err


def test_commands_never_use_ephemeral_package_runners(gate: SimpleNamespace) -> None:
    for step in gate.STEPS:
        for command in (step.check, step.fix):
            if command is None:
                continue
            assert command[0] not in {"npx", "bunx", "pipx"}
            assert not (command[0] == "uv" and command[1] in {"tool", "x"})
            if command[:2] == ("uv", "run"):
                assert "--locked" in command
                assert "--no-sync" in command


def test_exported_type_gates_use_the_same_checker(gate: SimpleNamespace) -> None:
    step = next(step for step in gate.STEPS if step.name == "types")
    assert step.check == ("uv", "run", "--locked", "--no-sync", "ty", "check")
    config = yaml.safe_load(
        (_ASSET.parent / "pre-commit-config.yaml.template").read_text(encoding="utf-8")
    )
    hook = next(
        hook
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "type-check"
    )
    assert hook["entry"].split() == list(step.check)
    assert hook["pass_filenames"] is False
    for path in ("src/main.py", "src/main.pyi", "ty.toml", "pyproject.toml", "uv.lock"):
        assert re.search(hook["files"], path)
    assert not re.search(hook["files"], "README.md")
