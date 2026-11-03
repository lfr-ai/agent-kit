"""Read-only session context-entry checks without executing project commands."""

from pathlib import Path

from agent_kit.core.guards import require_object, require_text
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
    """Inspect only the existence of the approved workspace entry files.

    A payload or ``cwd`` of the wrong type raises ``InputTypeError``.

    Args:
        payload (object): Decoded hook input; an object with an optional ``cwd``.

    Returns:
        SessionContext: Workspace from ``payload["cwd"]``, or the process's
        current directory when omitted or ``None``. Missing filenames follow
        ``AGENTS.md``, ``PROJECT.md``, ``llms.txt`` order; empty if all exist.
        File contents are never read.

    Raises:
        InvalidContextDirectoryError: ``cwd`` is empty or not absolute.
        UnavailableContextWorkspaceError: The workspace is not a directory.
    """
    supplied = require_object(payload, location="session context input").get("cwd")
    if supplied is None:
        root = Path.cwd()
    else:
        text = require_text(supplied, location="session context cwd")
        if not text or not Path(text).is_absolute():
            raise InvalidContextDirectoryError
        root = Path(text)
    if not root.is_dir():
        raise UnavailableContextWorkspaceError
    return SessionContext(
        workspace=str(root),
        missing=tuple(name for name in _ENTRY_FILES if not (root / name).is_file()),
    )
