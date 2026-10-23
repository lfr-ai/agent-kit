"""Licensed deterministic source-archive contract independent of vendor packing."""

from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
import scripts.build_capabilities as archive_module

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.infrastructure.output_adapter import OutputAdapter


def test_archive_contains_source_license_and_fixed_metadata(
    source_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero exit status must accompany actual capabilities, license, and stable ZIP metadata."""
    output = tmp_path / "archives"
    monkeypatch.setattr(archive_module, "_ROOT", source_root)
    monkeypatch.setattr(archive_module, "_OUTPUT", output)
    monkeypatch.setattr(archive_module.shutil, "which", lambda _name: "agent-kit")
    monkeypatch.setattr(sys, "argv", ["build-capabilities", "--profile", "backend"])

    def run(arguments: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        if arguments[1] == "compose":
            snapshot = FileCatalogAdapter().load(source_root)
            plan = CatalogService().compose(snapshot, "backend", (), ())
            destination = Path(arguments[arguments.index("--output") + 1])
            OutputAdapter().write(plan, destination)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(archive_module.subprocess, "run", run)

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
