"""Content-free failure classification shared by retrieval adapters; stdlib only."""

from enum import StrEnum, auto, unique
from http import HTTPStatus

from platform_kit_runtime.core.retrieval.models import (
    RetrievalAuthenticationError,
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalUnavailableError,
)

_CONTENT_STATUSES = frozenset(
    {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    }
)
_RETRYABLE_STATUSES = frozenset(
    {HTTPStatus.REQUEST_TIMEOUT, HTTPStatus.TOO_MANY_REQUESTS}
)


@unique
class FailureKind(StrEnum):
    """Provider-neutral failure category used to pick a typed public error."""

    AUTHENTICATION = auto()
    CONFIGURATION = auto()
    CONTENT = auto()
    UNAVAILABLE = auto()
    PROTOCOL = auto()


def classify_status(status: object) -> FailureKind:
    """Map an HTTP status to a failure kind; non-integers are protocol failures."""
    if isinstance(status, bool) or not isinstance(status, int):
        return FailureKind.PROTOCOL
    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        return FailureKind.AUTHENTICATION
    if status in _RETRYABLE_STATUSES or status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return FailureKind.UNAVAILABLE
    if status in _CONTENT_STATUSES:
        return FailureKind.CONTENT
    if status >= HTTPStatus.BAD_REQUEST:
        return FailureKind.CONFIGURATION
    return FailureKind.PROTOCOL


_RETRIEVAL_FAILURES = {
    FailureKind.AUTHENTICATION: RetrievalAuthenticationError,
    FailureKind.CONFIGURATION: RetrievalConfigurationError,
    FailureKind.CONTENT: RetrievalConfigurationError,
    FailureKind.UNAVAILABLE: RetrievalUnavailableError,
    FailureKind.PROTOCOL: RetrievalProtocolError,
}


def retrieval_failure(kind: FailureKind) -> RetrievalError:
    """Return a new content-free retrieval error for ``kind``."""
    return _RETRIEVAL_FAILURES[kind]()
