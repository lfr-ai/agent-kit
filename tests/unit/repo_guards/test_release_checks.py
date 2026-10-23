"""Release version, license, source provenance, and artifact inventory contracts."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile
import zipfile

import pytest
import scripts.check_release as release_module
from scripts.check_release import check, stage_release, write_checksums


@pytest.fixture
def release_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Prepare small synthetic distributions rather than building per test."""
    root = tmp_path / "release"
    root.mkdir()
    license_bytes = b"MIT License\nSynthetic license\n"
    (root / "LICENSE").write_bytes(license_bytes)
    (root / "pyproject.toml").write_text(
        '[project]\nname="agent-kit"\nversion="0.1.0"\nlicense="MIT"\n',
        encoding="utf-8",
    )
    (root / "catalog.json").write_text('{"version":"0.1.0"}', encoding="utf-8")
    (root / "apm.yml").write_text(
        'name: agent-kit\nversion: "0.1.0"\nlicense: MIT\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 0.1.0 - 2026-10-08\n", encoding="utf-8"
    )
    for name in (
        "shared",
        "backend",
        "frontend",
        "iac",
        "workflows",
        "ai",
        "coordination",
    ):
        bundle = root / "packages" / name
        bundle.mkdir(parents=True)
        (bundle / "apm.yml").write_text(
            'version: "0.1.0"\nlicense: MIT\n', encoding="utf-8"
        )
    distributions = root / "build/distributions"
    capabilities = root / "build/capabilities"
    distributions.mkdir(parents=True)
    capabilities.mkdir()
    with zipfile.ZipFile(
        distributions / "agent_kit-0.1.0-py3-none-any.whl", "w"
    ) as archive:
        archive.writestr(
            "agent_kit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: agent-kit\nVersion: 0.1.0\nLicense-Expression: MIT\n",
        )
        archive.writestr("agent_kit-0.1.0.dist-info/licenses/LICENSE", license_bytes)
    with tarfile.open(distributions / "agent_kit-0.1.0.tar.gz", "w:gz") as archive:
        entry = tarfile.TarInfo("agent_kit-0.1.0/LICENSE")
        entry.size = len(license_bytes)
        archive.addfile(entry, BytesIO(license_bytes))
    files = {
        "LICENSE": license_bytes,
        "apm.yml": b'license: MIT\nversion: "0.1.0"\n',
        "apm-policy.yml": b"enforcement: block\n",
        ".apm/skills/kit-test/SKILL.md": b"# Synthetic skill\n",
        ".github/agents/subagents/kit-reviewer.agent.md": b"---\ntools: [read, search]\n---\nRead only.\n",
        ".claude/agents/subagents/kit-reviewer.md": b"---\ntools: Read, Grep, Glob\n---\nRead only.\n",
    }
    provenance = {
        "source": {"catalog_version": "0.1.0"},
        "files": {
            name: hashlib.sha256(value).hexdigest() for name, value in files.items()
        },
    }
    with zipfile.ZipFile(
        capabilities / "agent-kit-fullstack-iac-0.1.0.zip", "w"
    ) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("provenance.json", json.dumps(provenance))
    trusted = {
        **files,
        "provenance.json": json.dumps(provenance).encode("utf-8"),
    }
    monkeypatch.setattr(release_module, "_expected_source", lambda _root: trusted)
    return root


def test_verified_artifacts_have_deterministic_checksums(release_root: Path) -> None:
    """The build gate checks actual contents then emits basename-only checksums."""
    assert check(release_root, tag="") == []

    output = write_checksums(release_root)
    original = output.read_bytes()
    assert len(output.read_text().splitlines()) == 3
    assert original == write_checksums(release_root).read_bytes()
    assert b".." not in original


def test_wrong_tag_is_rejected_before_publication(release_root: Path) -> None:
    """A tag cannot publish artifacts belonging to a different toolkit version."""
    assert any("tag" in item for item in check(release_root, tag="v0.2.0"))


def test_uv_build_ignore_marker_is_not_a_release_product(release_root: Path) -> None:
    """uv's known build-directory marker is excluded, but arbitrary extra files are not."""
    marker = release_root / "build/distributions/.gitignore"
    marker.write_bytes(b"*")
    assert check(release_root, tag="") == []

    marker.write_bytes(b"unreviewed content")
    assert any("inventory" in item for item in check(release_root, tag=""))


def test_version_drift_in_a_bundle_is_rejected(release_root: Path) -> None:
    """One stale APM manifest prevents a misleading unified release."""
    path = release_root / "packages/frontend/apm.yml"
    path.write_text('version: "0.0.9"\nlicense: MIT\n', encoding="utf-8")

    assert any("frontend" in item for item in check(release_root, tag=""))


def test_extra_stale_artifact_is_rejected(release_root: Path) -> None:
    """An old distribution is not attached to a new release just because it matches a glob."""
    (release_root / "build/distributions/agent_kit-0.0.9.tar.gz").write_bytes(b"stale")

    assert any("inventory" in item for item in check(release_root, tag=""))


def test_tampered_source_zip_is_rejected(release_root: Path) -> None:
    """Matching filenames do not substitute for source integrity."""
    path = release_root / "build/capabilities/agent-kit-fullstack-iac-0.1.0.zip"
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(".apm/extra.txt", "unattested")

    assert any("source archive" in item for item in check(release_root, tag=""))


def test_coordinated_zip_and_provenance_tampering_is_rejected(
    release_root: Path,
) -> None:
    """An archive cannot independently attest a changed skill with its own edited hash."""
    path = release_root / "build/capabilities/agent-kit-fullstack-iac-0.1.0.zip"
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    changed = ".apm/skills/kit-test/SKILL.md"
    contents[changed] = b"unreviewed procedure"
    provenance = json.loads(contents["provenance.json"])
    provenance["files"][changed] = hashlib.sha256(contents[changed]).hexdigest()
    contents["provenance.json"] = json.dumps(provenance).encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)

    assert any("source archive" in item for item in check(release_root, tag=""))


def test_missing_license_in_wheel_is_rejected(release_root: Path) -> None:
    """A wheel must carry the source license, not only a license label."""
    path = release_root / "build/distributions/agent_kit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as archive:
        metadata = archive.read("agent_kit-0.1.0.dist-info/METADATA")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("agent_kit-0.1.0.dist-info/METADATA", metadata)

    assert any("wheel" in item for item in check(release_root, tag=""))


def test_checksum_generation_refuses_unverified_artifacts(release_root: Path) -> None:
    """Checksum output is not created after artifact validation failed."""
    (release_root / "build/capabilities/agent-kit-fullstack-iac-0.1.0.zip").unlink()

    with pytest.raises(ValueError, match="inventory"):
        write_checksums(release_root)
    assert not (release_root / "build/SHA256SUMS").exists()


def test_release_upload_has_a_flat_verified_inventory(release_root: Path) -> None:
    """Upload and download consume identical basenames without nested directories."""
    stage = stage_release(release_root)
    expected = {
        "agent_kit-0.1.0-py3-none-any.whl",
        "agent_kit-0.1.0.tar.gz",
        "agent-kit-fullstack-iac-0.1.0.zip",
        "SHA256SUMS",
    }
    assert {path.name for path in stage.iterdir()} == expected
    for line in (stage / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((stage / name).read_bytes()).hexdigest() == digest
    original = {path.name: path.read_bytes() for path in stage.iterdir()}

    assert stage_release(release_root) == stage
    assert {path.name: path.read_bytes() for path in stage.iterdir()} == original


def test_release_staging_preserves_unknown_existing_files(release_root: Path) -> None:
    """Publication preparation never silently sweeps an old or operator-owned file."""
    stage = release_root / "build/release"
    stage.mkdir()
    old = stage / "unknown.zip"
    old.write_bytes(b"preserve")

    with pytest.raises(ValueError, match="staging"):
        stage_release(release_root)
    assert old.read_bytes() == b"preserve"
    assert list(stage.iterdir()) == [old]
