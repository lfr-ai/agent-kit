"""Request correlation identifiers bound to the current execution context."""

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
import re
from typing import Final
from uuid import uuid4

REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
MAX_REQUEST_ID_LENGTH: Final[int] = 128

# Visible ASCII safe in headers and log lines: no spaces, quotes or separators.
_REQUEST_ID_PATTERN = re.compile(
    rf"[A-Za-z0-9._:+/=-]{{1,{MAX_REQUEST_ID_LENGTH}}}", re.ASCII
)
_REQUEST_ID = ContextVar[str | None]("platform_kit_runtime_request_id", default=None)


def resolve_request_id(*, values: Sequence[str]) -> str:
    """Return the single well-formed inbound ID, otherwise a fresh UUID4.

    Missing, repeated, oversized or malformed ``X-Request-ID`` values are
    replaced, never echoed.
    """
    if len(values) == 1 and _REQUEST_ID_PATTERN.fullmatch(values[0]):
        return values[0]
    return str(uuid4())


def current_request_id() -> str | None:
    """Return the request ID bound to the running request, if any."""
    return _REQUEST_ID.get()


@contextmanager
def bound_request_id(*, request_id: str) -> Generator[None]:
    """Bind ``request_id`` for the enclosed block and restore the prior value."""
    token = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)
