"""HTTPX transport with bounded bodies, no redirects and safe error translation."""

from contextlib import AbstractAsyncContextManager
from http import HTTPMethod
from typing import Final, Protocol

import httpx

from platform_kit_runtime.core.identity.models import (
    DependencyUnavailableError,
    UpstreamFailureError,
)
from platform_kit_runtime.core.identity.ports import IdentityHTTPResponse

READ_CHUNK_BYTES: Final[int] = 8192
# Content coding that requests and accepts only uncompressed bodies.
IDENTITY_ENCODING: Final[str] = "identity"


class HttpxClient(Protocol):
    """The HTTPX streaming surface used by this adapter."""

    def stream(
        self, method: str, url: str, *, headers: dict[str, str]
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Open a caller-owned streaming response.

        Args:
            method (str): Explicit HTTP method.
            url (str): Upstream URL.
            headers (dict[str, str]): Explicit per-request headers.

        Returns:
            AbstractAsyncContextManager[httpx.Response]: Stream closed on context exit.

        Raises:
            httpx.HTTPError: Transport failure when entering or reading the stream.
        """
        ...


class HttpxIdentityTransport:
    """Translate transport failures without logging request URLs or credentials."""

    def __init__(self, *, client: HttpxClient) -> None:
        """Bind the caller-owned bounded HTTP client.

        Args:
            client (HttpxClient): Client with timeouts, no redirects and no ambient auth.
        """
        self._client = client

    async def get(
        self, *, url: str, access_token: str | None, max_bytes: int
    ) -> IdentityHTTPResponse:
        """GET a fixed upstream URL with optional server-only bearer credentials.

        Args:
            url (str): Explicit upstream URL.
            access_token (str | None): Private bearer token, or no credential.
            max_bytes (int): Maximum permitted response body size.

        Returns:
            IdentityHTTPResponse: Upstream status, bounded bytes and media type.

        Raises:
            DependencyUnavailableError: A connection, timeout or protocol failure occurred.
            UpstreamFailureError: Content is compressed or exceeds the byte limit.
        """
        headers = {"Accept-Encoding": IDENTITY_ENCODING}
        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"
        try:
            async with self._client.stream(
                HTTPMethod.GET, url, headers=headers
            ) as response:
                encoding = response.headers.get("Content-Encoding", IDENTITY_ENCODING)
                if encoding != IDENTITY_ENCODING:
                    raise UpstreamFailureError
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=READ_CHUNK_BYTES):
                    if len(body) + len(chunk) > max_bytes:
                        raise UpstreamFailureError
                    body.extend(chunk)
                return IdentityHTTPResponse(
                    status=response.status_code,
                    content=bytes(body),
                    content_type=response.headers.get("Content-Type", "").split(";")[0],
                )
        except httpx.HTTPError as error:
            raise DependencyUnavailableError from error
