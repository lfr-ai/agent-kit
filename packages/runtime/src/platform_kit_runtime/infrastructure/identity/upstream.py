"""Shared Graph/JWKS status translation, independent of either SDK adapter."""

from http import HTTPStatus

from platform_kit_runtime.core.identity.models import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
    UpstreamFailureError,
)


def check_upstream_status(status: int) -> None:
    """Accept 200 and translate any other ``status`` without reflecting bodies.

    401 raises ``AuthenticationRequiredError``; 429 and 5xx raise
    ``DependencyUnavailableError``; anything else raises
    ``UpstreamFailureError``.
    """
    if status == HTTPStatus.UNAUTHORIZED:
        raise AuthenticationRequiredError
    if (
        status == HTTPStatus.TOO_MANY_REQUESTS
        or status >= HTTPStatus.INTERNAL_SERVER_ERROR
    ):
        raise DependencyUnavailableError
    if status != HTTPStatus.OK:
        raise UpstreamFailureError
