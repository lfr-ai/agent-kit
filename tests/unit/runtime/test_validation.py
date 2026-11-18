from typing import Final

import pytest

from platform_kit_runtime.core.validation import (
    LOCALHOST,
    URLScheme,
    has_query_or_fragment,
    is_bounded_seconds,
    is_int_in_range,
    is_loopback_host,
    is_nonblank,
    is_openai_v1_deployment,
    is_service_endpoint,
)

pytestmark = pytest.mark.unit


class _Integer(int):
    pass


def test_url_schemes_are_lowercase_wire_values() -> None:
    assert tuple(URLScheme) == ("http", "https", "redis", "rediss")
    assert LOCALHOST == "localhost"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("text", True),
        (" padded ", True),
        ("", False),
        ("   ", False),
        ("line\nbreak", False),
        ("nul\x00", False),
        (7, False),
        (None, False),
    ],
)
def test_nonblank_requires_printable_text(value: object, expected: bool) -> None:
    assert is_nonblank(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, True),
        (5, True),
        (3, True),
        (0, False),
        (6, False),
        (True, False),
        pytest.param(_Integer(3), False, id="integer-subclass"),
        (3.0, False),
        pytest.param("3", False, id="numeric-string"),
        (None, False),
    ],
)
def test_int_in_range_accepts_only_exact_bounded_integers(
    value: object, expected: bool
) -> None:
    assert is_int_in_range(value, low=1, high=5) is expected


@pytest.mark.parametrize("value", [1, 0.5, 10, 10.0])
def test_bounded_seconds_accepts_positive_finite_durations(value: object) -> None:
    assert is_bounded_seconds(value, maximum=10)


@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, "1", None, float("inf"), float("nan"), 10**1000, 11],
)
def test_bounded_seconds_rejects_invalid_values(value: object) -> None:
    assert not is_bounded_seconds(value, maximum=10)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", True),
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("::1", True),
        ("LOCALHOST", False),
        ("localhost.example", False),
        ("10.0.0.1", False),
        ("example.net", False),
        ("", False),
        (None, False),
    ],
)
def test_loopback_host_requires_localhost_or_loopback_ip(
    host: str | None, expected: bool
) -> None:
    assert is_loopback_host(host) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.net/path", False),
        ("https://example.net?", True),
        ("https://example.net#", True),
        ("https://example.net/?a=1", True),
        ("https://example.net/#top", True),
    ],
)
def test_query_or_fragment_detects_empty_delimiters(url: str, expected: bool) -> None:
    assert has_query_or_fragment(url) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://search.example.net", True),
        ("https://search.example.net/base", True),
        ("https://search.example.net:443", True),
        ("https://search.example.net?", False),
        ("https://search.example.net#", False),
        ("https://search.example.net:0", False),
        ("https://search.example.net:99999", False),
        ("https://search.example.net:port", False),
        ("https://user@search.example.net", False),
        ("https://exam ple.net", False),
        ("https://example.net/\u2028", False),
        ("https://", False),
        ("http://search.example.net", False),
        ("http://localhost:4000", False),
        ("ftp://search.example.net", False),
        (" ", False),
        (None, False),
    ],
)
def test_service_endpoint_requires_plain_https(value: object, expected: bool) -> None:
    assert is_service_endpoint(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:4000", True),
        ("http://127.0.0.1:4000/v1", True),
        ("http://[::1]:4000", True),
        ("https://models.example.net", True),
        ("http://models.example.net", False),
        ("http://localhost:4000?debug", False),
        ("redis://localhost:6379", False),
    ],
)
def test_service_endpoint_allows_loopback_http_only_when_requested(
    value: str, expected: bool
) -> None:
    assert is_service_endpoint(value, allow_loopback_http=True) is expected


V1_BASE: Final[str] = "https://resource.openai.azure.com/openai/v1/"


@pytest.mark.parametrize(
    ("model", "api_base", "expected"),
    [
        ("openai/deployment", V1_BASE, True),
        ("openai/deployment", "https://hub.services.ai.azure.com/openai/v1/", True),
        ("azure/deployment", V1_BASE, False),
        ("openai/", V1_BASE, False),
        ("openai/ ", V1_BASE, False),
        (None, V1_BASE, False),
        ("openai/deployment", None, False),
        ("openai/deployment", "https://resource.openai.azure.com", False),
        ("openai/deployment", "https://resource.openai.azure.com/openai/v1", False),
        ("openai/deployment", "https://resource.openai.azure.com/OPENAI/V1/", False),
        ("openai/deployment", "http://localhost/openai/v1/", False),
        ("openai/deployment", f"{V1_BASE}?api-version=1", False),
    ],
)
def test_openai_v1_deployment_requires_named_deployment_on_https_v1(
    model: object, api_base: object, expected: bool
) -> None:
    assert is_openai_v1_deployment(model=model, api_base=api_base) is expected
