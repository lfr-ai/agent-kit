"""Read-only session context-entry checks without executing project commands."""

from pathlib import Path

from agent_kit.core.errors import InputTypeError
from agent_kit.core.models import SessionContext

_ENTRY_FILES = ("AGENTS.md", "PROJECT.md", "llms.txt")


class InvalidContextDirectoryError(ValueError):
    """A session directory value is not an absolute path."""

    def __init__(self) -> None:
        """Describe the session directory requirement."""
        super().__init__("session context cwd must be an absolute directory")


class UnavailableContextWorkspaceError(ValueError):
    """A session workspace cannot be inspected."""

    def __init__(self) -> None:
        """Report the unavailable workspace without exposing its contents."""
        super().__init__("session context workspace is unavailable")


def session_context(payload: object) -> SessionContext:
    """Inspect only the existence of the approved workspace entry files."""
    if not isinstance(payload, dict):
        raise InputTypeError(location="session context input", expected="an object")
    supplied = payload.get("cwd")
    if supplied is None:
        root = Path.cwd()
    else:
        if not isinstance(supplied, str):
            raise InputTypeError(location="session context cwd", expected="a string")
        if not supplied or not Path(supplied).is_absolute():
            raise InvalidContextDirectoryError
        root = Path(supplied)
    if not root.is_dir():
        raise UnavailableContextWorkspaceError
    return SessionContext(
        workspace=str(root),
        missing=tuple(name for name in _ENTRY_FILES if not (root / name).is_file()),
    )
