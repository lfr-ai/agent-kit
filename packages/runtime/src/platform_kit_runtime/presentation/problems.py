"""RFC 9457 error mapping and one privacy-safe diagnostic per handled error."""

from collections.abc import Mapping
from enum import StrEnum, auto, unique
from http import HTTPMethod, HTTPStatus
import logging
import re
from typing import Final, TypedDict
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from platform_kit_runtime.application.readiness import ReadinessUnavailableError

PROBLEM_MEDIA_TYPE: Final[str] = "application/problem+json"
BLANK_PROBLEM_TYPE: Final[str] = "about:blank"
CACHE_CONTROL: Final[str] = "Cache-Control"
NO_STORE: Final[str] = "no-store"

_LOGGER = logging.getLogger(__name__)
# RFC 9110's unquoted token syntax, not an authentication credential.
_AUTH_ATOM = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
_AUTH_QUOTED = r'"(?:[\x20-\x21\x23-\x5b\x5d-\x7e]|\\[\x20-\x7e])*"'
_AUTH_PARAMETER = rf"{_AUTH_ATOM} *= *(?:{_AUTH_ATOM}|{_AUTH_QUOTED})"
_AUTH_CHALLENGE = re.compile(
    rf"(?P<scheme>Basic|Bearer)(?: +{_AUTH_PARAMETER}(?: *, *{_AUTH_PARAMETER})*)?",
    re.IGNORECASE | re.ASCII,
)


@unique
class ProblemCode(StrEnum):
    """Stable client-facing categories; never derived from exception text."""

    NOT_READY = auto()
    INVALID_REQUEST = auto()
    NOT_FOUND = auto()
    METHOD_NOT_ALLOWED = auto()
    HTTP_ERROR = auto()
    INTERNAL_ERROR = auto()
    RATE_LIMITED = auto()


class ProblemDocument(TypedDict):
    """RFC 9457 wire fields plus the closed ``code`` extension."""

    type: str
    title: str
    status: int
    detail: str
    code: ProblemCode
    instance: str


def install_problem_handlers(*, app: FastAPI) -> None:
    """Register sanitized handlers on ``app``; all responses are non-cacheable.

    Validated ``Allow`` methods survive on 405. Recognized Basic/Bearer challenges
    on 401 are replaced with ``Basic realm="runtime"`` or ``Bearer``; supplied
    parameter values never survive. Bare Basic is repaired with the fixed realm.
    A missing, unsupported or malformed challenge becomes a generic 500, never
    a challenge-less 401. Header names and schemes are case-insensitive.
    Request data, validation details, exception text, causes and tracebacks are
    deliberately absent from both response bodies and runtime log records.
    Register before middleware construction.
    """
    app.add_exception_handler(ReadinessUnavailableError, _readiness_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)


async def _readiness_error(_request: Request, error: Exception) -> JSONResponse:
    """Expose only the safe readiness reason; unexpected handler types become 500."""
    if not isinstance(error, ReadinessUnavailableError):
        return problem_response(
            status=HTTPStatus.INTERNAL_SERVER_ERROR, code=ProblemCode.INTERNAL_ERROR
        )
    return problem_response(
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        code=ProblemCode.NOT_READY,
        failure_reason=error.reason,
    )


async def _validation_error(_request: Request, _error: Exception) -> JSONResponse:
    """Return a generic 422 without validation input, field locations or details."""
    return problem_response(
        status=HTTPStatus.UNPROCESSABLE_ENTITY, code=ProblemCode.INVALID_REQUEST
    )


async def _http_error(_request: Request, error: Exception) -> JSONResponse:
    """Map HTTP failures without exposing exception details or arbitrary headers.

    Normalize invalid statuses and promote a 401 without a safe challenge to 500.
    """
    if not isinstance(error, HTTPException):
        return problem_response(
            status=HTTPStatus.INTERNAL_SERVER_ERROR, code=ProblemCode.INTERNAL_ERROR
        )
    status = _error_status(status_code=error.status_code)
    headers = _safe_headers(error=error)
    if status == HTTPStatus.UNAUTHORIZED and "WWW-Authenticate" not in headers:
        status = HTTPStatus.INTERNAL_SERVER_ERROR
    code = {
        HTTPStatus.NOT_FOUND: ProblemCode.NOT_FOUND,
        HTTPStatus.METHOD_NOT_ALLOWED: ProblemCode.METHOD_NOT_ALLOWED,
    }.get(status, ProblemCode.HTTP_ERROR)
    return problem_response(status=status, code=code, headers=headers)


async def _unexpected_error(_request: Request, _error: Exception) -> JSONResponse:
    """Return a generic 500 without inspecting or logging the exception."""
    return problem_response(
        status=HTTPStatus.INTERNAL_SERVER_ERROR, code=ProblemCode.INTERNAL_ERROR
    )


def _error_status(*, status_code: int) -> HTTPStatus:
    """Normalize unknown and non-error HTTP statuses to 500."""
    try:
        status = HTTPStatus(status_code)
    except ValueError:
        return HTTPStatus.INTERNAL_SERVER_ERROR
    return (
        status if status >= HTTPStatus.BAD_REQUEST else HTTPStatus.INTERNAL_SERVER_ERROR
    )


def _safe_headers(*, error: HTTPException) -> Mapping[str, str]:
    """Keep only a repaired 401 challenge or validated 405 ``Allow`` methods.

    Drop malformed values and all exception-supplied headers on other statuses.
    """
    if not error.headers:
        return {}
    if error.status_code == HTTPStatus.UNAUTHORIZED:
        return _challenge_header(headers=error.headers)
    if error.status_code != HTTPStatus.METHOD_NOT_ALLOWED:
        return {}
    value = _header_value(headers=error.headers, name="allow")
    if value is None:
        return {}
    methods = tuple(method.strip() for method in value.split(","))
    if not all(method in HTTPMethod for method in methods):
        return {}
    return {"Allow": ", ".join(methods)}


def _header_value(*, headers: Mapping[str, str], name: str) -> str | None:
    """Read one case-insensitive header only when its value is printable ASCII."""
    values = tuple(value for key, value in headers.items() if key.casefold() == name)
    if len(values) != 1:
        return None
    value = values[0]
    return value if value.isascii() and value.isprintable() else None


def _challenge_header(*, headers: Mapping[str, str]) -> Mapping[str, str]:
    """Replace one valid Basic/Bearer challenge with a fixed, value-free challenge.

    Return no header for duplicate, malformed or unsupported challenges; never
    echo supplied realms, scopes, errors, descriptions, URLs or tokens.
    """
    value = _header_value(headers=headers, name="www-authenticate")
    if value is None:
        return {}
    match = _AUTH_CHALLENGE.fullmatch(value.strip())
    if match is None:
        return {}
    # Validate challenge syntax, but never reflect realms, scopes, errors or tokens.
    challenge = (
        'Basic realm="runtime"' if match["scheme"].casefold() == "basic" else "Bearer"
    )
    return {"WWW-Authenticate": challenge}


def problem_response(
    *,
    status: HTTPStatus,
    code: ProblemCode,
    headers: Mapping[str, str] | None = None,
    failure_reason: str | None = None,
) -> JSONResponse:
    """Build a no-store RFC 9457 problem and log one event with the same UUID.

    Callers supply only validated headers and a safe failure category. This
    boundary never inspects request data or exception diagnostics.

    Args:
        status (HTTPStatus): Error status; 5xx other than not-ready logs at
            ``ERROR``, everything else at ``WARNING``.
        code (ProblemCode): Stable client-facing category.
        headers (Mapping[str, str] | None): Validated extra response headers.
        failure_reason (str | None): Safe, closed failure category for the log.

    Returns:
        JSONResponse: ``application/problem+json`` body with a fresh
            ``urn:uuid`` instance and ``Cache-Control: no-store``.
    """
    instance = f"urn:uuid:{uuid4()}"
    document: ProblemDocument = {
        "type": BLANK_PROBLEM_TYPE,
        "title": status.phrase,
        "status": status.value,
        "detail": (
            "The runtime is not ready."
            if code is ProblemCode.NOT_READY
            else "The request could not be completed."
        ),
        "code": code,
        "instance": instance,
    }
    level = (
        logging.ERROR
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR
        and code is not ProblemCode.NOT_READY
        else logging.WARNING
    )
    _LOGGER.log(
        level,
        "Runtime request failed",
        extra={
            "event": "runtime.problem",
            "http_status": status.value,
            "problem_code": code.value,
            "instance": instance,
            "failure_reason": failure_reason,
        },
    )
    return JSONResponse(
        content=document,
        status_code=status.value,
        media_type=PROBLEM_MEDIA_TYPE,
        headers={**(headers or {}), CACHE_CONTROL: NO_STORE},
    )
