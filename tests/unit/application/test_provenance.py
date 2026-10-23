"""Composed-workspace integrity verification."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import yaml

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.infrastructure.output_adapter import OutputAdapter

if TYPE_CHECKING:
    from pathlib import Path

    from agent_kit.core.models import CheckReport


def _compose(source_root: Path, output: Path) -> Path:
    snapshot = FileCatalogAdapter().load(source_root)
    plan = CatalogService().compose(snapshot, "backend", (), ())
    return OutputAdapter().write(plan, output)


def _verify(root: Path) -> CheckReport:
    snapshot = FileCatalogAdapter().load_composed(root)
    return ProvenanceService().verify(snapshot)


def test_new_composition_passes_provenance(source_root: Path, tmp_path: Path) -> None:
    output = _compose(source_root, tmp_path / "backend")

    report = _verify(output)

    assert report.valid
    assert report.version == "0.1.0"


def test_provenance_hashes_manifest_and_native_policy(
    source_root: Path, tmp_path: Path
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert {"apm.yml", "apm-policy.yml"}.issubset(provenance["files"])
    assert str(source_root) not in (output / "provenance.json").read_text(
        encoding="utf-8"
    )

    for relative in ("apm.yml", "apm-policy.yml"):
        target = output / relative
        target.write_bytes(target.read_bytes() + b"\n")
        report = _verify(output)
        assert not report.valid
        assert any(relative in item.message for item in report.findings)
        target.write_bytes(target.read_bytes()[:-1])
        assert _verify(output).valid


def test_modified_and_extra_apm_files_fail_provenance(
    source_root: Path, tmp_path: Path
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    skill = output / ".apm/skills/kit-backend/SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8"
    )
    (output / ".apm/extra.md").write_text("extra\n", encoding="utf-8")

    report = _verify(output)

    assert not report.valid
    assert any(item.code == "provenance.drift" for item in report.findings)
    assert any(item.code == "provenance.extra" for item in report.findings)


def test_missing_recorded_file_fails_provenance(
    source_root: Path, tmp_path: Path
) -> None:
    output = _compose(source_root, tmp_path / "backend")
    (output / ".apm/instructions/kit-backend.instructions.md").unlink()

    report = _verify(output)

    assert not report.valid
    assert any(item.code == "provenance.missing" for item in report.findings)


def test_malformed_provenance_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "invalid"
    output.mkdir()
    (output / "provenance.json").write_text("{broken", encoding="utf-8")

    report = _verify(output)

    assert not report.valid
    assert any(item.code == "provenance.read" for item in report.findings)


def test_recorded_native_delivery_is_accepted_after_installation(
    source_root: Path, tmp_path: Path
) -> None:
    """Source provenance remains valid after APM creates attested native output."""
    output = _compose(source_root, tmp_path / "backend")
    relative = ".agents/skills/kit-backend/SKILL.md"
    native = output / relative
    native.parent.mkdir(parents=True)
    native.write_bytes((output / ".apm/skills/kit-backend/SKILL.md").read_bytes())
    digest = hashlib.sha256(native.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    lock = {
        "lockfile_version": "1",
        "dependencies": [],
        "deployments": [
            {
                "kind": "project-relative",
                "target": "legacy",
                "value": relative,
                "scope": "project",
                "owners": ["."],
                "active_owner": ".",
                "content_hash": f"sha256:{digest}",
            }
        ],
    }
    (output / "apm.lock.yaml").write_text(yaml.safe_dump(lock), encoding="utf-8")

    assert _verify(output).valid

    native.write_text("changed delivery", encoding="utf-8")
    report = _verify(output)
    assert not report.valid
    assert any(item.code == "provenance.delivery-drift" for item in report.findings)
