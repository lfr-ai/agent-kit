"""Ledger-attested generated files, replaced atomically with rollback."""

from __future__ import annotations

from enum import StrEnum, unique
import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Final

from agent_kit.core.paths import is_relative_file_path
from agent_kit.core.primitives import JSON_INDENT

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

LEDGER_SCHEMA_VERSION: Final[int] = 1
_LEDGER_FIELDS = frozenset({"schema_version", "files"})


@unique
class OwnedPathIssue(StrEnum):
    """Closed set of owned-path containment violations."""

    UNSAFE = "owned path is not a relative path beneath an unlinked root"
    LINKED = "owned path contains a link or junction"
    ESCAPING = "owned path escapes its root"


class OwnedPathError(ValueError):
    """An owned path is unsafe, linked, or outside its root.

    Attributes:
        issue (OwnedPathIssue): Violated containment requirement.
    """

    def __init__(self, issue: OwnedPathIssue) -> None:
        """Retain ``issue`` and use its fixed diagnostic as the message."""
        self.issue = issue
        super().__init__(issue.value)


def owned_path(root: Path, relative: str) -> Path:
    """Resolve ``relative`` beneath ``root`` without crossing links.

    Args:
        root (Path): Ownership root that must not be a link or junction.
        relative (str): POSIX-style path beneath ``root`` without traversal.

    Returns:
        Path: Unresolved ``root``-joined path, safe to read, write, or delete.

    Raises:
        OwnedPathError: The path is unsafe, crosses a link, or escapes ``root``.
    """
    if root.is_symlink() or root.is_junction() or not is_relative_file_path(relative):
        raise OwnedPathError(OwnedPathIssue.UNSAFE)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise OwnedPathError(OwnedPathIssue.LINKED)
    if not current.resolve(strict=False).is_relative_to(root.resolve()):
        raise OwnedPathError(OwnedPathIssue.ESCAPING)
    return current


def ledger_hashes(files: Mapping[str, bytes]) -> dict[str, str]:
    """Return each file's SHA-256 hex digest, in ``files`` order."""
    return {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }


def ledger_bytes(files: Mapping[str, bytes]) -> bytes:
    """Return the UTF-8 JSON ownership ledger attesting ``files`` in their order."""
    ledger = {"schema_version": LEDGER_SCHEMA_VERSION, "files": ledger_hashes(files)}
    return (json.dumps(ledger, indent=JSON_INDENT) + "\n").encode("utf-8")


def ledger_entries(document: object) -> dict[str, object] | None:
    """Return the ``files`` of a current-schema ledger ``document``, else ``None``."""
    if not isinstance(document, dict) or set(document) != _LEDGER_FIELDS:
        return None
    files = document["files"]
    if document["schema_version"] != LEDGER_SCHEMA_VERSION or not isinstance(
        files, dict
    ):
        return None
    return files


def replace_file(
    path: Path, content: bytes, *, before_replace: Callable[[], None] | None = None
) -> None:
    """Replace ``path`` through a closed sibling file, never leaving a partial file.

    Args:
        path (Path): Destination whose parent directories are created if absent.
        content (bytes): Complete replacement content.
        before_replace (Callable[[], None] | None): Check run after staging and
            immediately before the rename; its exception aborts the replacement.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        if before_replace is not None:
            before_replace()
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_owned(
    output: Mapping[str, bytes],
    previous: Mapping[str, str],
    *,
    ledger: str,
    resolve: Callable[[str], Path],
) -> None:
    """Write changed ``output`` and its ledger, delete dropped files, or roll back.

    Unchanged files are not rewritten. Any failure restores every touched file
    to its prior bytes, or deletes it when it did not exist, then propagates.

    Args:
        output (Mapping[str, bytes]): Generated content by owned relative path,
            in ledger order.
        previous (Mapping[str, str]): Audited digests from the prior ledger.
        ledger (str): Owned relative path of the ownership ledger.
        resolve (Callable[[str], Path]): Contained resolution of an owned path.
    """
    planned = {**output, ledger: ledger_bytes(output)}
    before = {name: _read(resolve(name)) for name in planned.keys() | previous.keys()}
    changed = {
        name: content for name, content in planned.items() if before[name] != content
    }
    removed = previous.keys() - output.keys()
    complete = False
    try:
        for name, content in changed.items():
            replace_file(resolve(name), content)
        for name in removed:
            resolve(name).unlink(missing_ok=True)
        complete = True
    finally:
        if not complete:
            _restore({name: before[name] for name in changed.keys() | removed}, resolve)


def _read(path: Path) -> bytes | None:
    """Return the bytes of a regular file at ``path``, else ``None``."""
    return path.read_bytes() if path.is_file() else None


def _restore(before: dict[str, bytes | None], resolve: Callable[[str], Path]) -> None:
    """Return each file in ``before`` to its prior bytes or absence.

    Args:
        before (dict[str, bytes | None]): Prior bytes, or ``None`` when absent.
        resolve (Callable[[str], Path]): Contained resolution of an owned path.
    """
    for name, content in before.items():
        path = resolve(name)
        if content is None:
            path.unlink(missing_ok=True)
        else:
            replace_file(path, content)
