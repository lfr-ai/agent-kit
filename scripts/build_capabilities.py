"""Build a selected, licensed APM source archive without plugin conversion."""

import argparse
from enum import Enum
import json
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import zipfile

from agent_kit.composition.root import compose_workspace, verify_provenance

_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = _ROOT / "build" / "capabilities"
# Fixed ZIP metadata keeps archives byte-reproducible across hosts.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_ZIP_UNIX_SYSTEM = 3
_ZIP_FILE_MODE = stat.S_IFREG | 0o644
_ZIP_MODE_SHIFT = 16


class _ArchiveIssue(Enum):
    """Stable failures for the final licensed-archive contract."""

    MISSING_REQUIRED_ENTRIES = "archive is missing required source entries"
    NO_CAPABILITIES = "archive has no capabilities"


class _ArchiveContractError(ValueError):
    """Report one known source-archive completeness failure."""

    def __init__(self, issue: _ArchiveIssue) -> None:
        """Retain ``issue`` and use its fixed diagnostic as the message."""
        self.issue = issue
        super().__init__(issue.value)


def _compose(profile: str, features: list[str], *, package: Path) -> int:
    """Compose the selection into ``package`` and verify its provenance.

    Args:
        profile (str): Profile to compose.
        features (list[str]): Optional features to add to the profile.
        package (Path): Output directory for the composed package.

    Returns:
        int: Zero when composition and provenance verification both pass, otherwise the failing exit code.
    """
    try:
        compose_workspace(_ROOT, profile, tuple(features), (), package)
        report = verify_provenance(package)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"Source composition failed: {error}\n")
        return 1
    if report.valid:
        return 0
    for finding in report.findings:
        sys.stderr.write(f"{finding.path}: {finding.message} [{finding.code}]\n")
    return 1


def _write_entries(
    archive: zipfile.ZipFile, package: Path, relatives: list[str]
) -> None:
    """Write files with fixed metadata so archives are byte-reproducible.

    Args:
        archive (zipfile.ZipFile): Open archive to write into.
        package (Path): Composed package directory to read from.
        relatives (list[str]): Package-relative paths to add, in any order.
    """
    for relative in sorted(relatives):
        entry = zipfile.ZipInfo(relative, date_time=_ZIP_EPOCH)
        entry.create_system = _ZIP_UNIX_SYSTEM
        entry.external_attr = _ZIP_FILE_MODE << _ZIP_MODE_SHIFT
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, (package / relative).read_bytes())


def _verify_archive(output: Path) -> None:
    """Reject an archive that lacks required entries or any capability.

    Raises:
        _ArchiveContractError: Required entries or capabilities are missing.
    """
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    if not {"LICENSE", "apm.yml", "apm-policy.yml", "provenance.json"}.issubset(names):
        raise _ArchiveContractError(_ArchiveIssue.MISSING_REQUIRED_ENTRIES)
    if not any(name.endswith("/SKILL.md") for name in names):
        raise _ArchiveContractError(_ArchiveIssue.NO_CAPABILITIES)


def _archive(output: Path, package: Path, relatives: list[str]) -> None:
    """Create and verify a new archive, removing only a partial one we created.

    Args:
        output (Path): Archive to create; it must not already exist.
        package (Path): Composed package directory to read from.
        relatives (list[str]): Package-relative paths to add.
    """
    created = False
    completed = False
    try:
        with zipfile.ZipFile(
            output, mode="x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            created = True
            _write_entries(archive, package, relatives)
        _verify_archive(output)
        completed = True
    finally:
        if created and not completed:
            output.unlink(missing_ok=True)


def main() -> int:
    """Compose, verify, and archive first-party source with no existing overwrite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="fullstack")
    parser.add_argument("--feature", action="append", default=[])
    args = parser.parse_args()
    with TemporaryDirectory(prefix="agent-kit-source-") as temporary:
        package = Path(temporary) / "package"
        returncode = _compose(args.profile, args.feature, package=package)
        if returncode:
            return returncode
        provenance = json.loads(
            (package / "provenance.json").read_text(encoding="utf-8")
        )
        version = provenance["source"]["catalog_version"]
        suffix = "-".join([args.profile, *sorted(set(args.feature))])
        output = _OUTPUT / f"agent-kit-{suffix}-{version}.zip"
        _OUTPUT.mkdir(parents=True, exist_ok=True)
        _archive(output, package, [*provenance["files"], "provenance.json"])
    sys.stdout.write(f"Licensed APM source archive: {output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
