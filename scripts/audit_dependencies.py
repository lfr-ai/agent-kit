"""Audit locked dependencies before they are installed.

The audit reads ``uv.lock`` instead of the active environment, so it can run with
``uv run --locked --no-sync`` before a changed lock installs new packages. It
rejects registry packages without wheels, because an install would then build
and execute their source distribution, and checks every hashed requirement from
the lock with ``pip-audit``. Its default PyPI service also validates the locked
hashes against the index, so a tampered lock entry fails the audit. When the
project has a ``bun.lock``, ``bun audit`` checks it too.
"""

from collections.abc import Mapping
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from typing import TypeGuard

_ROOT = Path(__file__).resolve().parents[1]


class InvalidLockMetadataError(ValueError):
    """The dependency inventory cannot be safely inspected."""

    def __init__(self) -> None:
        """Describe the required lock inventory without echoing input values."""
        super().__init__(
            "uv.lock: invalid package metadata; require a nonempty package list "
            "with valid names, versions, sources and wheel records"
        )


def source_only_packages(lock: Mapping[str, object]) -> list[str]:
    """Return registry packages that the lock can install only from source.

    Args:
        lock: Parsed ``uv.lock`` document.

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
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _package_record(value: object) -> TypeGuard[dict[str, object]]:
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
    return isinstance(value, list) and all(
        _mapping(wheel) and _nonempty_text(wheel.get("url")) for wheel in value
    )


def audit_command(requirements: Path, cache: Path) -> list[str]:
    """Build the fail-closed vulnerability audit command for hashed requirements.

    Args:
        requirements: Hashed requirements exported from the lock.
        cache: Private HTTP cache directory for this audit run.
    """
    return [
        sys.executable,
        "-m",
        "pip_audit",
        "--requirement",
        str(requirements),
        "--require-hashes",
        "--disable-pip",
        "--strict",
        "--progress-spinner",
        "off",
        "--cache-dir",
        str(cache),
    ]


def run(root: Path) -> int:
    """Audit one project's lockfiles and return a process exit code.

    Args:
        root: Project root containing ``uv.lock`` and optionally ``bun.lock``.
    """
    result = _audit_uv_lock(root)
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


def _audit_uv_lock(root: Path) -> int:
    """Reject source-only packages and audit hashed uv requirements.

    Args:
        root: Project root containing ``pyproject.toml`` and ``uv.lock``.
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
    with tempfile.TemporaryDirectory(prefix="agent-kit-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        export = subprocess.run(  # noqa: S603 - fixed uv arguments, no shell
            [
                uv,
                "export",
                "--locked",
                "--all-groups",
                "--no-emit-project",
                "--format",
                "requirements.txt",
                "--output-file",
                str(requirements),
                "--quiet",
            ],
            cwd=root,
            check=False,
        )
        if export.returncode:
            sys.stderr.write("Dependency audit could not export uv.lock.\n")
            return export.returncode
        return subprocess.run(  # noqa: S603 - fixed audit arguments, no shell
            audit_command(requirements, Path(directory) / "cache"),
            cwd=root,
            check=False,
        ).returncode


def main() -> int:
    """Audit this repository's locked dependencies."""
    return run(_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
