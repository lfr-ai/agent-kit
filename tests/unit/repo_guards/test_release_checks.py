"""Release version, license, source provenance, and artifact inventory contracts."""

from base64 import urlsafe_b64encode
from collections.abc import Callable
import csv
import hashlib
from io import BytesIO, StringIO
import json
from pathlib import Path
import tarfile
import tomllib
import zipfile

import pytest
import scripts.checks.release as release_module
from scripts.checks.release import check, stage_release, write_checksums


def _update_record(files: dict[str, bytes]) -> None:
    record = "platform_kit_runtime-0.4.2.dist-info/RECORD"
    stream = StringIO()
    writer = csv.writer(stream)
    for name, content in files.items():
        if name != record:
            digest = urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
            writer.writerow([name, "sha256=" + digest.decode("ascii"), len(content)])
    writer.writerow([record, "", ""])
    files[record] = stream.getvalue().encode()


def _write_distribution(
    path: Path, files: dict[str, bytes], *, update_record: bool = True
) -> None:
    if path.suffix == ".whl":
        if update_record:
            _update_record(files)
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
    else:
        with tarfile.open(path, "w:gz") as archive:
            for name, content in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                archive.addfile(entry, BytesIO(content))


def _runtime_distribution(root: Path, kind: str) -> tuple[Path, dict[str, bytes]]:
    suffix = "-py3-none-any.whl" if kind == "wheel" else ".tar.gz"
    path = root / f"build/distributions/platform_kit_runtime-0.4.2{suffix}"
    if kind == "wheel":
        with zipfile.ZipFile(path) as archive:
            return path, {name: archive.read(name) for name in archive.namelist()}
    with tarfile.open(path) as archive:
        files = {}
        for member in archive.getmembers():
            stream = archive.extractfile(member)
            assert stream is not None
            files[member.name] = stream.read()
        return path, files


def _build_runtime_fixture(root: Path) -> None:
    package = root / "packages/runtime"
    package.mkdir()
    files = {
        "LICENSE": b"MIT License\nRuntime contributors\n",
        "README.md": b"# Independent runtime\n",
        "docs/ai.md": b"# Optional AI\n",
        "docs/identity.md": b"# Optional identity\n",
        "src/platform_kit_runtime/__init__.py": b"from .composition import create_app\n",
        "src/platform_kit_runtime/composition.py": b"def create_app(): return None\n",
        "src/platform_kit_runtime/py.typed": b"",
        "pyproject.toml": (
            b'[build-system]\nrequires=["hatchling==1.27.0"]\n'
            b'build-backend="hatchling.build"\n'
            b'[project]\nname="platform-kit-runtime"\nversion="0.4.2"\n'
            b'license="MIT"\nlicense-files=["LICENSE"]\nreadme="README.md"\n'
            b'requires-python=">=3.13"\ndependencies=["fastapi>=0.162.0,<1"]\n'
            b'[project.optional-dependencies]\nauth=["msal>=1.39.0,<2"]\n'
            b'ai=["litellm>=1.103.7,<1.104"]\n'
            b'[tool.hatch.build.targets.wheel]\npackages=["src/platform_kit_runtime"]\n'
            b"[tool.hatch.build.targets.sdist]\n"
            b'include=["/src", "/README.md", "/docs", "/LICENSE", "/pyproject.toml"]\n'
        ),
    }
    for name, content in files.items():
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    metadata = (
        b"Metadata-Version: 2.4\nName: platform-kit-runtime\nVersion: 0.4.2\n"
        b"License-Expression: MIT\nRequires-Python: >=3.13\n"
        b"Requires-Dist: fastapi<1,>=0.162.0\n"
        b"Provides-Extra: ai\nProvides-Extra: auth\n"
        b"Requires-Dist: litellm<1.104,>=1.103.7; extra == 'ai'\n"
        b"Requires-Dist: msal<2,>=1.39.0; extra == 'auth'\n"
    )
    prefix = "platform_kit_runtime-0.4.2"
    _write_distribution(
        root / f"build/distributions/{prefix}-py3-none-any.whl",
        {
            **{
                name.removeprefix("src/"): content
                for name, content in files.items()
                if name.startswith("src/")
            },
            f"{prefix}.dist-info/METADATA": metadata,
            f"{prefix}.dist-info/licenses/LICENSE": files["LICENSE"],
            f"{prefix}.dist-info/WHEEL": (
                b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
            ),
            f"{prefix}.dist-info/RECORD": b"",
        },
    )
    _write_distribution(
        root / f"build/distributions/{prefix}.tar.gz",
        {
            f"{prefix}/{name}": content
            for name, content in {**files, "PKG-INFO": metadata}.items()
        },
    )


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
        "temporal",
        "identity",
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
        archive.writestr(
            "agent_kit/application/catalog/service.py",
            "class CatalogService:\n    pass\n",
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
            "src/agent_kit/application/catalog/service.py": (
                b"class CatalogService:\n    pass\n"
            ),
        }.items():
            entry = tarfile.TarInfo(f"agent_kit-0.1.0/{name}")
            entry.size = len(content)
            archive.addfile(entry, BytesIO(content))
    files = {
        "LICENSE": license_bytes,
        "apm.yml": b'license: MIT\nversion: "0.1.0"\n',
        "apm-policy.yml": b"enforcement: block\n",
        ".apm/skills/kit-test/SKILL.md": b"# Synthetic skill\n",
        ".github/agents/kit-example.agent.md": b"---\ntools: [read, search]\n---\nRead only.\n",
        ".claude/agents/kit-example.md": b"---\ntools: Read, Grep, Glob\n---\nRead only.\n",
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
    _build_runtime_fixture(root)
    return root


def test_verified_artifacts_have_deterministic_checksums(release_root: Path) -> None:
    """The build gate checks actual contents then emits basename-only checksums."""
    assert check(release_root) == []

    output = write_checksums(release_root)
    original = output.read_bytes()
    assert len(output.read_text().splitlines()) == 5
    assert original == write_checksums(release_root).read_bytes()
    assert b".." not in original
    output.write_bytes(b"stale checksums\n")
    assert write_checksums(release_root).read_bytes() == original


def test_runtime_version_and_license_are_read_from_its_own_package(
    release_root: Path,
) -> None:
    """The runtime is independently versioned, not forced to the toolkit version."""
    runtime = tomllib.loads(
        (release_root / "packages/runtime/pyproject.toml").read_text()
    )
    assert runtime["project"]["version"] == "0.4.2"
    assert check(release_root) == []
    stage = stage_release(release_root)
    assert (stage / "platform_kit_runtime-0.4.2-py3-none-any.whl").is_file()
    assert (stage / "platform_kit_runtime-0.4.2.tar.gz").is_file()


def test_missing_runtime_products_cannot_pass_as_a_maintainer_only_release(
    release_root: Path,
) -> None:
    for kind in ("wheel", "sdist"):
        path, _files = _runtime_distribution(release_root, kind)
        path.unlink()
    assert any("inventory" in finding for finding in check(release_root))
    with pytest.raises(ValueError, match="inventory"):
        stage_release(release_root)
    assert not (release_root / "build/SHA256SUMS").exists()


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    ("member", "replacement"),
    [
        ("__init__.py", None),
        ("composition.py", None),
        ("py.typed", None),
        ("composition.py", b""),
        ("composition.py", b"def create_app(): return 'tampered'\n"),
        ("unexpected.py", b"unreviewed = True\n"),
    ],
)
def test_runtime_requires_exact_implementation(
    release_root: Path, kind: str, member: str, replacement: bytes | None
) -> None:
    path, files = _runtime_distribution(release_root, kind)
    prefix = "" if kind == "wheel" else "platform_kit_runtime-0.4.2/src/"
    name = f"{prefix}platform_kit_runtime/{member}"
    if replacement is None:
        del files[name]
    else:
        files[name] = replacement
    _write_distribution(path, files)

    assert any(kind in finding for finding in check(release_root))
    with pytest.raises(ValueError, match=kind):
        write_checksums(release_root)
    assert not (release_root / "build/SHA256SUMS").exists()


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Version: 0.4.2", "Version: 0.1.0"),
        ("Name: platform-kit-runtime", "Name: agent-kit"),
        ("License-Expression: MIT", "License-Expression: Apache-2.0"),
        ("Requires-Python: >=3.13", "Requires-Python: >=3.14"),
        ("fastapi<1,>=0.162.0", "fastapi<2,>=0.162.0"),
        ("; extra == 'ai'", ""),
        ("; extra == 'auth'", "; extra == 'ai'"),
        ("Provides-Extra: auth\n", ""),
        ("Provides-Extra: ai", "Provides-Extra: ai\nProvides-Extra: unreviewed"),
        ("Requires-Dist: msal", "Requires-Dist: agent-kit"),
    ],
)
def test_runtime_metadata_and_optional_extra_isolation(
    release_root: Path, kind: str, old: str, new: str
) -> None:
    path, files = _runtime_distribution(release_root, kind)
    metadata = (
        "platform_kit_runtime-0.4.2.dist-info/METADATA"
        if kind == "wheel"
        else "platform_kit_runtime-0.4.2/PKG-INFO"
    )
    files[metadata] = files[metadata].replace(old.encode(), new.encode())
    _write_distribution(path, files)

    assert any(kind in finding for finding in check(release_root))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_runtime_license_bytes_are_not_just_a_label(
    release_root: Path, kind: str
) -> None:
    path, files = _runtime_distribution(release_root, kind)
    license_name = (
        "platform_kit_runtime-0.4.2.dist-info/licenses/LICENSE"
        if kind == "wheel"
        else "platform_kit_runtime-0.4.2/LICENSE"
    )
    files[license_name] = (release_root / "LICENSE").read_bytes()
    _write_distribution(path, files)
    assert any(kind in finding for finding in check(release_root))


@pytest.mark.parametrize("member", ["composition.py", "py.typed"])
def test_runtime_cannot_omit_required_source_and_artifact_files(
    release_root: Path, member: str
) -> None:
    (release_root / f"packages/runtime/src/platform_kit_runtime/{member}").unlink()
    for kind in ("wheel", "sdist"):
        path, files = _runtime_distribution(release_root, kind)
        prefix = "" if kind == "wheel" else "platform_kit_runtime-0.4.2/src/"
        del files[f"{prefix}platform_kit_runtime/{member}"]
        _write_distribution(path, files)
    assert check(release_root)


@pytest.mark.parametrize("member", ["WHEEL", "RECORD"])
def test_runtime_wheel_installation_metadata_cannot_be_tampered(
    release_root: Path, member: str
) -> None:
    path, files = _runtime_distribution(release_root, "wheel")
    files[f"platform_kit_runtime-0.4.2.dist-info/{member}"] = b"tampered\n"
    _write_distribution(path, files, update_record=member != "RECORD")
    assert any("wheel" in finding for finding in check(release_root))


@pytest.mark.parametrize("version", ["0.4", "next", "42"])
def test_invalid_runtime_source_version_is_a_reported_finding(
    release_root: Path, version: str
) -> None:
    project = release_root / "packages/runtime/pyproject.toml"
    project.write_text(
        project.read_text().replace('version="0.4.2"', f'version="{version}"')
    )
    assert any(
        finding.startswith(
            "release source metadata cannot be validated: _ReleaseContractError: "
        )
        for finding in check(release_root)
    )


@pytest.mark.parametrize(
    "declaration",
    [
        "Requires-Dist: agent-kit==0.1.0\n",
        "Requires-Dist: extra-tool @ https://invalid.test/tool.whl\n",
        "Requires-Dist: msal<2,>=1.39.0; python_version > '3.13'\n",
    ],
)
def test_runtime_rejects_undeclared_or_unsupported_dependencies(
    release_root: Path, declaration: str
) -> None:
    path, files = _runtime_distribution(release_root, "wheel")
    files["platform_kit_runtime-0.4.2.dist-info/METADATA"] += declaration.encode()
    _write_distribution(path, files)
    assert any("wheel" in finding for finding in check(release_root))


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_runtime_rejects_foreign_archive_files(release_root: Path, kind: str) -> None:
    path, files = _runtime_distribution(release_root, kind)
    files["agent_kit/__init__.py"] = b"foreign = True\n"
    _write_distribution(path, files)
    assert any(kind in finding for finding in check(release_root))


@pytest.mark.parametrize("member", ["pyproject.toml", "docs/ai.md", "README.md"])
def test_runtime_sdist_must_match_canonical_source(
    release_root: Path, member: str
) -> None:
    path, files = _runtime_distribution(release_root, "sdist")
    files[f"platform_kit_runtime-0.4.2/{member}"] += b"\n# unreviewed\n"
    _write_distribution(path, files)
    assert any("sdist" in finding for finding in check(release_root))


@pytest.mark.parametrize("owner", [".", "packages", "packages/runtime"])
def test_runtime_sdist_inherits_only_the_nearest_canonical_gitignore(
    release_root: Path, owner: str
) -> None:
    """Hatchling force-includes the nearest .gitignore, including a workspace ancestor."""
    (release_root / ".gitignore").write_bytes(b"root-only/\n")
    expected = b"__pycache__/\nbuild/\n"
    (release_root / owner / ".gitignore").write_bytes(expected)
    path, files = _runtime_distribution(release_root, "sdist")
    files["platform_kit_runtime-0.4.2/.gitignore"] = expected
    _write_distribution(path, files)

    assert check(release_root) == []
    assert (stage_release(release_root) / path.name).read_bytes() == path.read_bytes()


@pytest.mark.parametrize("mutation", ["missing", "tampered", "shadowed", "outside"])
def test_runtime_sdist_gitignore_still_requires_exact_source_identity(
    release_root: Path, mutation: str
) -> None:
    path, files = _runtime_distribution(release_root, "sdist")
    canonical = b"__pycache__/\nbuild/\n"
    owner = release_root.parent if mutation == "outside" else release_root
    (owner / ".gitignore").write_bytes(canonical)
    if mutation == "shadowed":
        (release_root / "packages/runtime/.gitignore").write_bytes(b"local-only/\n")
    if mutation != "missing":
        files["platform_kit_runtime-0.4.2/.gitignore"] = (
            b"tampered/\n" if mutation == "tampered" else canonical
        )
    _write_distribution(path, files)

    assert any("sdist" in finding for finding in check(release_root))
    with pytest.raises(ValueError, match="sdist"):
        write_checksums(release_root)


def test_runtime_sdist_cannot_trust_a_linked_gitignore(release_root: Path) -> None:
    external = release_root.parent / "external-ignore"
    external.write_bytes(b"outside/\n")
    try:
        (release_root / ".gitignore").symlink_to(external)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    path, files = _runtime_distribution(release_root, "sdist")
    files["platform_kit_runtime-0.4.2/.gitignore"] = external.read_bytes()
    _write_distribution(path, files)

    assert any("sdist" in finding for finding in check(release_root))
    assert external.read_bytes() == b"outside/\n"


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_runtime_rejects_duplicate_entries(release_root: Path, kind: str) -> None:
    path, files = _runtime_distribution(release_root, kind)
    name, content = next(iter(files.items()))
    if kind == "wheel":
        with (
            zipfile.ZipFile(path, "a") as archive,
            pytest.warns(UserWarning, match="Duplicate name"),
        ):
            archive.writestr(name, content)
    else:
        with tarfile.open(path, "w:gz") as archive:
            for member, data in [*files.items(), (name, content)]:
                entry = tarfile.TarInfo(member)
                entry.size = len(data)
                archive.addfile(entry, BytesIO(data))
    assert any(kind in finding for finding in check(release_root))


def test_stale_runtime_artifact_is_not_silently_staged(release_root: Path) -> None:
    (
        release_root / "build/distributions/platform_kit_runtime-0.1.0.tar.gz"
    ).write_bytes(b"stale")
    with pytest.raises(ValueError, match="inventory"):
        stage_release(release_root)


def test_runtime_tampering_between_checksums_and_staging_is_refused(
    release_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = release_module.write_checksums

    def tamper_after_checksums(root: Path, *, tag: str | None) -> Path:
        result = original(root, tag=tag)
        path, _files = _runtime_distribution(root, "wheel")
        path.write_bytes(b"changed after validation")
        return result

    monkeypatch.setattr(release_module, "write_checksums", tamper_after_checksums)
    with pytest.raises(ValueError, match="changed during preparation"):
        stage_release(release_root)
    assert not (release_root / "build/release").exists()


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


def test_empty_tag_is_a_mismatch_not_a_local_check(release_root: Path) -> None:
    """Only ``None`` selects a local check; an explicit empty tag fails closed."""
    assert any("tag" in item for item in check(release_root, tag=""))


def test_uv_build_ignore_marker_is_not_a_release_product(release_root: Path) -> None:
    """uv's known build-directory marker is excluded, but arbitrary extra files are not."""
    marker = release_root / "build/distributions/.gitignore"
    marker.write_bytes(b"*")
    assert check(release_root) == []

    marker.write_bytes(b"unreviewed content")
    assert any("inventory" in item for item in check(release_root))


def test_version_drift_in_a_bundle_is_rejected(release_root: Path) -> None:
    """One stale APM manifest prevents a misleading unified release."""
    path = release_root / "packages/frontend/apm.yml"
    path.write_text('version: "0.0.9"\nlicense: MIT\n', encoding="utf-8")

    assert any("frontend" in item for item in check(release_root))


def test_extra_stale_artifact_is_rejected(release_root: Path) -> None:
    """An old distribution is not attached to a new release just because it matches a glob."""
    (release_root / "build/distributions/agent_kit-0.0.9.tar.gz").write_bytes(b"stale")

    assert any("inventory" in item for item in check(release_root))


def test_tampered_source_zip_is_rejected(release_root: Path) -> None:
    """Matching filenames do not substitute for source integrity."""
    path = release_root / "build/capabilities/agent-kit-fullstack-iac-0.1.0.zip"
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(".apm/extra.txt", "unattested")

    assert any("source archive" in item for item in check(release_root))


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

    assert any("source archive" in item for item in check(release_root))


def test_missing_license_in_wheel_is_rejected(release_root: Path) -> None:
    """A wheel must carry the source license, not only a license label."""
    path = release_root / "build/distributions/agent_kit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as archive:
        metadata = archive.read("agent_kit-0.1.0.dist-info/METADATA")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("agent_kit-0.1.0.dist-info/METADATA", metadata)

    assert any("wheel" in item for item in check(release_root))


@pytest.mark.parametrize(
    "member",
    [
        "agent_kit/__init__.py",
        "agent_kit/application/catalog/service.py",
    ],
)
def test_wheel_requires_package_implementation(release_root: Path, member: str) -> None:
    """Matching metadata and a license cannot substitute for package code."""
    path = release_root / "build/distributions/agent_kit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    del contents[member]
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in contents.items():
            archive.writestr(name, content)

    assert any("wheel" in item for item in check(release_root))


@pytest.mark.parametrize(
    ("member", "content"),
    [
        ("agent_kit/application/catalog/service.py", ""),
        (
            "agent_kit-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nagent-kit = unrelated.main:main\n",
        ),
        (
            "agent_kit-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nAgent-Kit = agent_kit.main:main\n",
        ),
        (
            "agent_kit-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nother-command = unrelated.main:main\n",
        ),
        ("agent_kit-0.1.0.dist-info/entry_points.txt", "malformed entry points"),
        ("agent_kit/main.py", "def main() -> int: return 0\n"),
        ("agent_kit/__main__.py", "raise SystemExit(0)\n"),
    ],
)
def test_wheel_rejects_empty_code_or_public_cli(
    release_root: Path, member: str, content: str
) -> None:
    path = release_root / "build/distributions/agent_kit-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    contents[member] = content.encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)

    assert any("wheel" in item for item in check(release_root))
    with pytest.raises(ValueError, match="wheel"):
        write_checksums(release_root)
    assert not (release_root / "build/SHA256SUMS").exists()


@pytest.mark.parametrize(
    ("member", "replacement"),
    [
        ("src/agent_kit/__init__.py", None),
        ("src/agent_kit/application/catalog/service.py", None),
        ("pyproject.toml", None),
        ("src/agent_kit/application/catalog/service.py", b""),
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

    assert any("sdist" in item for item in check(release_root))


def test_sdist_rejects_reintroduced_module_cli(release_root: Path) -> None:
    path = release_root / "build/distributions/agent_kit-0.1.0.tar.gz"
    with tarfile.open(path, "r:gz") as archive:
        contents = {}
        for item in archive.getmembers():
            stream = archive.extractfile(item)
            assert stream is not None
            contents[item.name] = stream.read()
    contents["agent_kit-0.1.0/src/agent_kit/__main__.py"] = b"raise SystemExit(0)\n"
    with tarfile.open(path, "w:gz") as archive:
        for name, content in contents.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, BytesIO(content))

    assert any("sdist" in item for item in check(release_root))


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
        "platform_kit_runtime-0.4.2-py3-none-any.whl",
        "platform_kit_runtime-0.4.2.tar.gz",
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


def test_release_cli_reports_malformed_metadata_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unreadable release metadata is a finding with exit code 1, not a traceback."""
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    monkeypatch.setattr(release_module, "_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release"])

    assert release_module.main() == 1
    assert "release source metadata cannot be validated" in capsys.readouterr().err


def test_release_cli_treats_an_empty_release_tag_as_a_local_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An untagged CI run exports ``RELEASE_TAG=""``; that must not mean a tag."""
    received: list[str | None] = []

    def capture(root: Path, *, tag: str | None = None) -> Path:
        received.append(tag)
        return root

    monkeypatch.setattr(release_module, "stage_release", capture)
    monkeypatch.setattr(release_module, "_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release"])
    monkeypatch.setenv("RELEASE_TAG", "")

    assert release_module.main() == 0
    assert received == [None]
