"""Check or explicitly refresh this repository's selected native role projections."""

from __future__ import annotations

import argparse
from enum import Enum, unique
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Final

from agent_kit.application.selection import parse_selection
from agent_kit.composition.root import plan_composition
from agent_kit.core.errors import InputTypeError
from agent_kit.core.primitives import KIT_NAME_PATTERN, NativeRuntime
from agent_kit.infrastructure.catalog import FileCatalogAdapter
from agent_kit.infrastructure.owned_output import (
    LEDGER_SCHEMA_VERSION,
    OwnedPathError,
    OwnedPathIssue,
    ledger_entries,
    ledger_hashes,
    owned_path,
    publish_owned,
)

_ROOT = Path(__file__).resolve().parents[1]
_LOCK_PATH = ".agents/agentic-setup/native-lock.json"
_ROLE_PATHS = tuple(
    re.compile(
        re.escape(f"{runtime.agent_directory}/")
        + KIT_NAME_PATTERN
        + re.escape(runtime.agent_suffix)
    )
    for runtime in NativeRuntime
)
# Earlier ledgers attested workers under subagents/; those paths may only be removed.
_LEGACY_ROLE_PATHS = tuple(
    re.compile(
        re.escape(f"{runtime.agent_directory}/subagents/")
        + KIT_NAME_PATTERN
        + re.escape(runtime.agent_suffix)
    )
    for runtime in NativeRuntime
)
_DISCOVERY_ROOTS = {
    runtime.agent_directory: runtime.agent_suffix for runtime in NativeRuntime
}
AGENT_PREFIXES: Final[tuple[str, ...]] = tuple(
    f"{directory}/" for directory in _DISCOVERY_ROOTS
)


@unique
class _NativeRoleIssue(Enum):
    """Stable diagnostics for native projection ownership and source contracts."""

    PATH_NOT_CONTAINED = "native role path must be contained in an unlinked root"
    PATH_CONTAINS_LINK = "native role path contains a link or junction"
    PATH_ESCAPES_ROOT = "native role path escapes its ownership root"
    INVALID_SELECTION = "repository native selection is invalid"
    INVALID_LEDGER = "native role ledger is invalid"
    UNOWNED_LEDGER_PATH = "native role ledger contains an unowned path"
    INVALID_ROLE_PATH = "native role path must be a canonical runtime-specific filename"
    EDITED_ROLE = "native role was edited independently"
    EXISTING_UNOWNED_ROLE = "unowned native role already exists"
    LINKED_OUTPUT = "native output cannot be a symbolic link"


class _NativeRoleError(ValueError):
    """Report one native projection contract failure with optional role context."""

    def __init__(self, issue: _NativeRoleIssue, *, path: str | None = None) -> None:
        """Retain ``issue`` and optional ``path``; append the path to the diagnostic."""
        self.issue = issue
        self.path = path
        message = f"{issue.value}: {path}" if path is not None else issue.value
        super().__init__(message)


_PATH_ISSUES = {
    OwnedPathIssue.UNSAFE: _NativeRoleIssue.PATH_NOT_CONTAINED,
    OwnedPathIssue.LINKED: _NativeRoleIssue.PATH_CONTAINS_LINK,
    OwnedPathIssue.ESCAPING: _NativeRoleIssue.PATH_ESCAPES_ROOT,
}


def _owned_path(root: Path, relative: str) -> Path:
    """Resolve a role path beneath ``root``; violations raise ``_NativeRoleError``."""
    try:
        return owned_path(root, relative)
    except OwnedPathError as error:
        raise _NativeRoleError(_PATH_ISSUES[error.issue]) from error


def expected(root: Path) -> dict[str, bytes]:
    """Resolve the repository's own selection through the canonical catalog.

    Generated role content is keyed by repository-relative Copilot or Claude agent
    path; a malformed self-selection raises ``_NativeRoleError``.
    """
    try:
        selection = parse_selection(
            FileCatalogAdapter().load_selection(
                root / ".agents/agentic-setup/self.json"
            )
        )
    except (InputTypeError, ValueError) as error:
        raise _NativeRoleError(_NativeRoleIssue.INVALID_SELECTION) from error
    plan = plan_composition(
        root, selection.profile, selection.features, selection.runtimes
    )
    return {
        item.relative_path: item.content
        for item in plan.files
        if item.relative_path.startswith(AGENT_PREFIXES)
    }


def check(root: Path) -> list[str]:
    """Require generated role hashes and exact current source projection."""
    output = expected(root)
    ledger = json.loads(_owned_path(root, _LOCK_PATH).read_text(encoding="utf-8"))
    hashes = ledger_hashes(output)
    failures: list[str] = []
    if ledger != {"schema_version": LEDGER_SCHEMA_VERSION, "files": hashes}:
        failures.append("repository native role source/ownership ledger drifted")
    for name, data in output.items():
        path = _owned_path(root, name)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            failures.append(f"native role projection differs: {name}")
    discovered: set[str] = set()
    for directory, suffix in _DISCOVERY_ROOTS.items():
        discovered.update(_discovered_roles(root, directory, suffix))
    failures.extend(
        f"unexpected native role: {name}" for name in sorted(discovered - output.keys())
    )
    return failures


def _discovered_roles(root: Path, directory: str, suffix: str) -> set[str]:
    """Inventory only repository runtime role directories without following links.

    Args:
        root (Path): Repository ownership root used to validate every discovered path.
        directory (str): Root-relative runtime directory to search recursively.
        suffix (str): Filename ending identifying role files.
    """
    pending = [_owned_path(root, directory)]
    discovered: set[str] = set()
    while pending:
        parent = pending.pop()
        if not parent.exists():
            continue
        for entry in parent.iterdir():
            name = entry.relative_to(root).as_posix()
            path = _owned_path(root, name)
            if path.is_dir():
                pending.append(path)
            elif path.name.endswith(suffix):
                discovered.add(name)
    return discovered


def _is_projection_path(name: str, *, legacy: bool = False) -> bool:
    """Accept only canonical runtime filenames.

    Args:
        name (str): Repository-relative role path.
        legacy (bool): Whether previously attested ``subagents/`` paths also count.
    """
    patterns = (*_ROLE_PATHS, *_LEGACY_ROLE_PATHS) if legacy else _ROLE_PATHS
    return any(pattern.fullmatch(name) is not None for pattern in patterns)


def _previous_roles(root: Path) -> dict[str, str]:
    lock = _owned_path(root, _LOCK_PATH)
    if not lock.exists():
        return {}
    files = ledger_entries(json.loads(lock.read_text(encoding="utf-8")))
    if files is None:
        raise _NativeRoleError(_NativeRoleIssue.INVALID_LEDGER)
    hashes = {name: digest for name, digest in files.items() if isinstance(digest, str)}
    if len(hashes) != len(files):
        raise _NativeRoleError(_NativeRoleIssue.INVALID_LEDGER)
    return hashes


def _check_previous_roles(root: Path, previous: dict[str, str]) -> None:
    for name, digest in previous.items():
        if not _is_projection_path(name, legacy=True):
            raise _NativeRoleError(_NativeRoleIssue.UNOWNED_LEDGER_PATH, path=name)
        path = _owned_path(root, name)
        if path.exists() and (
            path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise _NativeRoleError(_NativeRoleIssue.EDITED_ROLE, path=name)


def _check_planned_roles(
    root: Path, output: dict[str, bytes], previous: dict[str, str]
) -> None:
    for name in output:
        if not _is_projection_path(name):
            raise _NativeRoleError(_NativeRoleIssue.INVALID_ROLE_PATH, path=name)
        path = _owned_path(root, name)
        if name not in previous and path.exists():
            raise _NativeRoleError(_NativeRoleIssue.EXISTING_UNOWNED_ROLE, path=name)
        if path.is_symlink():
            raise _NativeRoleError(_NativeRoleIssue.LINKED_OUTPUT)


def write(root: Path) -> None:
    """Refresh changed attested files; preserve independently edited output."""
    output = expected(root)
    previous = _previous_roles(root)
    _check_previous_roles(root, previous)
    _check_planned_roles(root, output, previous)
    publish_owned(
        output,
        previous,
        ledger=_LOCK_PATH,
        resolve=lambda name: _owned_path(root, name),
    )


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
        sys.stderr.write(f"{error}\n")
        return 1
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write("Selected repository native roles and ownership hashes passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
