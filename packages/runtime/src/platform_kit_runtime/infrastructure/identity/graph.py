"""Microsoft Graph's server-side, allowlisted profile and bounded photo adapter."""

from http import HTTPStatus

from platform_kit_runtime.core.identity.data import decode
from platform_kit_runtime.core.identity.models import (
    MAX_AVATAR_BYTES,
    MAX_JSON_BYTES,
    MAX_NAME_LENGTH,
    Avatar,
    ImageType,
    SafeProfile,
    UpstreamFailureError,
)
from platform_kit_runtime.core.identity.ports import IdentityHTTP
from platform_kit_runtime.infrastructure.identity.upstream import check_upstream_status

_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphAdapter:
    """Fetch only the delegated user's display name and supported photo."""

    def __init__(self, *, http: IdentityHTTP) -> None:
        """Bind a bounded transport for fixed Graph endpoints.

        Args:
            http (IdentityHTTP): Caller-owned bounded upstream GET transport.
        """
        self._http = http

    async def profile(self, *, access_token: str) -> SafeProfile:
        """Return only ``displayName``; never retain or expose raw Graph objects.

        Raises ``UpstreamFailureError`` for a malformed or out-of-bounds
        response.
        """
        response = await self._http.get(
            url=f"{_GRAPH_ROOT}/me?$select=displayName",
            access_token=access_token,
            max_bytes=MAX_JSON_BYTES,
        )
        check_upstream_status(response.status)
        try:
            name = decode(response.content).get("displayName")
            if name is not None and (
                not isinstance(name, str)
                or len(name) > MAX_NAME_LENGTH
                or not name.isprintable()
            ):
                raise UpstreamFailureError
            return SafeProfile(display_name=name)
        except ValueError as error:
            raise UpstreamFailureError from error

    async def avatar(self, *, access_token: str) -> Avatar | None:
        """Return a bounded PNG/JPEG, or ``None`` when Graph reports no photo (404).

        Raises ``UpstreamFailureError`` for an unsafe media type, signature or
        body.
        """
        response = await self._http.get(
            url=f"{_GRAPH_ROOT}/me/photo/$value",
            access_token=access_token,
            max_bytes=MAX_AVATAR_BYTES,
        )
        if response.status == HTTPStatus.NOT_FOUND:
            return None
        check_upstream_status(response.status)
        try:
            return Avatar(
                content=response.content, media_type=ImageType(response.content_type)
            )
        except ValueError as error:
            raise UpstreamFailureError from error
