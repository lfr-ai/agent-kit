"""Read-only session context-entry checks without executing project commands."""

from pathlib import Path
from typing import Final

from agent_kit.core.guards import require_object, require_text
from agent_kit.core.models import SessionContext

ENTRY_FILES: Final[tuple[str, ...]] = ("AGENTS.md", "PROJECT.md", "llms.txt")


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

    The workspace is ``payload["cwd"]``, or the current directory when it is
    omitted or ``None``; file contents are never read. Missing names follow
    ``AGENTS.md``, ``PROJECT.md``, ``llms.txt`` order and are empty when all exist.
    An empty or relative ``cwd`` raises ``InvalidContextDirectoryError``, and a
    workspace that is not a directory raises ``UnavailableContextWorkspaceError``.
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
        missing=tuple(name for name in ENTRY_FILES if not (root / name).is_file()),
    )
