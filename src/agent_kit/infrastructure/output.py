"""Atomic creation of first-party composed workspaces."""

from __future__ import annotations

import ctypes
from enum import StrEnum, unique
import logging
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import time
from typing import TYPE_CHECKING

from agent_kit.core.paths import is_relative_file_path

if TYPE_CHECKING:
    from agent_kit.core.models import CompositionPlan, PlannedFile

_LOGGER = logging.getLogger(__name__)
# Hidden sibling staging directories carry this marker so leftovers are attributable.
_STAGING_MARKER = ".agent-kit-"
# Linux renameat2(2): AT_FDCWD resolves relative paths from the working directory.
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
# Windows ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION and ERROR_LOCK_VIOLATION.
_WINDOWS_SHARING_CODES = frozenset({5, 32, 33})
_WINDOWS_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8)  # seconds; exponential backoff


@unique
class OutputPathIssue(StrEnum):
    """Closed set of publication path safety violations."""

    LINK = "output path contains a symlink or junction"
    UNSAFE_PLAN = "planned output contains an unsafe path"
    SOURCE_ANCESTOR = "output cannot be the source root or its ancestor"
    SOURCE_DIRECTORY = "output inside the source root must be beneath ROOT/build"
    SOURCE_OVERLAP = "output overlaps a source bundle"


class OutputPathError(ValueError):
    """A publication destination violates source or containment policy."""

    def __init__(self, issue: OutputPathIssue) -> None:
        """Identify the violated path invariant.

        Args:
            issue (OutputPathIssue): Failed output path safety requirement.
        """
        self.issue = issue
        super().__init__(issue.value)


class OutputExistsError(FileExistsError):
    """Atomic publication refuses to replace an existing destination."""

    def __init__(self, path: Path) -> None:
        """Identify the existing output.

        Args:
            path (Path): Requested publication destination.
        """
        super().__init__(f"output already exists: {path}")


class OutputCollisionError(ValueError):
    """A plan contains case-insensitively colliding destinations."""

    def __init__(self, *, previous: str, relative: str) -> None:
        """Identify the pair of colliding paths.

        Args:
            previous (str): First destination.
            relative (str): Colliding destination.
        """
        super().__init__(
            f"case-insensitive output collision between '{previous}' and '{relative}'"
        )


@unique
class PublicationSupportIssue(StrEnum):
    """Platform capabilities required for no-replace directory publication."""

    PLATFORM = "atomic composition supports Windows and Linux"
    RENAMEAT2 = "atomic composition requires Linux renameat2"


class UnsupportedPublicationError(NotImplementedError):
    """The host cannot publish a directory without replacement."""

    def __init__(self, issue: PublicationSupportIssue) -> None:
        """Identify the missing platform capability.

        Args:
            issue (PublicationSupportIssue): Missing publication capability.
        """
        self.issue = issue
        super().__init__(issue.value)


def _publish_directory(stage: Path, output: Path) -> None:
    """Publish without replacing an existing directory on supported platforms.

    Args:
        stage (Path): Fully written staging directory.
        output (Path): Destination that must not exist.

    Raises:
        UnsupportedPublicationError: The platform lacks a no-replace rename.
        OSError: The no-replace rename fails.
    """
    if sys.platform == "win32":
        _publish_windows_directory(stage, output)
        return
    if sys.platform != "linux":
        raise UnsupportedPublicationError(PublicationSupportIssue.PLATFORM)
    # POSIX rename may replace an empty directory; Linux's no-replace flag does not.
    library = ctypes.CDLL(None, use_errno=True)
    try:
        operation = library.renameat2
    except AttributeError as error:
        raise UnsupportedPublicationError(PublicationSupportIssue.RENAMEAT2) from error
    operation.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    result = operation(
        _AT_FDCWD, os.fsencode(stage), _AT_FDCWD, os.fsencode(output), _RENAME_NOREPLACE
    )
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(output))


def _rename_once(stage: Path, output: Path, *, final_attempt: bool) -> bool:
    """Attempt one no-replace rename; ``False`` reports a transient sharing denial.

    Args:
        stage (Path): Fully written staging directory.
        output (Path): Destination that must not exist.
        final_attempt (bool): Whether a sharing denial is raised instead of retried.

    Returns:
        bool: ``True`` when the rename succeeded, ``False`` for a retryable denial.

    Raises:
        OutputExistsError: The output already exists.
        PermissionError: The rename is denied for a non-transient reason.
    """
    _require_unlinked_path(stage)
    _require_unlinked_path(output)
    if output.exists():
        raise OutputExistsError(output)
    try:
        stage.rename(output)
    except PermissionError as error:
        if output.exists():
            raise OutputExistsError(output) from error
        sharing_denial = getattr(error, "winerror", None) in _WINDOWS_SHARING_CODES
        if final_attempt or not sharing_denial:
            raise
        return False
    return True


def _publish_windows_directory(stage: Path, output: Path) -> None:
    """Retry short-lived sharing denials without replacement or path redirection.

    Args:
        stage (Path): Fully written staging directory.
        output (Path): Destination that must not exist.
    """
    for delay in _WINDOWS_RETRY_DELAYS:
        if _rename_once(stage, output, final_attempt=False):
            return
        _LOGGER.debug(
            "publication rename denied by a sharing lock; retry in %ss", delay
        )
        time.sleep(delay)
    _rename_once(stage, output, final_attempt=True)


def _require_unlinked_path(path: Path) -> None:
    """Reject a linked ``path`` or ancestor with ``OutputPathError`` before writing.

    Symlinks and junctions both count as links.
    """
    for current in (*reversed(path.parents), path):
        if current.is_symlink() or current.is_junction():
            raise OutputPathError(OutputPathIssue.LINK)


class OutputAdapter:
    """Materialize a pure composition plan without replacing existing output."""

    def __init__(self) -> None:
        """Create the stateless output adapter."""

    def write(self, plan: CompositionPlan, requested_output: Path) -> Path:
        """Write a validated plan through a sibling staging directory.

        Containment violations raise ``OutputPathError``, case-insensitive
        collisions ``OutputCollisionError``, and a host without no-replace rename
        ``UnsupportedPublicationError``; filesystem failures propagate.

        Args:
            plan (CompositionPlan): Files to publish, with source paths used to
                prevent writing into the source tree.
            requested_output (Path): New destination; relative paths and ``~``
                are expanded before containment checks.

        Returns:
            Path: Resolved absolute destination after no-replace publication.

        Raises:
            OutputExistsError: The output already exists.
        """
        absolute_output = requested_output.expanduser().absolute()
        _require_unlinked_path(absolute_output)
        output = absolute_output.resolve(strict=False)
        self._check_output_location(plan, output)
        if output.exists() or output.is_symlink():
            raise OutputExistsError(output)
        planned_files = self._validate_files(plan.files)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{output.name}{_STAGING_MARKER}", dir=output.parent
        ) as temporary:
            stage = Path(temporary)
            for relative, item in planned_files:
                destination = stage.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as stream:
                    stream.write(item.content)
            _publish_directory(stage, output)
        _LOGGER.info("published %d files to %s", len(planned_files), output)
        return output

    def _validate_files(
        self, files: tuple[PlannedFile, ...]
    ) -> tuple[tuple[PurePosixPath, PlannedFile], ...]:
        """Pair each planned file with its parsed relative path, in plan order.

        An unsafe path raises ``OutputPathError`` and two paths that differ only
        by case raise ``OutputCollisionError``.
        """
        validated: list[tuple[PurePosixPath, PlannedFile]] = []
        folded_paths: dict[str, str] = {}
        for item in files:
            if not is_relative_file_path(item.relative_path):
                raise OutputPathError(OutputPathIssue.UNSAFE_PLAN)
            relative = PurePosixPath(item.relative_path)
            key = relative.as_posix().casefold()
            if key in folded_paths:
                raise OutputCollisionError(
                    previous=folded_paths[key], relative=item.relative_path
                )
            folded_paths[key] = item.relative_path
            validated.append((relative, item))
        return tuple(validated)

    def _check_output_location(self, plan: CompositionPlan, output: Path) -> None:
        """Reject destinations that could overwrite source or its ancestors.

        Args:
            plan (CompositionPlan): Plan naming the source root and bundle paths.
            output (Path): Resolved destination.

        Raises:
            OutputPathError: The output overlaps the source tree.
        """
        root = plan.root.resolve(strict=False)
        if output == root or root.is_relative_to(output):
            raise OutputPathError(OutputPathIssue.SOURCE_ANCESTOR)
        build_root = root / "build"
        output_is_build = output == build_root or output.is_relative_to(build_root)
        if output.is_relative_to(root) and not output_is_build:
            raise OutputPathError(OutputPathIssue.SOURCE_DIRECTORY)
        for _name, relative in plan.source_paths:
            source_root = root.joinpath(*PurePosixPath(relative).parts).resolve(
                strict=False
            )
            overlaps = (
                output == source_root
                or output.is_relative_to(source_root)
                or source_root.is_relative_to(output)
            )
            if overlaps and not (source_root == root and output_is_build):
                raise OutputPathError(OutputPathIssue.SOURCE_OVERLAP)
