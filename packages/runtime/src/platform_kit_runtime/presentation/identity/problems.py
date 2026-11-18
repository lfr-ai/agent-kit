"""Identity-only RFC 9457 mapping and a single redacted handling-boundary log."""

from enum import StrEnum, auto, unique
from http import HTTPStatus
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from platform_kit_runtime.core.identity.models import (
    AuthenticationRequiredError,
    AvatarMissingError,
    DependencyUnavailableError,
    IdentityError,
    InvalidCallbackError,
    PermissionDeniedError,
    UpstreamFailureError,
)
from platform_kit_runtime.presentation.problems import (
    BLANK_PROBLEM_TYPE,
    CACHE_CONTROL,
    NO_STORE,
    PROBLEM_MEDIA_TYPE,
)

# Retain the diagnostic logger name across internal module relocation.
_LOGGER = logging.getLogger("platform_kit_runtime.presentation.identity_problems")
_HANDLER_REGISTRATION_ERROR = (
    "Identity handlers must be registered before startup with "
    "install_identity_handlers(app=app)."
)


@unique
class IdentityProblemCode(StrEnum):
    """Stable identity wire errors."""

    INVALID_CALLBACK = auto()
    AUTHENTICATION_REQUIRED = auto()
    PERMISSION_DENIED = auto()
    UNAVAILABLE = "identity_unavailable"
    UPSTREAM_FAILURE = "identity_upstream_failure"
    AVATAR_MISSING = auto()
    INTERNAL = "identity_internal_error"


_ERRORS = {
    InvalidCallbackError: (
        HTTPStatus.BAD_REQUEST,
        IdentityProblemCode.INVALID_CALLBACK,
    ),
    AuthenticationRequiredError: (
        HTTPStatus.UNAUTHORIZED,
        IdentityProblemCode.AUTHENTICATION_REQUIRED,
    ),
    PermissionDeniedError: (
        HTTPStatus.FORBIDDEN,
        IdentityProblemCode.PERMISSION_DENIED,
    ),
    DependencyUnavailableError: (
        HTTPStatus.SERVICE_UNAVAILABLE,
        IdentityProblemCode.UNAVAILABLE,
    ),
    UpstreamFailureError: (
        HTTPStatus.BAD_GATEWAY,
        IdentityProblemCode.UPSTREAM_FAILURE,
    ),
    AvatarMissingError: (HTTPStatus.NOT_FOUND, IdentityProblemCode.AVATAR_MISSING),
}


def identity_problem(error: Exception) -> JSONResponse:
    """Return a non-cacheable RFC 9457 problem and emit one sanitized log event.

    Classify by exact error type, never its message; use a fresh UUID instance.
    """
    status, code = _ERRORS.get(
        type(error), (HTTPStatus.INTERNAL_SERVER_ERROR, IdentityProblemCode.INTERNAL)
    )
    instance = f"urn:uuid:{uuid4()}"
    _LOGGER.warning(
        "Identity request failed",
        extra={
            "event": "runtime.identity.problem",
            "http_status": status.value,
            "problem_code": code.value,
            "instance": instance,
        },
    )
    headers = {CACHE_CONTROL: NO_STORE, "Referrer-Policy": "no-referrer"}
    if status == HTTPStatus.UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        content={
            "type": BLANK_PROBLEM_TYPE,
            "title": status.phrase,
            "status": status.value,
            "detail": "The identity request could not be completed.",
            "code": code.value,
            "instance": instance,
        },
        status_code=status.value,
        headers=headers,
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def _identity_error(_request: Request, error: Exception) -> JSONResponse:
    return identity_problem(error)


def install_identity_handlers(*, app: FastAPI) -> None:
    """Register sanitized identity handling before middleware construction.

    Raises ``RuntimeError`` once startup or request handling has built the
    middleware stack, because adding handlers then would silently leave the
    active stack unchanged.
    """
    if app.middleware_stack is not None:
        raise RuntimeError(_HANDLER_REGISTRATION_ERROR)
    app.add_exception_handler(IdentityError, _identity_error)


def ensure_identity_handlers(*, app: FastAPI) -> None:
    """Install pre-start handlers or verify them before attaching lifespan routes.

    Raises ``RuntimeError`` when middleware exists without the pre-registered
    identity handler.
    """
    if app.middleware_stack is None:
        install_identity_handlers(app=app)
    elif app.exception_handlers.get(IdentityError) is not _identity_error:
        raise RuntimeError(_HANDLER_REGISTRATION_ERROR)
