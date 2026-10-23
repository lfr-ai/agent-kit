"""Atomic creation of first-party composed workspaces."""

from __future__ import annotations

import ctypes
from enum import StrEnum, unique
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import tempfile
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_kit.core.models import CompositionPlan, PlannedFile

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_WINDOWS_SHARING_CODES = frozenset({5, 32, 33})
_WINDOWS_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8)


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
    """Publish without replacing an existing directory on supported platforms."""
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
    """Attempt one no-replace rename; ``False`` reports a transient sharing denial."""
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
    """Retry short-lived sharing denials without replacement or path redirection."""
    for delay in _WINDOWS_RETRY_DELAYS:
        if _rename_once(stage, output, final_attempt=False):
            return
        time.sleep(delay)
    _rename_once(stage, output, final_attempt=True)


def _require_unlinked_path(path: Path) -> None:
    """Reject symlinks and junctions before writing or retrying publication."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise OutputPathError(OutputPathIssue.LINK)


class OutputAdapter:
    """Materialize a pure composition plan without replacing existing output."""

    def __init__(self) -> None:
        """Create the stateless output adapter."""

    def write(self, plan: CompositionPlan, requested_output: Path) -> Path:
        """Write a validated plan through a sibling staging directory."""
        absolute_output = requested_output.expanduser().absolute()
        _require_unlinked_path(absolute_output)
        output = absolute_output.resolve(strict=False)
        self._check_output_location(plan, output)
        if output.exists() or output.is_symlink():
            raise OutputExistsError(output)
        planned_files = self._validate_files(plan.files)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{output.name}.agent-kit-", dir=output.parent
        ) as temporary:
            stage = Path(temporary)
            for relative, item in planned_files:
                destination = stage.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as stream:
                    stream.write(item.content)
            _publish_directory(stage, output)
        return output

    def _validate_files(
        self, files: tuple[PlannedFile, ...]
    ) -> tuple[tuple[PurePosixPath, PlannedFile], ...]:
        """Validate output containment and case-insensitive destination uniqueness."""
        validated: list[tuple[PurePosixPath, PlannedFile]] = []
        folded_paths: dict[str, str] = {}
        for item in files:
            relative = PurePosixPath(item.relative_path)
            windows = PureWindowsPath(item.relative_path)
            if (
                not relative.parts
                or relative.as_posix() != item.relative_path
                or relative.is_absolute()
                or windows.is_absolute()
                or windows.drive
                or "\\" in item.relative_path
                or any(part in {"..", ""} for part in relative.parts)
            ):
                raise OutputPathError(OutputPathIssue.UNSAFE_PLAN)
            key = relative.as_posix().casefold()
            if key in folded_paths:
                raise OutputCollisionError(
                    previous=folded_paths[key], relative=item.relative_path
                )
            folded_paths[key] = item.relative_path
            validated.append((relative, item))
        return tuple(validated)

    def _check_output_location(self, plan: CompositionPlan, output: Path) -> None:
        """Reject destinations that could overwrite source or its ancestors."""
        root = plan.root.resolve(strict=False)
        if output == root or root.is_relative_to(output):
            raise OutputPathError(OutputPathIssue.SOURCE_ANCESTOR)
        build_root = root / "build"
        output_is_build = output == build_root or output.is_relative_to(build_root)
        if output.is_relative_to(root) and not output_is_build:
            raise OutputPathError(OutputPathIssue.SOURCE_DIRECTORY)
        for _name, relative in plan.source_paths:
            source_root = (
                root
                if relative == "."
                else root.joinpath(*PurePosixPath(relative).parts)
            )
            source_root = source_root.resolve(strict=False)
            if (
                output == source_root
                or output.is_relative_to(source_root)
                or source_root.is_relative_to(output)
            ) and not (relative == "." and output_is_build):
                raise OutputPathError(OutputPathIssue.SOURCE_OVERLAP)
