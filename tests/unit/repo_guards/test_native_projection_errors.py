"""Expected-input error handling at the native projection CLI boundary."""

from pathlib import Path
import sys

import pytest
from scripts import render_native

from agent_kit.core.errors import InputTypeError


def test_main_reports_input_type_error_as_a_nonzero_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Known decoded-input type failures remain CLI diagnostics, not tracebacks."""
    monkeypatch.setattr(sys, "argv", ["render-native"])

    def invalid_input(_root: object) -> list[str]:
        raise InputTypeError(location="native selection.profile", expected="a string")

    monkeypatch.setattr(render_native, "check", invalid_input)

    assert render_native.main() == 1
    assert (
        capsys.readouterr().err.strip() == "native selection.profile must be a string"
    )


def test_main_does_not_swallow_unexpected_type_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programmer TypeErrors still surface rather than becoming input diagnostics."""
    monkeypatch.setattr(sys, "argv", ["render-native"])
    failure = TypeError()

    def programmer_error(_root: object) -> list[str]:
        raise failure

    monkeypatch.setattr(render_native, "check", programmer_error)

    with pytest.raises(TypeError) as error:
        render_native.main()
    assert error.value is failure


@pytest.mark.parametrize(
    "content",
    [
        pytest.param('{"schema_version": 1}', id="no-profile"),
        pytest.param('{"schema_version": 1, "profile": "x", "extra": 1}', id="extra"),
        pytest.param('{"schema_version": 1, "profile": 1}', id="numeric-profile"),
        pytest.param("not json", id="malformed"),
    ],
)
def test_malformed_self_selection_is_a_stable_diagnostic(
    tmp_path: Path, content: str
) -> None:
    """The repository selection shares the composition selection schema."""
    selection = tmp_path / ".agents" / "agentic-setup" / "self.json"
    selection.parent.mkdir(parents=True)
    selection.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="repository native selection is invalid"):
        render_native.expected(tmp_path)
