"""Opt-in browser BFF routes; only safe views and opaque cookies reach clients."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http import HTTPMethod, HTTPStatus

from fastapi import APIRouter, FastAPI, Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from platform_kit_runtime.core.identity.models import (
    LOGIN_TTL_SECONDS,
    MAX_TOKEN_BYTES,
    AuthenticationRequiredError,
    AvatarMissingError,
    DependencyUnavailableError,
    IdentityConfig,
    IdentityError,
    InvalidCallbackError,
)
from platform_kit_runtime.core.identity.ports import BrowserIdentity
from platform_kit_runtime.presentation.identity.problems import (
    ensure_identity_handlers,
    identity_problem,
)
from platform_kit_runtime.presentation.identity.security import (
    login_cookie,
    require_csrf,
    require_origin,
    session_cookie,
)

_PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


@asynccontextmanager
async def _route_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    ensure_identity_handlers(app=app)
    yield


class IdentityRoutes:
    """Presentation-only browser handlers over an application service."""

    def __init__(self, *, config: IdentityConfig, service: BrowserIdentity) -> None:
        """Bind fixed-origin policy and the injected identity service.

        Args:
            config (IdentityConfig): Fixed origin, cookie and TTL policy.
            service (BrowserIdentity): Browser use cases over private state.
        """
        self._config = config
        self._service = service

    def router(self) -> APIRouter:
        """Return a fresh router that verifies pre-registered handlers at startup.

        Missing handlers raise ``RuntimeError`` at startup, not during router
        construction.
        """
        router = APIRouter(lifespan=_route_lifespan)
        router.add_api_route("/auth/login", self.login, methods=[HTTPMethod.GET])
        router.add_api_route("/auth/callback", self.callback, methods=[HTTPMethod.GET])
        router.add_api_route("/auth/logout", self.logout, methods=[HTTPMethod.POST])
        router.add_api_route("/auth/me", self.me, methods=[HTTPMethod.GET])
        router.add_api_route("/auth/avatar", self.avatar, methods=[HTTPMethod.GET])
        return router

    def _set_cookie(
        self, response: Response, *, name: str, value: str, ttl: int
    ) -> None:
        response.set_cookie(
            key=name,
            value=value,
            max_age=ttl,
            path="/",
            secure=self._config.secure_cookies,
            httponly=True,
            samesite="lax",
        )

    def _clear_cookie(self, response: Response, *, name: str) -> None:
        response.delete_cookie(
            key=name,
            path="/",
            secure=self._config.secure_cookies,
            httponly=True,
            samesite="lax",
        )

    async def login(self, request: Request) -> Response:
        """Return a private 303 to the provider with an opaque login-binding cookie.

        The optional ``return_to`` query path must be safe; a duplicated or
        unsafe value raises ``InvalidCallbackError``.
        """
        destinations = request.query_params.getlist("return_to")
        if len(destinations) > 1:
            raise InvalidCallbackError
        login = await self._service.login(
            return_to=destinations[0] if destinations else "/"
        )
        response = RedirectResponse(
            login.authorization_url,
            status_code=HTTPStatus.SEE_OTHER,
            headers=_PRIVATE_HEADERS,
        )
        self._set_cookie(
            response,
            name=login_cookie(self._config),
            value=login.binding,
            ttl=LOGIN_TTL_SECONDS,
        )
        return response

    async def callback(self, request: Request) -> Response:
        """Consume exactly one code and state; clear the binding even on failure.

        Returns a 303 with a rotated session, or a sanitized identity problem.
        Malformed proof is consumed and handled locally as a 400; the
        login-binding cookie is cleared on every identity outcome.
        """
        try:
            try:
                state, code = _callback_fields(request)
            except InvalidCallbackError:
                await self._service.cancel_login(
                    binding=request.cookies.get(login_cookie(self._config))
                )
                raise
            result = await self._service.callback(
                binding=request.cookies.get(login_cookie(self._config)),
                state=state,
                code=code,
                previous=request.cookies.get(session_cookie(self._config)),
            )
            response = RedirectResponse(
                result.return_to,
                status_code=HTTPStatus.SEE_OTHER,
                headers=_PRIVATE_HEADERS,
            )
            self._set_cookie(
                response,
                name=session_cookie(self._config),
                value=result.session_id,
                ttl=self._config.session_ttl_seconds,
            )
        except IdentityError as error:
            response = identity_problem(error)
        self._clear_cookie(response, name=login_cookie(self._config))
        return response

    async def logout(self, request: Request) -> Response:
        """Validate origin/CSRF, delete local state, then clear cookies.

        Origin is checked before reading state; absent or incorrect origin/CSRF
        proof raises ``PermissionDeniedError``, and a missing local session
        raises ``AuthenticationRequiredError``. Returns an empty 204 after
        deletion; read or delete outages clear browser cookies and return a
        sanitized 503, never confirmed revocation. Actual deletion still
        requires CSRF. No Entra token refresh is needed.
        """
        require_origin(request=request, config=self._config)
        session_id = request.cookies.get(session_cookie(self._config))
        try:
            session = await self._service.session(session_id=session_id, refresh=False)
            require_csrf(request=request, session=session, config=self._config)
            if session_id is None:
                raise AuthenticationRequiredError
            await self._service.logout(session_id=session_id)
            response = Response(
                status_code=HTTPStatus.NO_CONTENT, headers=_PRIVATE_HEADERS
            )
        except DependencyUnavailableError as error:
            response = identity_problem(error)
        for name in (session_cookie(self._config), login_cookie(self._config)):
            self._clear_cookie(response, name=name)
        return response

    async def me(self, request: Request) -> Response:
        """Return private JSON with safe identity, profile and the CSRF proof.

        Invalid sessions raise ``AuthenticationRequiredError``; upstream/cache
        failures propagate as sanitized identity errors.
        """
        session = await self._service.session(
            session_id=request.cookies.get(session_cookie(self._config))
        )
        profile = await self._service.profile(session=session)
        principal = session.tokens.principal
        return JSONResponse(
            content={
                "identity": {
                    "tenant_id": principal.tenant_id,
                    "subject_id": principal.subject_id,
                },
                "profile": {"display_name": profile.display_name},
                "csrf_token": session.csrf_token,
            },
            headers=_PRIVATE_HEADERS,
        )

    async def avatar(self, request: Request) -> Response:
        """Return supported image bytes with no sniffing or browser cache.

        A missing photo raises ``AvatarMissingError``; invalid sessions and
        upstream/cache failures propagate as sanitized identity errors.
        """
        session = await self._service.session(
            session_id=request.cookies.get(session_cookie(self._config))
        )
        avatar = await self._service.avatar(session=session)
        if avatar is None:
            raise AvatarMissingError
        return Response(
            content=avatar.content,
            media_type=avatar.media_type,
            headers=_PRIVATE_HEADERS,
        )


def _callback_fields(request: Request) -> tuple[str, str]:
    fields = [request.query_params.getlist(name) for name in ("state", "code")]
    if request.query_params.get("error") or any(
        len(values) != 1 or not values[0] or len(values[0]) > MAX_TOKEN_BYTES
        for values in fields
    ):
        raise InvalidCallbackError
    return fields[0][0], fields[1][0]
