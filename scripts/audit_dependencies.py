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

_ROOT = Path(__file__).resolve().parents[1]


def source_only_packages(lock: Mapping[str, object]) -> list[str]:
    """Return registry packages that the lock can install only from source.

    Args:
        lock: Parsed ``uv.lock`` document.
    """
    packages = lock.get("package")
    if not isinstance(packages, list):
        return []
    blocked: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        source = package.get("source")
        if (
            isinstance(source, dict)
            and "registry" in source
            and not package.get("wheels")
        ):
            blocked.append(f"{package.get('name')}=={package.get('version')}")
    return sorted(blocked)


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
        print("Dependency audit requires bun to audit bun.lock.", file=sys.stderr)
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
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"Dependency audit cannot read uv.lock: {error}", file=sys.stderr)
        return 1
    blocked = source_only_packages(lock)
    for package in blocked:
        print(
            f"uv.lock: {package} has no wheel; installing it would run its build",
            file=sys.stderr,
        )
    if blocked:
        return 1
    uv = shutil.which("uv")
    if uv is None:
        print("Dependency audit requires uv on PATH.", file=sys.stderr)
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
            print("Dependency audit could not export uv.lock.", file=sys.stderr)
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
