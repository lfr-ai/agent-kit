"""Contracts for the bounded native session-context script adapter."""

import io
import json
from pathlib import Path

import pytest
import scripts.session_context as session_context_script


def test_main_emits_the_existing_session_start_context(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(tmp_path)})))

    assert session_context_script.main() == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out) == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"Active workspace: {tmp_path}\n"
                "Agent entry points: AGENTS.md, PROJECT.md, llms.txt.\n"
                "Missing agent context files: AGENTS.md, PROJECT.md, llms.txt."
            ),
        },
    }
    assert captured.err == ""


@pytest.mark.parametrize("raw", ["{", "[]", '{"cwd": false}', '{"cwd": []}'])
def test_main_rejects_malformed_and_wrong_type_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: str,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))

    assert session_context_script.main() == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "session context could not be checked:" in captured.err


def test_main_rejects_invalid_utf8_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(b"\xff"), encoding="utf-8")
    )

    assert session_context_script.main() == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "session context could not be checked:" in captured.err


def test_main_rejects_oversized_input_without_emitting_context(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(" " * (session_context_script._MAX_CONTEXT_CHARS + 1))
    )

    assert session_context_script.main() == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "session context input is too large\n"
