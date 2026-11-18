"""Validate exact release artifacts and versions before producing checksums."""

from __future__ import annotations

import argparse
from base64 import urlsafe_b64encode
import configparser
import csv
from dataclasses import dataclass
from email.parser import BytesParser
from enum import StrEnum, auto, unique
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tomllib
from typing import assert_never
import zipfile

import yaml

from agent_kit.composition.root import plan_composition
from agent_kit.core.guards import is_json_object, require_object, require_str_list
from agent_kit.core.paths import is_relative_file_path
from agent_kit.core.primitives import (
    PACKAGE_REQUIRED_FILES,
    SKILL_FILE,
    NativeRuntime,
)
from agent_kit.infrastructure.owned_output import replace_file
from scripts.build_profiles import LICENSE
from scripts.checks.governance import publication_blockers

_ROOT = Path(__file__).resolve().parent.parent.parent
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_RUNTIME_NAME = "platform-kit-runtime"
_SOURCE_PREFIXES = (
    ".apm/",
    *(f"{runtime.agent_directory}/" for runtime in NativeRuntime),
)
_REQUIREMENT = re.compile(
    r"([\w.-]+(?:\[[\w,.-]+\])?)"
    r"((?:(?:~=|==|!=|<=|>=|<|>)[0-9][\w.*+-]*,?)*)"
    r'(;extra=="[\w.-]+")?\Z'
)
_BUNDLES = (
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
)


@unique
class _ArtifactKind(StrEnum):
    """Closed archive formats understood by the local release checker."""

    WHEEL = auto()
    SDIST = auto()
    SOURCE = auto()


@dataclass(frozen=True, kw_only=True, slots=True)
class _Package:
    """Expected identity and implementation for one independently versioned package.

    ``root`` contains canonical metadata and license bytes. ``name`` and the
    nonempty ``implementation`` module are fixed expectations, while ``version``
    comes from this package's metadata rather than a shared release constant.
    """

    root: Path
    name: str
    version: str
    implementation: str

    @property
    def module(self) -> str:
        """Return the import and archive basename for this distribution."""
        return self.name.replace("-", "_")


@unique
class _ReleaseIssue(StrEnum):
    """Stable diagnostics for release metadata, archives, and staging."""

    INVALID_PROJECT_VERSION = "project version must be a numeric three-part release"
    INVALID_WHEEL = "wheel code, public CLI, metadata or license contract is invalid"
    UNSAFE_SDIST = "sdist contains unsafe members"
    INVALID_SDIST_LICENSE = "sdist license does not match"
    INVALID_SDIST_CONTENT = "sdist implementation or build metadata is invalid"
    INVALID_PACKAGE_METADATA = "package identity or dependency metadata is invalid"
    UNTRUSTED_PACKAGE = "package archive does not match canonical source"
    DUPLICATE_SOURCE_ENTRIES = "source archive has duplicate entries"
    UNTRUSTED_SOURCE = "source archive does not match independently composed source"
    INVALID_PROVENANCE = "source archive provenance is invalid"
    INVALID_SOURCE_INVENTORY = "source archive inventory or version is invalid"
    MISSING_CAPABILITIES = "source archive lacks licensed capabilities"
    INVALID_SOURCE_PATH = "source archive provenance or path is invalid"
    INVALID_SOURCE_MANIFEST = "source archive license or manifest is invalid"
    LINKED_BUILD_DIRECTORY = (
        "release preparation must not traverse a linked build directory"
    )
    INVALID_CHECKSUM_TARGET = (
        "release checksums require an owned regular file in the build directory"
    )
    INVALID_STAGING_DIRECTORY = "release staging must be an owned regular directory"
    UNKNOWN_STAGING_ENTRIES = "release staging contains unknown or linked entries"
    CHANGED_STAGING_SOURCE = "release staging source changed during preparation"
    INVALID_STAGING_COPY = "release staging verification failed"


class _ReleaseContractError(ValueError):
    """Report one fixed release contract failure without ad-hoc messages."""

    def __init__(self, issue: _ReleaseIssue) -> None:
        """Retain ``issue`` and use its fixed diagnostic as the message."""
        self.issue = issue
        super().__init__(issue.value)


class _ReleaseValidationError(ValueError):
    """Preserve the complete validation findings when checksum creation is refused."""

    def __init__(self, findings: list[str]) -> None:
        """Retain ``findings`` as an immutable tuple and join them for the message."""
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def _expected_source(root: Path) -> dict[str, bytes]:
    """Independently compose expected release bytes from the canonical source.

    The mapping is keyed by archive-relative path.
    """
    plan = plan_composition(root, "fullstack", ("iac",), ())
    return {item.relative_path: item.content for item in plan.files}


def _version(root: Path) -> str:
    """Read the numeric three-part version from ``root/pyproject.toml``.

    An invalid version raises ``_ReleaseContractError``.
    """
    value = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = require_object(value.get("project"), location="project")
    version = project.get("version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_PROJECT_VERSION)
    return version


def _artifacts(root: Path) -> dict[Path, tuple[_ArtifactKind, _Package]]:
    """Map exact build paths under ``root`` to format and per-package identity.

    Each package supplies its own version, and an invalid one raises
    ``_ReleaseContractError``; arbitrary matching globs are never accepted as
    release products.
    """
    artifacts: dict[Path, tuple[_ArtifactKind, _Package]] = {}
    for package_root, name, implementation in (
        (root, "agent-kit", "application/catalog/service.py"),
        (root / "packages/runtime", _RUNTIME_NAME, "composition.py"),
    ):
        package = _Package(
            root=package_root,
            name=name,
            version=_version(package_root),
            implementation=implementation,
        )
        prefix = root / f"build/distributions/{package.module}-{package.version}"
        artifacts[Path(f"{prefix}-py3-none-any.whl")] = (_ArtifactKind.WHEEL, package)
        artifacts[Path(f"{prefix}.tar.gz")] = (_ArtifactKind.SDIST, package)
        if package_root == root:
            source = (
                root
                / f"build/capabilities/agent-kit-fullstack-iac-{package.version}.zip"
            )
            artifacts[source] = (_ArtifactKind.SOURCE, package)
    return artifacts


class _EntryPointParser(configparser.ConfigParser):
    """Keep installed console command names case-sensitive."""

    # ConfigParser hook parameter name; cspell:ignore optionstr
    def optionxform(self, optionstr: str) -> str:
        """Return ``optionstr`` unchanged so console command names stay case-sensitive."""
        return optionstr


def _wheel(path: Path, package: _Package, license_bytes: bytes) -> None:
    """Require package implementation, metadata, license, and no public CLI.

    Args:
        path (Path): Wheel archive to inspect.
        package (_Package): Expected package identity and implementation.
        license_bytes (bytes): Exact bytes of this package's ``LICENSE``.

    Raises:
        _ReleaseContractError: The wheel content is invalid.
    """
    with zipfile.ZipFile(path) as archive:
        prefix = f"{package.module}-{package.version}.dist-info"
        names = set(archive.namelist())
        archive.read(f"{package.module}/__init__.py")
        implementation = archive.read(f"{package.module}/{package.implementation}")
        entry_points_path = f"{prefix}/entry_points.txt"
        entry_points_content = (
            archive.read(entry_points_path) if entry_points_path in names else b""
        )
        entry_points = _EntryPointParser(interpolation=None)
        if entry_points_content:
            try:
                entry_points.read_string(entry_points_content.decode("utf-8"))
            except configparser.Error as error:
                raise _ReleaseContractError(_ReleaseIssue.INVALID_WHEEL) from error
        metadata = BytesParser().parsebytes(archive.read(f"{prefix}/METADATA"))
        if (
            not implementation.strip()
            or (
                entry_points.has_section("console_scripts")
                and entry_points.items("console_scripts")
            )
            or f"{package.module}/main.py" in names
            or f"{package.module}/__main__.py" in names
            or metadata.get_all("Version") != [package.version]
            or metadata.get_all("Name") != [package.name]
            or metadata.get_all("License-Expression") != [LICENSE]
            or archive.read(f"{prefix}/licenses/LICENSE") != license_bytes
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_WHEEL)
        if package.name == _RUNTIME_NAME:
            if len(archive.namelist()) != len(names):
                raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_PACKAGE)
            _runtime_content(
                {name: archive.read(name) for name in names},
                package,
                kind=_ArtifactKind.WHEEL,
            )


def _sdist_file(archive: tarfile.TarFile, name: str) -> bytes:
    """Read one required regular source member without extracting to disk.

    Args:
        archive (tarfile.TarFile): Open source distribution.
        name (str): Member path inside the archive.

    Returns:
        bytes: The member's content.

    Raises:
        _ReleaseContractError: The required source member is not a file.
    """
    stream = archive.extractfile(name)
    if stream is None:
        raise _ReleaseContractError(_ReleaseIssue.INVALID_SDIST_CONTENT)
    with stream:
        return stream.read()


def _sdist(
    path: Path, package: _Package, license_bytes: bytes, *, project_bytes: bytes
) -> None:
    """Require source code and release/build metadata, rejecting unsafe members.

    Args:
        path (Path): Source distribution to inspect.
        package (_Package): Expected package identity and implementation.
        license_bytes (bytes): Exact bytes of this package's ``LICENSE``.
        project_bytes (bytes): Exact bytes of this package's ``pyproject.toml``.

    Raises:
        _ReleaseContractError: A member, implementation, build recipe, or license is invalid.
    """
    with tarfile.open(path, mode="r:gz") as archive:
        for item in archive.getmembers():
            if (
                not is_relative_file_path(item.name)
                or item.issym()
                or item.islnk()
                or (not item.isfile() and not item.isdir())
            ):
                raise _ReleaseContractError(_ReleaseIssue.UNSAFE_SDIST)
        prefix = f"{package.module}-{package.version}"
        if _sdist_file(archive, f"{prefix}/LICENSE") != license_bytes:
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SDIST_LICENSE)
        _sdist_file(archive, f"{prefix}/src/{package.module}/__init__.py")
        metadata = tomllib.loads(
            _sdist_file(archive, f"{prefix}/pyproject.toml").decode("utf-8")
        )
        expected = tomllib.loads(project_bytes.decode("utf-8"))
        names = {item.name.removeprefix(f"{prefix}/") for item in archive.getmembers()}
        if (
            not _sdist_file(
                archive, f"{prefix}/src/{package.module}/{package.implementation}"
            ).strip()
            or f"src/{package.module}/main.py" in names
            or f"src/{package.module}/__main__.py" in names
            or any(
                metadata.get(section) != expected.get(section)
                for section in ("build-system", "project")
            )
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SDIST_CONTENT)
        if package.name == _RUNTIME_NAME:
            _runtime_sdist(archive, package)


def _runtime_sdist(archive: tarfile.TarFile, package: _Package) -> None:
    """Check unique runtime sdist entries against independently read package bytes.

    Raises:
        _ReleaseContractError: Inventory, source bytes, or metadata differ.
    """
    prefix = f"{package.module}-{package.version}/"
    names = archive.getnames()
    if len(names) != len(set(names)) or any(
        not name.startswith(prefix) for name in names
    ):
        raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_PACKAGE)
    _runtime_content(
        {
            item.name.removeprefix(prefix): _sdist_file(archive, item.name)
            for item in archive.getmembers()
            if item.isfile()
        },
        package,
        kind=_ArtifactKind.SDIST,
    )


def _runtime_gitignore(package: _Package) -> dict[str, bytes]:
    """Read the nearest canonical ignore file that Hatchling adds to the sdist.

    The runtime lives at ``packages/runtime``. Stop at the repository root:
    an ignore file outside this boundary must not become trusted source. A linked
    candidate raises ``_ReleaseContractError``; the mapping is empty when no
    ignore file exists.
    """
    for directory in (package.root, package.root.parent, package.root.parent.parent):
        path = directory / ".gitignore"
        if path.is_symlink() or path.is_junction():
            raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_PACKAGE)
        if path.exists():
            return {path.name: path.read_bytes()}
    return {}


def _runtime_source(package: _Package, *, kind: _ArtifactKind) -> dict[str, bytes]:
    """Read canonical bytes in wheel or sdist layout, excluding Python bytecode caches.

    Sdists also include the exact inherited ignore file, not arbitrary build
    extras. Neither format can attest its own source inventory. A missing or
    unreadable source path propagates ``OSError``.

    Raises:
        _ReleaseContractError: Canonical paths are linked or not regular files.
    """
    roots = (
        ("src", "docs", "README.md", "LICENSE", "pyproject.toml")
        if kind == _ArtifactKind.SDIST
        else (f"src/{package.module}",)
    )
    files = _runtime_gitignore(package) if kind == _ArtifactKind.SDIST else {}
    for relative in roots:
        source = package.root / relative
        for path in (source, *source.rglob("*")):
            if "__pycache__" in path.parts:
                continue
            if path.is_symlink() or path.is_junction():
                raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_PACKAGE)
            if path.is_dir():
                continue
            name = path.relative_to(package.root).as_posix()
            files[
                name if kind == _ArtifactKind.SDIST else name.removeprefix("src/")
            ] = path.read_bytes()
    return files


def _requirement_key(value: str) -> tuple[str, tuple[str, ...], str]:
    """Normalize ``value`` to ``(name/extras, sorted constraints, extra gate)``.

    This intentionally supports the current package metadata, not arbitrary PEP 508
    expressions or direct URLs; it adds no undeclared packaging-library dependency.
    Any other shape fails closed with ``_ReleaseContractError``.
    """
    match = _REQUIREMENT.fullmatch(re.sub(r"\s+", "", value).lower().replace("'", '"'))
    if match is None:
        raise _ReleaseContractError(_ReleaseIssue.INVALID_PACKAGE_METADATA)
    name, constraints, marker = match.groups()
    return name, tuple(sorted(filter(None, constraints.split(",")))), marker or ""


def _runtime_metadata(content: bytes, package: _Package) -> None:
    """Verify runtime identity and dependency metadata, including optional-extra gates.

    The same contract applies to wheel metadata and sdist ``PKG-INFO``.

    Raises:
        ValueError: Project shape, identity, license, or dependency declarations differ.
        _ReleaseContractError: Built metadata violates the package contract.
    """
    project = require_object(
        tomllib.loads((package.root / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ],
        location="project",
    )
    metadata = BytesParser().parsebytes(content)
    fields = {
        "Name": package.name,
        "Version": package.version,
        "License-Expression": LICENSE,
        "Requires-Python": project.get("requires-python"),
    }
    if (
        project.get("name") != package.name
        or project.get("license") != LICENSE
        or any(metadata.get_all(key) != [value] for key, value in fields.items())
    ):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_PACKAGE_METADATA)
    extras = require_object(
        project.get("optional-dependencies", {}), location="optional-dependencies"
    )
    dependencies = require_str_list(
        project.get("dependencies", []), location="dependencies"
    )
    expected = [_requirement_key(item) for item in dependencies]
    for extra, requirements in extras.items():
        expected.extend(
            _requirement_key(f'{item}; extra == "{extra}"')
            for item in require_str_list(requirements, location="optional-dependencies")
        )
    if sorted(metadata.get_all("Provides-Extra", [])) != sorted(extras) or sorted(
        _requirement_key(item) for item in metadata.get_all("Requires-Dist", [])
    ) != sorted(expected):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_PACKAGE_METADATA)


def _wheel_installation_metadata(content: dict[str, bytes], prefix: str) -> None:
    """Validate pure-Python wheel tags and every RECORD hash against actual bytes.

    ``content`` holds all unique wheel entries; ``prefix`` identifies dist-info.
    Absent metadata propagates ``KeyError`` and malformed RECORD ``csv.Error``.

    Raises:
        _ReleaseContractError: Wheel installation metadata or RECORD entries differ.
    """
    wheel = BytesParser().parsebytes(content[f"{prefix}/WHEEL"])
    fields = {"Wheel-Version": "1.0", "Root-Is-Purelib": "true", "Tag": "py3-none-any"}
    record = f"{prefix}/RECORD"
    rows = list(csv.reader(StringIO(content[record].decode("utf-8")), strict=True))
    expected = [
        [
            name,
            "sha256="
            + urlsafe_b64encode(hashlib.sha256(data).digest())
            .rstrip(b"=")
            .decode("ascii"),
            str(len(data)),
        ]
        for name, data in content.items()
        if name != record
    ]
    expected.append([record, "", ""])
    if any(wheel.get_all(key) != [value] for key, value in fields.items()) or sorted(
        rows
    ) != sorted(expected):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_WHEEL)


def _runtime_content(
    content: dict[str, bytes], package: _Package, *, kind: _ArtifactKind
) -> None:
    """Apply one exact-source and metadata contract to both runtime archive formats.

    Remove only checked build metadata from ``content`` before comparing every
    remaining entry against canonical source bytes. Absent generated metadata
    propagates ``KeyError``.

    Raises:
        ValueError: Inventory, bytes, identity, or dependency metadata are invalid.
        _ReleaseContractError: Source inventory or bytes differ.
    """
    if kind == _ArtifactKind.WHEEL:
        prefix = f"{package.module}-{package.version}.dist-info"
        _wheel_installation_metadata(content, prefix)
        metadata = content.pop(f"{prefix}/METADATA")
        for name in ("WHEEL", "RECORD", "licenses/LICENSE"):
            content.pop(f"{prefix}/{name}")
        content.pop(f"{prefix}/entry_points.txt", None)
    else:
        metadata = content.pop("PKG-INFO")
    _runtime_metadata(metadata, package)
    source_prefix = (
        f"src/{package.module}" if kind == _ArtifactKind.SDIST else package.module
    )
    required = {
        f"{source_prefix}/{name}"
        for name in ("__init__.py", package.implementation, "py.typed")
    }
    if not required.issubset(content) or content != _runtime_source(package, kind=kind):
        raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_PACKAGE)


def _verify_source_bytes(
    archive: zipfile.ZipFile, names: list[str], trusted: dict[str, bytes]
) -> None:
    """Require unique entries whose bytes equal the independently composed source.

    Args:
        archive (zipfile.ZipFile): Open source archive.
        names (list[str]): Entry names in archive order, duplicates included.
        trusted (dict[str, bytes]): Expected path to file bytes.

    Raises:
        _ReleaseContractError: Entries repeat or differ from the source.
    """
    if len(names) != len(set(names)):
        raise _ReleaseContractError(_ReleaseIssue.DUPLICATE_SOURCE_ENTRIES)
    if set(names) != set(trusted) or any(
        archive.read(name) != expected for name, expected in trusted.items()
    ):
        raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_SOURCE)


def _unsafe_source_entry(
    archive: zipfile.ZipFile, name: str, digest: object, required: frozenset[str]
) -> bool:
    """Return whether one provenance entry escapes, is unexpected, or mismatches.

    Args:
        archive (zipfile.ZipFile): Open source archive.
        name (str): Entry path recorded in the provenance file list.
        digest (object): Recorded SHA-256 hex digest, as decoded.
        required (frozenset[str]): Top-level paths that are always allowed.

    Returns:
        bool: ``True`` when the entry must be rejected.
    """
    return (
        not is_relative_file_path(name)
        or (name not in required and not name.startswith(_SOURCE_PREFIXES))
        or hashlib.sha256(archive.read(name)).hexdigest() != digest
    )


def _source(
    path: Path, version: str, license_bytes: bytes, trusted: dict[str, bytes]
) -> None:
    """Require source bytes, exact inventory, and provenance in the selected ZIP.

    Args:
        path (Path): Source archive to inspect.
        version (str): Expected catalog and manifest version.
        license_bytes (bytes): Exact bytes of the repository ``LICENSE``.
        trusted (dict[str, bytes]): Independently composed path to file bytes.

    Raises:
        _ReleaseContractError: Provenance, inventory, or a path is invalid.
    """
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        _verify_source_bytes(archive, names, trusted)
        provenance: object = json.loads(archive.read("provenance.json"))
        if not is_json_object(provenance):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_PROVENANCE)
        source = provenance.get("source")
        hashes = provenance.get("files")
        if (
            not is_json_object(source)
            or source.get("catalog_version") != version
            or not is_json_object(hashes)
            or set(names) != set(hashes) | {"provenance.json"}
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SOURCE_INVENTORY)
        if not PACKAGE_REQUIRED_FILES.issubset(hashes) or not any(
            name.endswith(f"/{SKILL_FILE}") for name in names
        ):
            raise _ReleaseContractError(_ReleaseIssue.MISSING_CAPABILITIES)
        if any(
            _unsafe_source_entry(archive, name, digest, PACKAGE_REQUIRED_FILES)
            for name, digest in hashes.items()
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SOURCE_PATH)
        manifest: object = yaml.safe_load(archive.read("apm.yml"))
        if (
            not is_json_object(manifest)
            or manifest.get("version") != version
            or manifest.get("license") != LICENSE
            or archive.read("LICENSE") != license_bytes
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SOURCE_MANIFEST)


def _metadata_findings(root: Path, version: str, findings: list[str]) -> None:
    """Append catalog, manifest, and changelog drift from the package version.

    Args:
        root (Path): Repository root that holds the release metadata files.
        version (str): Package version every manifest must match.
        findings (list[str]): Collector that drift messages are appended to.
    """
    catalog: object = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    if not is_json_object(catalog) or catalog.get("version") != version:
        findings.append("catalog version does not match the package")
    for relative in ("apm.yml", *(f"packages/{name}/apm.yml" for name in _BUNDLES)):
        manifest: object = yaml.safe_load((root / relative).read_text(encoding="utf-8"))
        if (
            not is_json_object(manifest)
            or manifest.get("version") != version
            or manifest.get("license") != LICENSE
        ):
            findings.append(f"{relative}: version or license drift")
    if f"## {version} - " not in (root / "CHANGELOG.md").read_text(encoding="utf-8"):
        findings.append("changelog has no dated entry for the release version")


def _ignore_marker(folder: str, path: Path) -> bool:
    """Return whether a path is the owned distributions ignore marker.

    Args:
        folder (str): Build subfolder that holds ``path``.
        path (Path): Candidate entry in that folder.

    Returns:
        bool: ``True`` for a regular, non-linked ``.gitignore`` containing ``*`` in ``distributions``.
    """
    return (
        folder == "distributions"
        and path.name == ".gitignore"
        and not path.is_symlink()
        and path.is_file()
        and path.read_bytes() == b"*"
    )


def _artifact_inventory(root: Path) -> set[Path]:
    """List built artifacts, or nothing when either build folder is absent."""
    folders = ("distributions", "capabilities")
    if not all((root / "build" / folder).is_dir() for folder in folders):
        return set()
    return {
        path
        for folder in folders
        for path in (root / "build" / folder).iterdir()
        if not _ignore_marker(folder, path)
    }


def _validate_artifact(
    root: Path,
    path: Path,
    kind: _ArtifactKind,
    package: _Package,
) -> None:
    """Dispatch one artifact to the validator for its kind.

    The validator raises ``ValueError`` when the archive violates its release
    contract.

    Args:
        root (Path): Repository root used to read the expected project bytes and source.
        path (Path): Artifact to validate.
        kind (_ArtifactKind): Which validator applies.
        package (_Package): Expected independently versioned package.
    """
    license_bytes = (package.root / "LICENSE").read_bytes()
    match kind:
        case _ArtifactKind.WHEEL:
            _wheel(path, package, license_bytes)
        case _ArtifactKind.SDIST:
            _sdist(
                path,
                package,
                license_bytes,
                project_bytes=(package.root / "pyproject.toml").read_bytes(),
            )
        case _ArtifactKind.SOURCE:
            _source(path, package.version, license_bytes, _expected_source(root))
        case unreachable:
            assert_never(unreachable)


def _artifact_findings(
    root: Path,
    path: Path,
    kind: _ArtifactKind,
    package: _Package,
) -> list[str]:
    """Report a linked, irregular, or invalid artifact; absent ones are inventory.

    Args:
        root (Path): Repository root passed through to validation.
        path (Path): Artifact location, which may not exist.
        kind (_ArtifactKind): Which validator applies.
        package (_Package): Expected independently versioned package.

    Returns:
        list[str]: At most one finding describing why the artifact is rejected.
    """
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return [f"{kind}: artifact is not a regular owned file"]
    if not path.is_file():
        return []
    try:
        _validate_artifact(root, path, kind, package)
    except (
        OSError,
        ValueError,
        KeyError,
        tarfile.TarError,
        zipfile.BadZipFile,
        configparser.Error,
        csv.Error,
        yaml.YAMLError,
    ):
        return [
            f"{package.name} {kind if kind != _ArtifactKind.SOURCE else 'source archive'}: invalid content or license"
        ]
    return []


def _collect_findings(root: Path, *, tag: str | None, findings: list[str]) -> None:
    """Append every release finding; partial findings survive a later failure.

    Args:
        root (Path): Repository root to validate.
        tag (str | None): Release tag, or ``None`` for a local check.
        findings (list[str]): Collector that findings are appended to.
    """
    version = _version(root)
    if tag is not None and tag != f"v{version}":
        findings.append("release tag does not match the package version")
    if tag is not None:
        findings.extend(publication_blockers(root))
    _metadata_findings(root, version, findings)
    expected = _artifacts(root)
    if _artifact_inventory(root) != set(expected):
        findings.append(
            "release artifact inventory is incomplete or contains stale files"
        )
    for path, (kind, package) in expected.items():
        findings.extend(_artifact_findings(root, path, kind, package))


def check(root: Path, *, tag: str | None = None) -> list[str]:
    """Check local artifacts; tagged publication additionally requires approved owners.

    Args:
        root (Path): Repository root to validate.
        tag (str | None): Release tag, or ``None`` for a local check.

    Returns:
        list[str]: Human-readable findings; empty when the release is valid.
    """
    findings: list[str] = []
    try:
        _collect_findings(root, tag=tag, findings=findings)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        findings.append(
            "release source metadata cannot be validated: "
            f"{type(error).__name__}: {error}"
        )
    return findings


def write_checksums(root: Path, *, tag: str | None = None) -> Path:
    """Write deterministic basename-only checksums after artifact validation.

    Args:
        root (Path): Repository root whose built artifacts are validated.
        tag (str | None): Release tag, or ``None`` for a local check.

    Returns:
        Path: The written ``build/SHA256SUMS`` file.

    Raises:
        _ReleaseValidationError: Validation reported findings.
    """
    output = root / "build/SHA256SUMS"
    _verify_checksum_target(root, output)
    findings = check(root, tag=tag)
    if findings:
        raise _ReleaseValidationError(findings)
    artifacts = _artifacts(root)
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(artifacts, key=lambda item: item.name)
    ]
    _publish_checksums(root, output, "".join(lines).encode("ascii"))
    return output


def _verify_checksum_target(root: Path, output: Path) -> None:
    """Refuse linked parents, escaped paths, and irregular checksum targets.

    Args:
        root (Path): Repository root the build directory must sit directly under.
        output (Path): Checksum file destination.

    Raises:
        _ReleaseContractError: The checksum destination is not an owned file.
    """
    build = output.parent
    if any(path.is_symlink() or path.is_junction() for path in (build, *build.parents)):
        raise _ReleaseContractError(_ReleaseIssue.LINKED_BUILD_DIRECTORY)
    if (
        not build.is_dir()
        or build.resolve().parent != root.resolve()
        or output.is_symlink()
        or output.is_junction()
        or (output.exists() and (not output.is_file() or output.stat().st_nlink != 1))
    ):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_CHECKSUM_TARGET)


def _publish_checksums(root: Path, output: Path, content: bytes) -> None:
    """Replace checksums through a closed sibling file, cleaning up on failure.

    Args:
        root (Path): Repository root validated before and after the write.
        output (Path): Checksum file destination.
        content (bytes): Complete checksum file content.
    """
    _verify_checksum_target(root, output)
    replace_file(
        output, content, before_replace=lambda: _verify_checksum_target(root, output)
    )


def _verify_stage_target(root: Path, stage: Path, names: set[str]) -> None:
    """Refuse linked, irregular, or foreign staging locations before writing.

    Args:
        root (Path): Repository root that holds the ``build`` directory.
        stage (Path): Flat upload directory to prepare.
        names (set[str]): File names the staging directory may already contain.

    Raises:
        _ReleaseContractError: The staging location is linked or foreign.
    """
    if (root / "build").is_symlink() or (root / "build").is_junction():
        raise _ReleaseContractError(_ReleaseIssue.LINKED_BUILD_DIRECTORY)
    if (
        stage.is_symlink()
        or stage.is_junction()
        or (stage.exists() and not stage.is_dir())
    ):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_STAGING_DIRECTORY)
    if stage.is_dir() and any(
        path.name not in names or not path.is_file() or path.is_symlink()
        for path in stage.iterdir()
    ):
        raise _ReleaseContractError(_ReleaseIssue.UNKNOWN_STAGING_ENTRIES)


def _verify_staged_checksums(content: dict[str, bytes]) -> None:
    """Refuse content whose bytes moved after the checksums were written.

    A changed file raises ``_ReleaseContractError``.
    """
    for line in content["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if hashlib.sha256(content[name]).hexdigest() != digest:
            raise _ReleaseContractError(_ReleaseIssue.CHANGED_STAGING_SOURCE)


def _write_stage(stage: Path, content: dict[str, bytes]) -> None:
    """Write the flat upload layout and read every copy back.

    Args:
        stage (Path): Staging directory to create or reuse.
        content (dict[str, bytes]): File name to the exact bytes to stage.

    Raises:
        _ReleaseContractError: A staged copy differs from its source.
    """
    stage.mkdir(exist_ok=True)
    for name, data in content.items():
        (stage / name).write_bytes(data)
    if any((stage / name).read_bytes() != data for name, data in content.items()):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_STAGING_COPY)


def stage_release(root: Path, *, tag: str | None = None) -> Path:
    """Create the exact local flat layout and verify its copied checksum witness.

    Nothing is published remotely; validation runs once, inside checksum writing.

    Args:
        root (Path): Repository root whose built artifacts are staged.
        tag (str | None): Release tag, or ``None`` for a local check.

    Returns:
        Path: The verified ``build/release`` directory.
    """
    artifacts = _artifacts(root)
    stage = root / "build/release"
    _verify_stage_target(
        root, stage, {path.name for path in artifacts} | {"SHA256SUMS"}
    )
    checksums = write_checksums(root, tag=tag)
    content = {path.name: path.read_bytes() for path in artifacts}
    content["SHA256SUMS"] = checksums.read_bytes()
    # Never publish a copy whose bytes moved between validation and staging.
    _verify_staged_checksums(content)
    _write_stage(stage, content)
    return stage


def main() -> int:
    """Validate and stage local artifacts without publication; ``1`` on findings."""
    parser = argparse.ArgumentParser(description=__doc__)
    # An unset or empty RELEASE_TAG (untagged workflow input) means a local check.
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG", ""))
    args = parser.parse_args()
    try:
        stage = stage_release(_ROOT, tag=args.tag or None)
    except _ReleaseValidationError as error:
        findings = error.findings
    except _ReleaseContractError as error:
        findings = (str(error),)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        message = (
            "release source metadata cannot be validated: "
            f"{type(error).__name__}: {error}"
        )
        findings = (message,)
    else:
        sys.stdout.write(f"Release artifacts verified and staged: {stage}\n")
        return 0
    for finding in findings:
        sys.stderr.write(f"{finding}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
