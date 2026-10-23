"""Console entry point wiring through the composition root."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import agent_kit.composition.root as composition_module
import agent_kit.main as main_module

if TYPE_CHECKING:
    from pathlib import Path


def test_apm_check_rejects_bad_provenance_before_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    composed = tmp_path / "not-composed"
    composed.mkdir()
    monkeypatch.setattr(
        "sys.argv",
        ["agent-kit", "apm-check", "--root", str(composed)],
    )
    monkeypatch.setattr(
        composition_module.ApmCliAdapter,
        "check",
        lambda _self, _root: pytest.fail("APM must not run before provenance passes"),
    )

    result = main_module.main()

    assert result == 1
    assert "provenance.json" in capsys.readouterr().err


def test_console_help_is_available_without_source_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["agent-kit", "--help"])

    with pytest.raises(SystemExit, match="0"):
        main_module.main()

    assert "usage: agent-kit" in capsys.readouterr().out
