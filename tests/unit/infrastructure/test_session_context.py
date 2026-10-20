"""Read-only advisory session context checks."""

from pathlib import Path

import pytest

from agent_kit.core.errors import InputTypeError
from agent_kit.infrastructure.session_context import session_context


def test_complete_context_reports_no_missing_entries(tmp_path: Path) -> None:
    """Healthy context reports the workspace without executing commands."""
    for name in ("AGENTS.md", "PROJECT.md", "llms.txt"):
        (tmp_path / name).write_text("entry", encoding="utf-8")

    context = session_context({"cwd": str(tmp_path)})

    assert context.workspace == str(tmp_path)
    assert context.missing == ()


def test_partial_context_preserves_the_missing_entry_order(tmp_path: Path) -> None:
    """Missing facts and index are reported as advisory information."""
    (tmp_path / "AGENTS.md").write_text("entry", encoding="utf-8")

    assert session_context({"cwd": str(tmp_path)}).missing == ("PROJECT.md", "llms.txt")


@pytest.mark.parametrize("payload", [[], {"cwd": False}])
def test_invalid_context_payloads_report_errors(payload: object) -> None:
    """Invalid input cannot become a fabricated healthy context."""
    with pytest.raises(InputTypeError, match="session context"):
        session_context(payload)


def test_relative_context_directory_is_an_invalid_value() -> None:
    with pytest.raises(ValueError, match="absolute directory"):
        session_context({"cwd": "relative"})


def test_context_defaults_to_actual_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hosts without cwd use the actual process workspace."""
    monkeypatch.chdir(tmp_path)

    assert session_context({}).workspace == str(tmp_path)


def test_missing_workspace_directory_is_reported(tmp_path: Path) -> None:
    """An absolute cwd that no longer exists is not a healthy workspace."""
    with pytest.raises(ValueError, match="unavailable"):
        session_context({"cwd": str(tmp_path / "gone")})
