"""Argparse presentation result handling with injected actions."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO, StringIO, TextIOWrapper
import json
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import pytest

from agent_kit.core.errors import InputTypeError
from agent_kit.core.models import CheckReport, Finding, ProfileSummary, SessionContext
from agent_kit.infrastructure.session_context import session_context
from agent_kit.presentation.cli import CliActions, main

if TYPE_CHECKING:
    from collections.abc import Callable


def _ok(_root: Path) -> CheckReport:
    return CheckReport(findings=(), profiles=(), version="0.1.0")


def _cli_actions(
    check: Callable[[Path], CheckReport] = _ok,
    apm_check: Callable[[Path], CheckReport | None] = lambda _root: None,
    context: Callable[[object], SessionContext] = lambda _payload: SessionContext(
        workspace="synthetic", missing=()
    ),
) -> CliActions:
    return CliActions(
        apm_check=apm_check,
        check=check,
        compose=lambda _root, _profile, _features, _runtimes, output, _skills: output,
        default_root=Path.cwd,
        context=context,
        provenance=_ok,
    )


def test_check_json_includes_profile_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = main(_cli_actions(), ["check", "--json"])
    captured = capsys.readouterr()

    assert result == 0
    assert '"valid": true' in captured.out
    assert captured.err == ""


def test_check_failure_is_clear_and_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = CheckReport(
        findings=(
            Finding(
                code="catalog.invalid",
                message="catalog shape is invalid",
                path="catalog.json",
            ),
        ),
        profiles=(),
        version=None,
    )
    result = main(_cli_actions(check=lambda _root: report), ["check", "--root", "."])
    captured = capsys.readouterr()

    assert result == 1
    assert "catalog.json: catalog shape is invalid" in captured.err
    assert captured.out == ""


def test_compose_refuses_before_action_when_validation_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = CheckReport(
        findings=(Finding(code="invalid", message="not ready", path="catalog.json"),),
        profiles=(),
        version=None,
    )
    called = False

    def compose(
        _root: Path,
        _profile: str,
        _features: tuple[str, ...],
        _runtimes: tuple[str, ...],
        output: Path,
        _skills: tuple[str, ...],
    ) -> Path:
        nonlocal called
        called = True
        return output

    actions = _cli_actions(check=lambda _root: report)
    actions = CliActions(
        apm_check=actions.apm_check,
        check=actions.check,
        compose=compose,
        default_root=actions.default_root,
        context=actions.context,
        provenance=actions.provenance,
    )

    result = main(actions, ["compose", "backend", "--output", "not-created"])

    assert result == 1
    assert not called
    assert "not ready" in capsys.readouterr().err


def test_context_emits_only_advisory_session_information(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", _input_stream('{"tool_name":"Read"}'))

    result = main(_cli_actions(), ["context"])

    assert result == 0
    output = capsys.readouterr().out
    assert '"hookEventName": "SessionStart"' in output
    assert "synthetic" in output
    assert "permissionDecision" not in output


def test_context_reports_missing_entry_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", _input_stream('{"toolName":"powershell"}'))
    actions = _cli_actions(
        context=lambda _payload: SessionContext(
            workspace="synthetic", missing=("PROJECT.md",)
        )
    )

    result = main(actions, ["context"])
    output = capsys.readouterr().out

    assert result == 0
    assert "Missing agent context files: PROJECT.md." in output
    assert '"hookEventName": "SessionStart"' in output


def test_context_json_is_safe_for_cp1252_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "\u65e5\u672c\U0001f680"
    workspace.mkdir()
    monkeypatch.setattr("sys.stdin", _input_stream(json.dumps({"cwd": str(workspace)})))
    buffer = BytesIO()
    with TextIOWrapper(buffer, encoding="cp1252", errors="strict") as stream:
        monkeypatch.setattr("sys.stdout", stream)

        assert main(_cli_actions(context=session_context), ["context"]) == 0

        stream.flush()
        raw = buffer.getvalue()
        response = json.loads(raw.decode("ascii"))
        context = response["hookSpecificOutput"]["additionalContext"]
        assert str(workspace) in context
        assert response["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_check_json_is_safe_for_cp1252_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    path = "assets/\u65e5\u672c\U0001f680.md"
    report = CheckReport(
        findings=(Finding(code="links.missing", message="Missing guide.", path=path),),
        profiles=(),
        version="0.1.0",
    )
    buffer = BytesIO()
    with TextIOWrapper(buffer, encoding="cp1252", errors="strict") as stream:
        monkeypatch.setattr("sys.stdout", stream)

        assert main(_cli_actions(check=lambda _root: report), ["check", "--json"]) == 1

        stream.flush()
        response = json.loads(buffer.getvalue().decode("ascii"))
        assert response["valid"] is False
        assert response["findings"][0]["path"] == path


def test_context_malformed_json_reports_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", _input_stream("{"))

    result = main(_cli_actions(), ["context"])

    assert result == 1
    assert "could not be checked" in capsys.readouterr().err


@pytest.mark.parametrize("payload", ["[]", '{"cwd": false}'])
def test_context_wrong_types_have_actionable_nonzero_errors(
    payload: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", _input_stream(payload))

    assert main(_cli_actions(context=session_context), ["context"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "session context could not be checked:" in captured.err


@pytest.mark.parametrize("command", ["check", "context"])
def test_unexpected_programming_type_errors_are_not_hidden(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = TypeError("unexpected programming failure")

    def fail(_payload: object) -> SessionContext:
        raise failure

    def fail_check(_root: Path) -> CheckReport:
        raise failure

    monkeypatch.setattr("sys.stdin", _input_stream("{}"))
    with pytest.raises(TypeError, match="unexpected programming failure"):
        main(_cli_actions(check=fail_check, context=fail), [command])


def _input_stream(content: str) -> TextIO:
    """Create a small in-memory text stream for stdin injection."""
    return StringIO(content)


_INVALID = CheckReport(
    findings=(Finding(code="x.bad", message="bad input", path="catalog.json"),),
    profiles=(),
    version=None,
)


def test_check_text_reports_version_and_uses_default_root(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --root, check validates the injected default root."""
    seen: list[Path] = []

    def check(root: Path) -> CheckReport:
        seen.append(root)
        return _ok(root)

    actions = replace(_cli_actions(check=check), default_root=lambda: Path("found"))

    assert main(actions, ["check"]) == 0
    assert seen == [Path("found")]
    assert capsys.readouterr().out.strip() == "source catalog valid: 0.1.0"


def test_check_json_serializes_profile_summaries(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Profile budgets appear in the stable JSON report."""
    summary = ProfileSummary(
        body_lines=10,
        description_chars=20,
        limits=(("skill_body_lines", 300),),
        policy_lines=5,
        profile="backend",
        skill_count=2,
    )
    report = CheckReport(findings=(), profiles=(summary,), version="0.1.0")

    assert main(_cli_actions(check=lambda _root: report), ["check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profiles"]["backend"] == {
        "skill_count": 2,
        "body_lines": 10,
        "description_chars": 20,
        "policy_lines": 5,
        "limits": {"skill_body_lines": 300},
    }


@pytest.mark.parametrize("skills", [[], ["kit-a", "kit-b"]])
def test_compose_forwards_arguments_and_reports_session_mode(
    capsys: pytest.CaptureFixture[str], skills: list[str]
) -> None:
    """Compose passes repeatable options as tuples and explains session delivery."""
    received: list[tuple[object, ...]] = []

    def compose(*arguments: object) -> Path:
        received.append(arguments)
        return Path("out")

    actions = replace(_cli_actions(), compose=compose)
    argv = ["compose", "backend", "--root", "src", "--output", "out"]
    argv += ["--feature", "iac", "--runtime", "claude"]
    for skill in skills:
        argv += ["--skill", skill]

    assert main(actions, argv) == 0
    assert received == [
        (Path("src"), "backend", ("iac",), ("claude",), Path("out"), tuple(skills))
    ]
    output = capsys.readouterr().out
    assert "composed backend profile" in output
    assert ("native roles omitted" in output) is bool(skills)


@pytest.mark.parametrize(
    ("command", "attribute", "success"),
    [
        ("provenance", "provenance", "composed output provenance verified"),
        ("apm-check", "apm_check", "APM policy and audit checks passed"),
    ],
)
def test_root_commands_report_success_and_findings(
    capsys: pytest.CaptureFixture[str],
    command: str,
    attribute: str,
    success: str,
) -> None:
    """Valid results print a confirmation; findings go to stderr with exit 1."""
    passing = replace(_cli_actions(), **{attribute: _ok})
    failing = replace(_cli_actions(), **{attribute: lambda _root: _INVALID})

    assert main(passing, [command, "--root", "out"]) == 0
    assert success in capsys.readouterr().out
    assert main(failing, [command, "--root", "out"]) == 1
    assert "catalog.json: bad input [x.bad]" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [
        OSError("disk"),
        RuntimeError("apm"),
        ValueError("v"),
        InputTypeError(location="catalog input", expected="an object"),
    ],
)
def test_operation_errors_become_exit_one_with_message(
    capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    """Expected operational errors are reported, not raised as tracebacks."""

    def fail(_root: Path) -> CheckReport:
        raise error

    assert main(_cli_actions(check=fail), ["check"]) == 1
    assert str(error) in capsys.readouterr().err


def test_oversized_context_input_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hook input above the bound is rejected before JSON parsing."""
    monkeypatch.setattr("sys.stdin", _input_stream(" " * 1_000_001))

    assert main(_cli_actions(), ["context"]) == 1
    assert "too large" in capsys.readouterr().err


def test_missing_command_is_a_usage_error() -> None:
    """Argparse exits with status 2 when no subcommand is supplied."""
    with pytest.raises(SystemExit, match="2"):
        main(_cli_actions(), [])
