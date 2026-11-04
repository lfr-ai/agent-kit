"""Licensed deterministic source-archive contract independent of vendor packing."""

from pathlib import Path
import sys
import zipfile

import pytest
import scripts.build_capabilities as archive_module


def test_archive_contains_source_license_and_fixed_metadata(
    source_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero exit status must accompany actual capabilities, license, and stable ZIP metadata."""
    output = tmp_path / "archives"
    monkeypatch.setattr(archive_module, "_ROOT", source_root)
    monkeypatch.setattr(archive_module, "_OUTPUT", output)
    monkeypatch.setattr(sys, "argv", ["build-capabilities", "--profile", "backend"])

    assert archive_module.main() == 0
    artifact = output / "agent-kit-backend-0.1.0.zip"
    with zipfile.ZipFile(artifact) as archive:
        names = set(archive.namelist())
        assert {"LICENSE", "apm.yml", "apm-policy.yml", "provenance.json"}.issubset(
            names
        )
        assert ".apm/skills/kit-backend/SKILL.md" in names
        assert all(
            info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()
        )
    existing = artifact.read_bytes()

    with pytest.raises(FileExistsError, match="exists"):
        archive_module.main()
    assert artifact.read_bytes() == existing
