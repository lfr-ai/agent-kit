"""Audit locked dependencies before they are installed.

The audit reads ``uv.lock`` instead of the active environment, so it can run with
``uv run --no-project python`` before a changed lock installs new packages. It
rejects registry packages without wheels, because an install would then build
and execute their source distribution, and then runs ``uv audit`` (OSV
advisories plus archived, deprecated and quarantined project statuses) and fails
on any finding. ``uv audit`` does not compare lock hashes with the index; uv
verifies each artifact hash when ``uv sync --locked`` installs it. When the
project has a ``bun.lock``, ``bun audit`` checks it too.

This script is stdlib-only on purpose: it must run before ``uv sync`` installs the
project, so it cannot import ``agent_kit`` and keeps its own small decoding guards.
"""

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from typing import TypeGuard

_ROOT = Path(__file__).resolve().parents[1]
_UV_AUDIT_ARGUMENTS = (
    "audit",
    "--locked",
    "--preview-features",
    "audit-command,json-output",
    "--output-format",
    "json",
)


class InvalidLockMetadataError(ValueError):
    """The dependency inventory cannot be safely inspected."""

    def __init__(self) -> None:
        """Describe the required lock inventory without echoing input values."""
        super().__init__(
            "uv.lock: invalid package metadata; require a nonempty package list "
            "with valid names, versions, sources and wheel records"
        )


@dataclass(frozen=True, kw_only=True, slots=True)
class _AuditSummary:
    """Validated counts from uv's preview JSON report."""

    audited_packages: int
    vulnerabilities: int
    adverse_statuses: int


def source_only_packages(lock: Mapping[str, object]) -> list[str]:
    """Identify locked registry packages without wheels.

    Returns:
        list[str]: Sorted ``name==version`` strings, or an empty list if none
            are blocked.

    Raises:
        InvalidLockMetadataError: The package inventory is missing or malformed.
    """
    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        raise InvalidLockMetadataError
    blocked: list[str] = []
    for package in packages:
        if not _package_record(package):
            raise InvalidLockMetadataError
        source = package["source"]
        if (
            isinstance(source, dict)
            and "registry" in source
            and not package.get("wheels")
        ):
            blocked.append(f"{package.get('name')}=={package.get('version')}")
    return sorted(blocked)


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Report whether ``value`` is a dict whose keys are all strings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _nonempty_text(value: object) -> bool:
    """Report whether ``value`` is a string with a non-whitespace character."""
    return isinstance(value, str) and bool(value.strip())


def _package_record(value: object) -> TypeGuard[dict[str, object]]:
    """Report whether ``value`` is a lock package with name, version, source and wheels."""
    if not _mapping(value) or not all(
        _nonempty_text(value.get(field)) for field in ("name", "version")
    ):
        return False
    source = value.get("source")
    if not _mapping(source) or not source:
        return False
    if "registry" in source and not _nonempty_text(source["registry"]):
        return False
    return _wheel_records(value.get("wheels", []))


def _wheel_records(value: object) -> bool:
    """Report whether ``value`` is a list of wheel records that each have a URL."""
    return isinstance(value, list) and all(
        _mapping(wheel) and _nonempty_text(wheel.get("url")) for wheel in value
    )


def _count(value: object) -> int | None:
    """Return a nonnegative integer count, rejecting JSON booleans."""
    return value if type(value) is int and value >= 0 else None


def _summary(value: object) -> _AuditSummary | None:
    """Validate all counts in uv's summary, or return ``None``."""
    if not _mapping(value):
        return None
    packages = _count(value.get("audited_packages"))
    vulnerabilities = _count(value.get("vulnerabilities"))
    adverse = _count(value.get("adverse_statuses"))
    if packages is None or vulnerabilities is None or adverse is None:
        return None
    return _AuditSummary(
        audited_packages=packages,
        vulnerabilities=vulnerabilities,
        adverse_statuses=adverse,
    )


def _consistent_findings(report: dict[str, object], summary: _AuditSummary) -> bool:
    """Require finding arrays to agree with their counts; no finding is accepted.

    Args:
        report (dict[str, object]): Decoded ``uv audit`` report.
        summary (_AuditSummary): Validated counts from the report summary.

    Returns:
        bool: ``True`` when each finding list exists and matches its count.
    """
    return all(
        isinstance(findings, list) and len(findings) == count
        for findings, count in (
            (report.get("vulnerabilities"), summary.vulnerabilities),
            (report.get("adverse_statuses"), summary.adverse_statuses),
        )
    )


def _finding_counts(report: object) -> _AuditSummary | None:
    """Read a complete, consistent preview report; errors invalidate the report."""
    if not _mapping(report) or report.get("schema") != {"version": "preview"}:
        return None
    if "error" in report or "errors" in report:
        return None
    summary = _summary(report.get("summary"))
    if summary is None or not _consistent_findings(report, summary):
        return None
    return summary


def run(root: Path, *, ignore_until_fixed: tuple[str, ...] = ()) -> int:
    """Audit locks before installation; return zero only for clean, readable reports.

    Args:
        root (Path): Directory containing ``uv.lock`` and optional ``bun.lock``.
        ignore_until_fixed (tuple[str, ...]): Explicitly approved advisory IDs to ignore while unfixed.

    Returns:
        int: The failing tool's exit code, or one for invalid input or unavailable tools.
    """
    try:
        return _audit_locks(root, ignore_until_fixed=ignore_until_fixed)
    except (OSError, UnicodeError):
        sys.stderr.write(
            "Dependency audit cannot run audit tool or decode its output.\n"
        )
        return 1


def _audit_locks(root: Path, *, ignore_until_fixed: tuple[str, ...]) -> int:
    """Audit Python first, then the optional Bun lock, without syncing either.

    Args:
        root (Path): Directory containing ``uv.lock`` and optional ``bun.lock``.
        ignore_until_fixed (tuple[str, ...]): Approved advisory IDs to ignore while unfixed.

    Returns:
        int: Zero when every present lock passes, otherwise the failing exit code.
    """
    result = _audit_uv_lock(root, ignore_until_fixed=ignore_until_fixed)
    if result or not (root / "bun.lock").is_file():
        return result
    bun = shutil.which("bun")
    if bun is None:
        sys.stderr.write("Dependency audit requires bun to audit bun.lock.\n")
        return 1
    # Reads the lockfile, so it also runs before node_modules is installed.
    return subprocess.run(  # noqa: S603 - fixed bun arguments, no shell
        [bun, "audit"], cwd=root, check=False
    ).returncode


def _audit_uv_lock(root: Path, *, ignore_until_fixed: tuple[str, ...]) -> int:
    """Reject source-only packages in ``root``, then fail on any ``uv audit`` finding.

    Args:
        root (Path): Directory containing ``uv.lock``.
        ignore_until_fixed (tuple[str, ...]): Approved advisory IDs to ignore while unfixed.

    Returns:
        int: Zero when the lock is clean, otherwise a failing exit code.
    """
    try:
        lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
        blocked = source_only_packages(lock)
    except (
        OSError,
        UnicodeError,
        tomllib.TOMLDecodeError,
        InvalidLockMetadataError,
    ) as error:
        sys.stderr.write(f"Dependency audit cannot read uv.lock: {error}\n")
        return 1
    for package in blocked:
        sys.stderr.write(
            f"uv.lock: {package} has no wheel; installing it would run its build\n"
        )
    if blocked:
        return 1
    uv = shutil.which("uv")
    if uv is None:
        sys.stderr.write("Dependency audit requires uv on PATH.\n")
        return 1
    return _run_uv_audit(uv, root, ignore_until_fixed=ignore_until_fixed)


def _run_uv_audit(uv: str, root: Path, *, ignore_until_fixed: tuple[str, ...]) -> int:
    """Run ``uv audit`` in ``root`` and fail on a finding, error or unreadable report.

    Args:
        uv (str): Path of the ``uv`` launcher.
        root (Path): Directory containing ``uv.lock``.
        ignore_until_fixed (tuple[str, ...]): Approved advisory IDs to ignore while unfixed.

    Returns:
        int: Zero for a clean, readable report, otherwise a failing exit code.
    """
    exceptions = [
        argument
        for advisory in ignore_until_fixed
        for argument in ("--ignore-until-fixed", advisory)
    ]
    scan = subprocess.run(  # noqa: S603 - fixed uv arguments, no shell
        [uv, *_UV_AUDIT_ARGUMENTS, *exceptions],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        counts = _finding_counts(json.loads(scan.stdout))
    except json.JSONDecodeError:
        counts = None
    if counts is None:
        sys.stderr.write(
            "Dependency audit failed: invalid report "
            f"(uv audit exit {scan.returncode}).\n"
        )
        return scan.returncode or 1
    if scan.returncode or counts.vulnerabilities or counts.adverse_statuses:
        sys.stderr.write(scan.stdout)
        return scan.returncode or 1
    return 0


def main() -> int:
    """Audit repository locks and return the gate's exit code.

    Invalid arguments or a help request exit through argparse.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ignore-until-fixed",
        action="append",
        default=[],
        metavar="ID",
        help="Ignore an explicitly approved advisory only while no fix is available.",
    )
    args = parser.parse_args()
    return run(_ROOT, ignore_until_fixed=tuple(args.ignore_until_fixed))


if __name__ == "__main__":
    raise SystemExit(main())
