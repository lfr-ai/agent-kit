"""Check or explicitly refresh this repository's selected native role projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import NamedTemporaryFile

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.core.errors import InputTypeError
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_ROOT = Path(__file__).resolve().parents[1]
_LOCK_PATH = ".agents/agentic-setup/native-lock.json"


class _NativeRoleIssue(Enum):
    """Stable diagnostics for native projection ownership and source contracts."""

    PATH_NOT_CONTAINED = "native role path must be contained in an unlinked root"
    PATH_CONTAINS_LINK = "native role path contains a link or junction"
    PATH_ESCAPES_ROOT = "native role path escapes its ownership root"
    INVALID_SELECTION = "repository native selection is invalid"
    INVALID_LEDGER = "native role ledger is invalid"
    UNOWNED_LEDGER_PATH = "native role ledger contains an unowned path"
    EDITED_ROLE = "native role was edited independently"
    EXISTING_UNOWNED_ROLE = "unowned native role already exists"
    LINKED_OUTPUT = "native output cannot be a symbolic link"


class _NativeRoleError(ValueError):
    """Report one native projection contract failure with optional role context."""

    def __init__(self, issue: _NativeRoleIssue, *, path: str | None = None) -> None:
        self.issue = issue
        self.path = path
        message = f"{issue.value}: {path}" if path is not None else issue.value
        super().__init__(message)


def _owned_path(root: Path, relative: str) -> Path:
    """Reject linked parents and path escapes for reads, writes, deletions, and rollback."""
    parts = PurePosixPath(relative)
    if (
        root.is_symlink()
        or root.is_junction()
        or parts.is_absolute()
        or PureWindowsPath(relative).drive
        or "\\" in relative
        or ".." in parts.parts
    ):
        raise _NativeRoleError(_NativeRoleIssue.PATH_NOT_CONTAINED)
    current = root
    for part in parts.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise _NativeRoleError(_NativeRoleIssue.PATH_CONTAINS_LINK)
    if not current.resolve(strict=False).is_relative_to(root.resolve()):
        raise _NativeRoleError(_NativeRoleIssue.PATH_ESCAPES_ROOT)
    return current


def _replace(path: Path, content: bytes) -> None:
    """Replace one attested projection atomically without leaving a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=".role-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def expected(root: Path) -> dict[str, bytes]:
    """Resolve the repository's own selection through the canonical catalog."""
    config = json.loads(
        (root / ".agents/agentic-setup/self.json").read_text(encoding="utf-8")
    )
    if (
        not isinstance(config, dict)
        or set(config) != {"schema_version", "profile", "features", "runtimes"}
        or type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or not isinstance(config["profile"], str)
        or not isinstance(config["features"], list)
        or not all(isinstance(item, str) for item in config["features"])
        or not isinstance(config["runtimes"], list)
        or not all(isinstance(item, str) for item in config["runtimes"])
    ):
        raise _NativeRoleError(_NativeRoleIssue.INVALID_SELECTION)
    plan = CatalogService().compose(
        FileCatalogAdapter().load(root),
        config["profile"],
        tuple(config["features"]),
        tuple(config["runtimes"]),
    )
    return {
        item.relative_path: item.content
        for item in plan.files
        if item.relative_path.startswith((".github/agents/", ".claude/agents/"))
    }


def check(root: Path) -> list[str]:
    """Require generated role hashes and exact current source projection."""
    output = expected(root)
    ledger = json.loads(_owned_path(root, _LOCK_PATH).read_text(encoding="utf-8"))
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in output.items()}
    if ledger != {"schema_version": 1, "files": hashes}:
        return ["repository native role source/ownership ledger drifted"]
    failures: list[str] = []
    for name, data in output.items():
        path = _owned_path(root, name)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            failures.append(f"native role projection differs: {name}")
    return failures


def write(root: Path) -> None:  # noqa: C901, PLR0912
    """Refresh only attested role files; preserve any independently edited output."""
    output = expected(root)
    lock = _owned_path(root, _LOCK_PATH)
    previous: dict[str, str] = {}
    if lock.exists():
        ledger = json.loads(lock.read_text(encoding="utf-8"))
        if (
            not isinstance(ledger, dict)
            or set(ledger) != {"schema_version", "files"}
            or ledger.get("schema_version") != 1
            or not isinstance(ledger.get("files"), dict)
        ):
            raise _NativeRoleError(_NativeRoleIssue.INVALID_LEDGER)
        files = ledger["files"]
        if not all(
            isinstance(name, str) and isinstance(digest, str)
            for name, digest in files.items()
        ):
            raise _NativeRoleError(_NativeRoleIssue.INVALID_LEDGER)
        previous = files
    for name, digest in previous.items():
        parts = PurePosixPath(name)
        if (
            "\\" in name
            or ".." in parts.parts
            or not name.startswith(
                (
                    ".github/agents/kit-",
                    ".github/agents/subagents/kit-",
                    ".claude/agents/kit-",
                    ".claude/agents/subagents/kit-",
                )
            )
        ):
            raise _NativeRoleError(_NativeRoleIssue.UNOWNED_LEDGER_PATH)
        path = _owned_path(root, name)
        if path.exists() and (
            path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise _NativeRoleError(_NativeRoleIssue.EDITED_ROLE, path=name)
    for name, data in output.items():
        path = _owned_path(root, name)
        if name not in previous and path.exists() and path.read_bytes() != data:
            raise _NativeRoleError(_NativeRoleIssue.EXISTING_UNOWNED_ROLE, path=name)
        if path.is_symlink():
            raise _NativeRoleError(_NativeRoleIssue.LINKED_OUTPUT)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in output.items()}
    planned = {
        **output,
        _LOCK_PATH: (
            json.dumps({"schema_version": 1, "files": hashes}, indent=2) + "\n"
        ).encode("utf-8"),
    }
    touched = set(planned) | previous.keys()
    before = {
        name: _owned_path(root, name).read_bytes()
        if _owned_path(root, name).is_file()
        else None
        for name in touched
    }
    completed = False
    try:
        for name, data in planned.items():
            _replace(_owned_path(root, name), data)
        for name in previous.keys() - output.keys():
            _owned_path(root, name).unlink(missing_ok=True)
        completed = True
    finally:
        if not completed:
            for name, data in before.items():
                if data is None:
                    _owned_path(root, name).unlink(missing_ok=True)
                else:
                    _replace(_owned_path(root, name), data)


def main() -> int:
    """Default to read-only verification; refresh requires an explicit flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        if args.write:
            write(_ROOT)
        failures = check(_ROOT)
    except (OSError, ValueError, InputTypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("Selected repository native roles and ownership hashes passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
