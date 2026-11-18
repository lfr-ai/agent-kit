"""Strict coverage JSON input, its stable diagnostic, and asset path safety."""

from __future__ import annotations

from enum import Enum, unique
from typing import TYPE_CHECKING

from agent_kit.core.errors import DuplicateJSONFieldError
from agent_kit.core.paths import is_relative_file_path
from agent_kit.infrastructure.documents import load_json

if TYPE_CHECKING:
    from pathlib import Path


@unique
class _CoverageIssue(Enum):
    """Stable diagnostics for invalid inventory structure."""

    DUPLICATE_KEY = "duplicate coverage or asset key"


class _CoverageInputError(ValueError):
    """Report a known duplicate-key error from coverage JSON."""

    def __init__(self, issue: _CoverageIssue) -> None:
        """Retain ``issue`` and use its fixed diagnostic as the message."""
        self.issue = issue
        super().__init__(issue.value)


def read_json(path: Path) -> object:
    """Read JSON at ``path``; a repeated key raises ``_CoverageInputError``."""
    try:
        return load_json(path.read_text(encoding="utf-8"))
    except DuplicateJSONFieldError as error:
        raise _CoverageInputError(_CoverageIssue.DUPLICATE_KEY) from error


def unsafe_asset(root: Path, relative: object) -> bool:
    """Reject non-string, absolute, drive, backslash, parent, missing, or escaping paths.

    Args:
        root (Path): Repository root the asset must stay inside.
        relative (object): Decoded asset reference.

    Returns:
        bool: ``True`` when the reference must be rejected.
    """
    return (
        not isinstance(relative, str)
        or not is_relative_file_path(relative)
        or not (root / relative).is_file()
        or not (root / relative).resolve().is_relative_to(root.resolve())
    )
