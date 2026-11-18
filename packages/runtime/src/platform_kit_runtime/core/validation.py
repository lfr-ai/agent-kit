"""Shared predicates for explicit settings and URLs; standard library only."""

from enum import StrEnum, auto, unique
from ipaddress import ip_address
from math import isfinite
from typing import Final
from urllib.parse import urlsplit

LOCALHOST: Final[str] = "localhost"
_QUERY_DELIMITER = "?"
_FRAGMENT_DELIMITER = "#"
_OPENAI_PROVIDER_PREFIX = "openai/"
_OPENAI_V1_PATH = "/openai/v1/"


@unique
class URLScheme(StrEnum):
    """URL schemes that runtime settings accept."""

    HTTP = auto()
    HTTPS = auto()
    REDIS = auto()
    REDISS = auto()


def is_nonblank(value: object) -> bool:
    """Return whether ``value`` is printable text with a non-whitespace character."""
    return isinstance(value, str) and bool(value.strip()) and value.isprintable()


def is_int_in_range(value: object, *, low: int, high: int) -> bool:
    """Return whether ``value`` is an exact ``int`` within ``[low, high]``.

    Booleans and other ``int`` subclasses are rejected.

    Args:
        value (object): Candidate setting.
        low (int): Inclusive lower bound.
        high (int): Inclusive upper bound.

    Returns:
        bool: True when ``value`` is a plain integer in range.
    """
    return type(value) is int and low <= value <= high


def is_bounded_seconds(value: object, *, maximum: float) -> bool:
    """Return whether ``value`` is a finite positive non-boolean duration.

    Args:
        value (object): Candidate duration in seconds.
        maximum (float): Inclusive upper bound.

    Returns:
        bool: True when ``0 < value <= maximum``.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    # The range check runs first because isfinite cannot take huge integers.
    return 0 < value <= maximum and isfinite(value)


def is_loopback_host(host: str | None) -> bool:
    """Return whether ``host`` is ``localhost`` or a literal loopback IP address."""
    if host == LOCALHOST:
        return True
    try:
        return ip_address(host or "").is_loopback
    except ValueError:
        return False


def has_query_or_fragment(url: str) -> bool:
    """Return whether ``url`` has a query or fragment delimiter, even an empty one.

    ``urlsplit`` drops an empty ``?`` or ``#``, so the raw text is checked.
    """
    return _QUERY_DELIMITER in url or _FRAGMENT_DELIMITER in url


def is_service_endpoint(value: object, *, allow_loopback_http: bool = False) -> bool:
    """Return whether ``value`` is a plain HTTPS service URL.

    A plain URL has a host, no port ``0``, no user information, no query or
    fragment, and only printable characters without whitespace. A path is
    allowed.

    Args:
        value (object): Candidate endpoint.
        allow_loopback_http (bool): Also accept ``http`` on ``localhost`` or a
            literal loopback IP address, for local development.

    Returns:
        bool: True when the endpoint is safe to pass to an SDK.
    """
    if not is_nonblank(value) or not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = parsed.hostname
    plain = (
        bool(host)
        and port != 0
        and parsed.username is None
        and parsed.password is None
        and not has_query_or_fragment(value)
        and not any(character.isspace() for character in value)
    )
    if not plain:
        return False
    if parsed.scheme == URLScheme.HTTPS:
        return True
    return (
        allow_loopback_http
        and parsed.scheme == URLScheme.HTTP
        and is_loopback_host(host)
    )


def is_openai_v1_deployment(*, model: object, api_base: object) -> bool:
    """Return whether settings name a deployment on an HTTPS ``/openai/v1/`` base.

    Keyless Microsoft Entra calls through LiteLLM's ``openai/`` provider need
    this shape: the provider sends the token as a bearer header and no API
    version, which the Azure OpenAI v1 API accepts.

    Args:
        model (object): LiteLLM selector; must be ``openai/<deployment>`` with a
            non-blank deployment name.
        api_base (object): Endpoint; must be a plain HTTPS service URL whose
            path is exactly ``/openai/v1/``. Loopback HTTP is rejected.

    Returns:
        bool: True when both values have the required shape.
    """
    if not isinstance(model, str) or not model.startswith(_OPENAI_PROVIDER_PREFIX):
        return False
    deployment = model.removeprefix(_OPENAI_PROVIDER_PREFIX)
    if not deployment.strip() or not is_service_endpoint(api_base):
        return False
    return isinstance(api_base, str) and urlsplit(api_base).path == _OPENAI_V1_PATH
