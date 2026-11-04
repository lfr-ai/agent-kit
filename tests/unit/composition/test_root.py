"""Repository composition workflows reuse the validated application services."""

from pathlib import Path

import pytest

from agent_kit.application.services.catalog_service import CompositionError
from agent_kit.composition.root import (
    compose_workspace,
    validate_source,
    verify_provenance,
)


def test_source_and_composition_workflows_use_real_adapters(
    source_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "composed"

    assert validate_source(source_root).valid
    assert compose_workspace(source_root, "backend", (), (), output) == output.resolve()
    assert verify_provenance(output).valid


def test_invalid_source_prevents_composition_and_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "composed"

    with pytest.raises(CompositionError, match="source validation failed"):
        compose_workspace(tmp_path, "backend", (), (), output)

    assert not output.exists()


def test_provenance_workflow_reports_tampering(
    source_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "composed"
    compose_workspace(source_root, "backend", (), (), output)
    with (output / "apm.yml").open("ab") as stream:
        stream.write(b"\n")

    report = verify_provenance(output)

    assert not report.valid
    assert any(item.code == "provenance.drift" for item in report.findings)
