"""Bounded synchronous HTTPX bridge for MSAL, run only in worker threads."""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from http import HTTPMethod, HTTPStatus
from typing import Protocol

import httpx

from platform_kit_runtime.core.identity.data import decode
from platform_kit_runtime.core.identity.models import (
    MAX_JSON_BYTES,
    DependencyUnavailableError,
    UpstreamFailureError,
)
from platform_kit_runtime.infrastructure.identity.http import (
    IDENTITY_ENCODING,
    READ_CHUNK_BYTES,
)


class SyncHTTPClient(Protocol):
    """The synchronous HTTPX streaming surface used by MSAL's bridge."""

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        data: Mapping[str, str] | None,
    ) -> AbstractContextManager[httpx.Response]:
        """Open a synchronous streaming response.

        Args:
            method (str): Explicit HTTP method.
            url (str): Upstream URL.
            headers (Mapping[str, str]): Explicit per-request headers.
            params (Mapping[str, str] | None): Optional query parameters.
            data (Mapping[str, str] | None): Optional form fields.

        Returns:
            AbstractContextManager[httpx.Response]: Stream closed on context exit.

        Raises:
            httpx.HTTPError: Transport failure when entering or reading the stream.
        """
        ...


@dataclass(frozen=True, kw_only=True, slots=True)
class MSALResponse:
    """MSAL's minimal response interface, with a bounded private body.

    Attributes:
        status_code (int): Upstream HTTP status.
        headers (Mapping[str, str]): Upstream response headers.
        content (bytes): Bounded private body; omitted from repr.
    """

    status_code: int
    headers: Mapping[str, str]
    content: bytes = field(repr=False)

    @property
    def text(self) -> str:
        """Private UTF-8 response text for the SDK, never for logging."""
        return self.content.decode()

    def json(self) -> dict[str, object]:
        """Return the private JSON object; raise ``UpstreamFailureError`` otherwise."""
        try:
            return decode(self.content)
        except ValueError as error:
            raise UpstreamFailureError from error


class MSALHTTP(Protocol):
    """The supported MSAL get/post HTTP interface."""

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> MSALResponse:
        """Fetch bounded metadata.

        Args:
            url (str): Explicit metadata URL.
            params (Mapping[str, str] | None): Optional query parameters.
            headers (Mapping[str, str] | None): Optional per-request headers.

        Returns:
            MSALResponse: Bounded metadata response for the SDK.

        Raises:
            DependencyUnavailableError: Transport or upstream availability failure.
            UpstreamFailureError: Status, encoding, size or JSON is invalid.
        """
        ...

    def post(
        self,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> MSALResponse:
        """Submit a confidential token request.

        Args:
            url (str): Explicit token endpoint.
            data (Mapping[str, str] | None): Private form fields, including assertion.
            params (Mapping[str, str] | None): Optional query parameters.
            headers (Mapping[str, str] | None): Optional per-request headers.

        Returns:
            MSALResponse: Bounded private token response for the SDK.

        Raises:
            DependencyUnavailableError: Transport or upstream availability failure.
            UpstreamFailureError: Status, encoding, size or JSON is invalid.
        """
        ...


class MSALHTTPTransport:
    """Serve MSAL without requests defaults, redirects or unbounded token bodies."""

    def __init__(self, *, client: SyncHTTPClient) -> None:
        """Bind the caller-owned synchronous HTTP client.

        Args:
            client (SyncHTTPClient): Client with timeout, no redirects or ambient auth.
        """
        self._client = client

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> MSALResponse:
        """Fetch bounded metadata.

        Args:
            url (str): Explicit metadata URL.
            params (Mapping[str, str] | None): Optional query parameters.
            headers (Mapping[str, str] | None): Optional per-request headers.

        Returns:
            MSALResponse: Bounded JSON-object response for the SDK.
        """
        return self._request(
            HTTPMethod.GET, url, params=params, headers=headers, data=None
        )

    def post(
        self,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> MSALResponse:
        """Submit a confidential token request.

        Args:
            url (str): Explicit token endpoint.
            data (Mapping[str, str] | None): Private form fields, including assertion.
            params (Mapping[str, str] | None): Optional query parameters.
            headers (Mapping[str, str] | None): Optional per-request headers.

        Returns:
            MSALResponse: Bounded private JSON-object response for the SDK.
        """
        return self._request(
            HTTPMethod.POST, url, params=params, headers=headers, data=data
        )

    def _request(
        self,
        method: HTTPMethod,
        url: str,
        *,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        data: Mapping[str, str] | None,
    ) -> MSALResponse:
        try:
            request_headers = {
                **(headers or {}),
                "Accept-Encoding": IDENTITY_ENCODING,
            }
            with self._client.stream(
                method, url, params=params, headers=request_headers, data=data
            ) as response:
                _check_status(method=method, status=response.status_code)
                encoding = response.headers.get("Content-Encoding", IDENTITY_ENCODING)
                if encoding != IDENTITY_ENCODING:
                    raise UpstreamFailureError
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=READ_CHUNK_BYTES):
                    if len(content) + len(chunk) > MAX_JSON_BYTES:
                        raise UpstreamFailureError
                    content.extend(chunk)
                result = MSALResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content=bytes(content),
                )
                result.json()
                return result
        except httpx.HTTPError as error:
            raise DependencyUnavailableError from error


def _check_status(*, method: HTTPMethod, status: int) -> None:
    if (
        status == HTTPStatus.TOO_MANY_REQUESTS
        or status >= HTTPStatus.INTERNAL_SERVER_ERROR
    ):
        raise DependencyUnavailableError
    if HTTPStatus.MULTIPLE_CHOICES <= status < HTTPStatus.BAD_REQUEST or (
        method is HTTPMethod.GET and status != HTTPStatus.OK
    ):
        raise UpstreamFailureError
