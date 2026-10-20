"""Expected-input error handling at the native projection CLI boundary."""

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
