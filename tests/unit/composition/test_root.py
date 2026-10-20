"""Composition root wiring: source discovery and APM gating behind provenance."""

from pathlib import Path

import pytest

import agent_kit.composition.root as root_module
from agent_kit.composition.root import build_actions


def test_default_root_is_the_nearest_catalog_ancestor(
    source_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Commands run from a nested directory find the enclosing source root."""
    nested = source_root / "packages" / "backend"
    monkeypatch.chdir(nested)

    assert build_actions().default_root() == source_root.resolve()


def test_default_root_falls_back_to_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without any catalog, the working directory is used for explicit errors."""
    monkeypatch.chdir(tmp_path)

    assert build_actions().default_root() == tmp_path.resolve()


def test_check_and_compose_use_the_real_adapters(
    source_root: Path, tmp_path: Path
) -> None:
    """Wired actions validate, compose, and verify a synthetic source tree."""
    actions = build_actions()
    output = tmp_path / "composed"

    assert actions.check(source_root).valid
    assert actions.compose(source_root, "backend", (), (), output, ()) == output
    assert actions.provenance(output).valid


def test_apm_runs_only_after_provenance_passes(
    source_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verified workspace reaches the APM adapter and returns no report."""
    calls: list[Path] = []
    monkeypatch.setattr(
        root_module.ApmCliAdapter, "check", lambda _self, root: calls.append(root)
    )
    actions = build_actions()
    output = actions.compose(source_root, "backend", (), (), tmp_path / "out", ())

    assert actions.apm_check(output) is None
    assert calls == [output]
