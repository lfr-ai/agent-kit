"""Validate exact release artifacts and versions before producing checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import TypeGuard

import yaml

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from scripts.check_governance import publication_blockers

_ROOT = Path(__file__).resolve().parents[1]
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_BUNDLES = ("shared", "backend", "frontend", "iac", "workflows", "ai", "coordination")


class _ReleaseIssue(Enum):
    """Stable diagnostics for release metadata, archives, and staging."""

    INVALID_PROJECT_VERSION = "project version must be a numeric three-part release"
    INVALID_WHEEL = "wheel metadata or license does not match the release"
    UNSAFE_SDIST = "sdist contains unsafe members"
    INVALID_SDIST_LICENSE = "sdist license does not match"
    DUPLICATE_SOURCE_ENTRIES = "source archive has duplicate entries"
    UNTRUSTED_SOURCE = "source archive does not match independently composed source"
    INVALID_PROVENANCE = "source archive provenance is invalid"
    INVALID_SOURCE_INVENTORY = "source archive inventory or version is invalid"
    MISSING_CAPABILITIES = "source archive lacks licensed capabilities"
    INVALID_SOURCE_PATH = "source archive provenance or path is invalid"
    INVALID_SOURCE_MANIFEST = "source archive license or manifest is invalid"
    LINKED_BUILD_DIRECTORY = (
        "release staging must not traverse a linked build directory"
    )
    INVALID_STAGING_DIRECTORY = "release staging must be an owned regular directory"
    UNKNOWN_STAGING_ENTRIES = "release staging contains unknown or linked entries"
    CHANGED_STAGING_SOURCE = "release staging source changed during preparation"
    INVALID_STAGING_COPY = "release staging verification failed"


class _ReleaseContractError(ValueError):
    """Report one fixed release contract failure without ad-hoc messages."""

    def __init__(self, issue: _ReleaseIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


class _ReleaseValidationError(ValueError):
    """Preserve the complete validation findings when checksum creation is refused."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = tuple(findings)
        super().__init__("; ".join(findings))


def _expected_source(root: Path) -> dict[str, bytes]:
    """Independently compose expected release bytes from the checked-out canonical source."""
    plan = CatalogService().compose(
        FileCatalogAdapter().load(root), "fullstack", ("iac",), ()
    )
    return {item.relative_path: item.content for item in plan.files}


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Keep decoded metadata concrete at the artifact boundary."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _version(root: Path) -> str:
    """Read the package version rather than duplicating a release constant."""
    value = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version: object = value["project"]["version"]
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_PROJECT_VERSION)
    return version


def _artifacts(root: Path, version: str) -> dict[Path, str]:
    """Define the exact initial release products, not arbitrary matching globs."""
    return {
        root / f"build/distributions/agent_kit-{version}-py3-none-any.whl": "wheel",
        root / f"build/distributions/agent_kit-{version}.tar.gz": "sdist",
        root / f"build/capabilities/agent-kit-fullstack-iac-{version}.zip": "source",
    }


def _wheel(path: Path, version: str, license_bytes: bytes) -> None:
    """Inspect metadata and actual bundled license without installing the wheel."""
    with zipfile.ZipFile(path) as archive:
        prefix = f"agent_kit-{version}.dist-info"
        metadata = BytesParser().parsebytes(archive.read(f"{prefix}/METADATA"))
        if (
            metadata.get_all("Version") != [version]
            or metadata.get_all("Name") != ["agent-kit"]
            or metadata.get_all("License-Expression") != ["MIT"]
            or archive.read(f"{prefix}/licenses/LICENSE") != license_bytes
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_WHEEL)


def _sdist(path: Path, version: str, license_bytes: bytes) -> None:
    """Read the source license while rejecting linked or unsafe members."""
    with tarfile.open(path, mode="r:gz") as archive:
        for item in archive.getmembers():
            parts = PurePosixPath(item.name)
            if (
                parts.is_absolute()
                or ".." in parts.parts
                or "\\" in item.name
                or item.issym()
                or item.islnk()
                or (not item.isfile() and not item.isdir())
            ):
                raise _ReleaseContractError(_ReleaseIssue.UNSAFE_SDIST)
        stream = archive.extractfile(f"agent_kit-{version}/LICENSE")
        if stream is None or stream.read() != license_bytes:
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SDIST_LICENSE)


def _source(
    path: Path, version: str, license_bytes: bytes, trusted: dict[str, bytes]
) -> None:
    """Require source bytes, exact inventory, and provenance in the selected ZIP."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise _ReleaseContractError(_ReleaseIssue.DUPLICATE_SOURCE_ENTRIES)
        if set(names) != set(trusted) or any(
            archive.read(name) != expected for name, expected in trusted.items()
        ):
            raise _ReleaseContractError(_ReleaseIssue.UNTRUSTED_SOURCE)
        provenance: object = json.loads(archive.read("provenance.json"))
        if not _mapping(provenance):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_PROVENANCE)
        source = provenance.get("source")
        hashes = provenance.get("files")
        if (
            not _mapping(source)
            or source.get("catalog_version") != version
            or not _mapping(hashes)
            or set(names) != set(hashes) | {"provenance.json"}
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SOURCE_INVENTORY)
        required = {"LICENSE", "apm.yml", "apm-policy.yml"}
        if not required.issubset(hashes) or not any(
            name.endswith("/SKILL.md") for name in names
        ):
            raise _ReleaseContractError(_ReleaseIssue.MISSING_CAPABILITIES)
        for name, digest in hashes.items():
            relative = PurePosixPath(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in name
                or (
                    name not in required
                    and not name.startswith(
                        (".apm/", ".github/agents/", ".claude/agents/")
                    )
                )
                or hashlib.sha256(archive.read(name)).hexdigest() != digest
            ):
                raise _ReleaseContractError(_ReleaseIssue.INVALID_SOURCE_PATH)
        manifest: object = yaml.safe_load(archive.read("apm.yml"))
        if (
            not _mapping(manifest)
            or manifest.get("version") != version
            or manifest.get("license") != "MIT"
            or archive.read("LICENSE") != license_bytes
        ):
            raise _ReleaseContractError(_ReleaseIssue.INVALID_SOURCE_MANIFEST)


def check(root: Path, *, tag: str) -> list[str]:  # noqa: C901, PLR0912
    """Check local artifacts; tagged publication additionally requires approved owners."""
    findings: list[str] = []
    try:
        version = _version(root)
        license_bytes = (root / "LICENSE").read_bytes()
        if tag and tag != f"v{version}":
            findings.append("release tag does not match the package version")
        if tag:
            findings.extend(publication_blockers(root))
        catalog: object = json.loads(
            (root / "catalog.json").read_text(encoding="utf-8")
        )
        if not _mapping(catalog) or catalog.get("version") != version:
            findings.append("catalog version does not match the package")
        for relative in ("apm.yml", *(f"packages/{name}/apm.yml" for name in _BUNDLES)):
            manifest: object = yaml.safe_load(
                (root / relative).read_text(encoding="utf-8")
            )
            if (
                not _mapping(manifest)
                or manifest.get("version") != version
                or manifest.get("license") != "MIT"
            ):
                findings.append(f"{relative}: version or license drift")
        if f"## {version} - " not in (root / "CHANGELOG.md").read_text(
            encoding="utf-8"
        ):
            findings.append("changelog has no dated entry for the release version")
        expected = _artifacts(root, version)
        actual = (
            {
                path
                for folder in ("distributions", "capabilities")
                for path in (root / "build" / folder).iterdir()
                if not (
                    folder == "distributions"
                    and path.name == ".gitignore"
                    and not path.is_symlink()
                    and path.is_file()
                    and path.read_bytes() == b"*"
                )
            }
            if all(
                (root / "build" / folder).is_dir()
                for folder in ("distributions", "capabilities")
            )
            else set()
        )
        if actual != set(expected):
            findings.append(
                "release artifact inventory is incomplete or contains stale files"
            )
        for path, kind in expected.items():
            if path.is_symlink() or (path.exists() and not path.is_file()):
                findings.append(f"{kind}: artifact is not a regular owned file")
                continue
            if not path.is_file():
                continue
            try:
                if kind == "wheel":
                    _wheel(path, version, license_bytes)
                elif kind == "sdist":
                    _sdist(path, version, license_bytes)
                else:
                    _source(path, version, license_bytes, _expected_source(root))
            except (
                OSError,
                ValueError,
                KeyError,
                tarfile.TarError,
                zipfile.BadZipFile,
                yaml.YAMLError,
            ):
                findings.append(
                    f"{kind if kind != 'source' else 'source archive'}: invalid content or license"
                )
    except (OSError, ValueError, KeyError, yaml.YAMLError):
        findings.append("release source metadata cannot be validated")
    return findings


def write_checksums(root: Path) -> Path:
    """Write deterministic basename-only checksums after strict artifact validation."""
    findings = check(root, tag="")
    if findings:
        raise _ReleaseValidationError(findings)
    artifacts = _artifacts(root, _version(root))
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(artifacts, key=lambda item: item.name)
    ]
    output = root / "build/SHA256SUMS"
    output.write_bytes("".join(lines).encode("ascii"))
    return output


def stage_release(root: Path) -> Path:
    """Create the exact flat upload layout and verify its copied checksum witness."""
    artifacts = _artifacts(root, _version(root))
    stage = root / "build/release"
    if (root / "build").is_symlink() or (root / "build").is_junction():
        raise _ReleaseContractError(_ReleaseIssue.LINKED_BUILD_DIRECTORY)
    if (
        stage.is_symlink()
        or stage.is_junction()
        or (stage.exists() and not stage.is_dir())
    ):
        raise _ReleaseContractError(_ReleaseIssue.INVALID_STAGING_DIRECTORY)
    names = {path.name for path in artifacts} | {"SHA256SUMS"}
    if stage.is_dir() and any(
        path.name not in names or not path.is_file() or path.is_symlink()
        for path in stage.iterdir()
    ):
        raise _ReleaseContractError(_ReleaseIssue.UNKNOWN_STAGING_ENTRIES)
    checksums = write_checksums(root)
    content = {path.name: path.read_bytes() for path in artifacts}
    content["SHA256SUMS"] = checksums.read_bytes()
    # Never publish a copy whose bytes moved between validation and staging.
    for line in content["SHA256SUMS"].decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if hashlib.sha256(content[name]).hexdigest() != digest:
            raise _ReleaseContractError(_ReleaseIssue.CHANGED_STAGING_SOURCE)
    stage.mkdir(exist_ok=True)
    for name, data in content.items():
        (stage / name).write_bytes(data)
    for name, data in content.items():
        if (stage / name).read_bytes() != data:
            raise _ReleaseContractError(_ReleaseIssue.INVALID_STAGING_COPY)
    return stage


def main() -> int:
    """Fail invalid release preparation before artifacts can be uploaded."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG", ""))
    args = parser.parse_args()
    findings = check(_ROOT, tag=args.tag)
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        return 1
    print(f"Release artifacts verified and staged: {stage_release(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
