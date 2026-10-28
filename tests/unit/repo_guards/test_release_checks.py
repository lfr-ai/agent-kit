"""Release version, license, source provenance, and artifact inventory contracts."""

from collections.abc import Callable
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
        '[build-system]\nrequires=["hatchling==1.27.0"]\n'
        'build-backend="hatchling.build"\n'
        '[project]\nname="agent-kit"\nversion="0.1.0"\nlicense="MIT"\n'
        '[project.scripts]\nagent-kit="agent_kit.main:main"\n'
        '[tool.hatch.build.targets.wheel]\npackages=["src/agent_kit"]\n',
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
        "terraform",
        "bicep",
        "remote-access",
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
        archive.writestr("agent_kit/__init__.py", "")
        archive.writestr("agent_kit/main.py", "def main() -> int:\n    return 0\n")
        archive.writestr(
            "agent_kit-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nagent-kit = agent_kit.main:main\n",
        )
        archive.writestr(
            "agent_kit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: agent-kit\nVersion: 0.1.0\nLicense-Expression: MIT\n",
        )
        archive.writestr("agent_kit-0.1.0.dist-info/licenses/LICENSE", license_bytes)
    with tarfile.open(distributions / "agent_kit-0.1.0.tar.gz", "w:gz") as archive:
        for name, content in {
            "LICENSE": license_bytes,
            "pyproject.toml": (root / "pyproject.toml").read_bytes(),
            "src/agent_kit/__init__.py": b"",
            "src/agent_kit/main.py": b"def main() -> int:\n    return 0\n",
        }.items():
            entry = tarfile.TarInfo(f"agent_kit-0.1.0/{name}")
            entry.size = len(content)
            archive.addfile(entry, BytesIO(content))
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
    output.write_bytes(b"stale checksums\n")
    assert write_checksums(release_root).read_bytes() == original


@pytest.mark.parametrize("prepare", [write_checksums, stage_release])
@pytest.mark.parametrize("target_exists", [True, False])
def test_checksum_link_is_refused_without_touching_external_bytes(
    release_root: Path, prepare: Callable[[Path], Path], target_exists: bool
) -> None:
    """Neither checksum entry point may follow a live or dangling output link."""
    external = release_root.parent / "external"
    if target_exists:
        external.write_bytes(b"preserve external bytes\n")
    output = release_root / "build/SHA256SUMS"
    try:
        output.symlink_to(external)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    before = set(output.parent.iterdir())

    with pytest.raises(ValueError, match=r"checksum|link|regular"):
        prepare(release_root)

    assert output.is_symlink()
    if target_exists:
        assert external.read_bytes() == b"preserve external bytes\n"
    else:
        assert not external.exists()
    assert set(output.parent.iterdir()) == before


@pytest.mark.parametrize("prepare", [write_checksums, stage_release])
def test_checksum_directory_is_explicitly_refused(
    release_root: Path, prepare: Callable[[Path], Path]
) -> None:
    """An irregular checksum target is not replaced or left with temporary files."""
    output = release_root / "build/SHA256SUMS"
    output.mkdir()
    before = set(output.parent.iterdir())

    with pytest.raises(ValueError, match=r"checksum|regular"):
        prepare(release_root)

    assert output.is_dir()
    assert set(output.parent.iterdir()) == before


@pytest.mark.parametrize("prepare", [write_checksums, stage_release])
def test_checksum_hard_link_is_refused_without_touching_external_bytes(
    release_root: Path, prepare: Callable[[Path], Path]
) -> None:
    """A regular file shared with an external path is not owned checksum output."""
    external = release_root.parent / "external"
    external.write_bytes(b"preserve external bytes\n")
    output = release_root / "build/SHA256SUMS"
    output.hardlink_to(external)
    before = set(output.parent.iterdir())

    with pytest.raises(ValueError, match=r"checksum|regular"):
        prepare(release_root)

    assert external.read_bytes() == b"preserve external bytes\n"
    assert output.samefile(external)
    assert set(output.parent.iterdir()) == before


@pytest.mark.parametrize("prepare", [write_checksums, stage_release])
def test_linked_build_cannot_redirect_checksums(
    release_root: Path, prepare: Callable[[Path], Path]
) -> None:
    """Standalone checksum generation has the same build boundary as staging."""
    build = release_root / "build"
    external = release_root.parent / "external-build"
    build.rename(external)
    try:
        build.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    before = set(external.iterdir())

    with pytest.raises(ValueError, match=r"build|link"):
        prepare(release_root)

    assert set(external.iterdir()) == before


def test_checksum_publication_failure_preserves_previous_output_and_cleans_temp(
    release_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed replacement cannot truncate a previous checksum witness."""
    output = release_root / "build/SHA256SUMS"
    output.write_bytes(b"previous checksums\n")
    before = set(output.parent.iterdir())
    failure = OSError("controlled checksum replacement failure")

    def fail_replace(temporary: Path, destination: Path) -> Path:
        assert temporary.parent == output.parent
        assert temporary != output
        assert temporary.is_file()
        assert destination == output
        raise failure

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="controlled") as raised:
        write_checksums(release_root)

    assert raised.value is failure
    assert output.read_bytes() == b"previous checksums\n"
    assert set(output.parent.iterdir()) == before


def test_checksum_target_is_rechecked_before_publication(
    release_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link introduced while preparing the sibling file is refused and cleaned up."""
    external = release_root.parent / "external"
    external.write_bytes(b"preserve external bytes\n")
    output = release_root / "build/SHA256SUMS"
    try:
        output.symlink_to(external)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    output.unlink()
    before = set(output.parent.iterdir())
    verify = release_module._verify_checksum_target
    calls = 0

    def link_before_final_check(root: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            destination.symlink_to(external)
        verify(root, destination)

    monkeypatch.setattr(
        release_module, "_verify_checksum_target", link_before_final_check
    )
    with pytest.raises(ValueError, match=r"checksum|regular"):
        write_checksums(release_root)

    assert external.read_bytes() == b"preserve external bytes\n"
    assert output.is_symlink()
    assert set(output.parent.iterdir()) == before | {output}


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


@pytest.mark.parametrize(
    "member",
    [
        "agent_kit/__init__.py",
        "agent_kit/main.py",
        "agent_kit-0.1.0.dist-info/entry_points.txt",
    ],
)
def test_wheel_requires_package_code_and_console_entrypoint(
    release_root: Path, member: str
) -> None:
    """Matching metadata and a license cannot substitute for the distributable CLI."""
    path = release_root / "build/distributions/agent_kit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    del contents[member]
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)

    assert any("wheel" in item for item in check(release_root, tag=""))


@pytest.mark.parametrize(
    ("member", "content"),
    [
        ("agent_kit/main.py", ""),
        (
            "agent_kit-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nagent-kit = unrelated.main:main\n",
        ),
        (
            "agent_kit-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nAgent-Kit = agent_kit.main:main\n",
        ),
        ("agent_kit-0.1.0.dist-info/entry_points.txt", "malformed entry points"),
    ],
)
def test_wheel_rejects_empty_code_or_invalid_console_entrypoint(
    release_root: Path, member: str, content: str
) -> None:
    path = release_root / "build/distributions/agent_kit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents[member] = content.encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)

    assert any("wheel" in item for item in check(release_root, tag=""))
    with pytest.raises(ValueError, match="wheel"):
        write_checksums(release_root)
    assert not (release_root / "build/SHA256SUMS").exists()


@pytest.mark.parametrize(
    ("member", "replacement"),
    [
        ("src/agent_kit/__init__.py", None),
        ("src/agent_kit/main.py", None),
        ("pyproject.toml", None),
        ("src/agent_kit/main.py", b""),
        ("pyproject.toml", b'[project]\nname="unrelated"\n'),
    ],
)
def test_sdist_requires_implementation_and_build_metadata(
    release_root: Path, member: str, replacement: bytes | None
) -> None:
    """A license-only archive cannot stand in for the source distribution."""
    path = release_root / "build/distributions/agent_kit-0.1.0.tar.gz"
    with tarfile.open(path, "r:gz") as archive:
        contents = {}
        for item in archive.getmembers():
            stream = archive.extractfile(item)
            assert stream is not None
            contents[item.name] = stream.read()
    if replacement is None:
        del contents[f"agent_kit-0.1.0/{member}"]
    else:
        contents[f"agent_kit-0.1.0/{member}"] = replacement
    with tarfile.open(path, "w:gz") as archive:
        for name, content in contents.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, BytesIO(content))

    assert any("sdist" in item for item in check(release_root, tag=""))


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
