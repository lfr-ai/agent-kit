"""MSAL confidential Entra flows with an isolated token cache per session."""

import asyncio
from dataclasses import replace
import time

import msal

from platform_kit_runtime.core.identity.data import decode, encode, mapping, text
from platform_kit_runtime.core.identity.models import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
    IdentityConfig,
    InvalidCallbackError,
    Principal,
    ProviderLogin,
    ProviderTokens,
    UpstreamFailureError,
    finite_number,
)
from platform_kit_runtime.core.identity.ports import BearerValidator, ClientAssertion
from platform_kit_runtime.infrastructure.identity.msal_http import MSALHTTP

_GRAPH_SCOPES = ("User.Read",)
_TRANSIENT_OAUTH_ERRORS = frozenset({"server_error", "temporarily_unavailable"})
_REAUTH_OAUTH_ERRORS = frozenset({"invalid_grant", "invalid_request", "access_denied"})


class EntraIdentityProvider:
    """Keep MSAL flows and tokens server-side; validate ID signatures explicitly."""

    def __init__(
        self,
        *,
        config: IdentityConfig,
        http: MSALHTTP,
        assertion: ClientAssertion,
        validator: BearerValidator,
    ) -> None:
        """Bind fixed trust configuration and caller-owned ports.

        Args:
            config (IdentityConfig): Tenant, client and fixed redirect settings.
            http (MSALHTTP): Bounded synchronous HTTP bridge used in worker threads.
            assertion (ClientAssertion): Current signed client-assertion supplier.
            validator (BearerValidator): Independent ID-token signature validator.
        """
        self._config = config
        self._http = http
        self._assertion = assertion
        self._validator = validator

    def _client(
        self, cache: msal.SerializableTokenCache
    ) -> msal.ConfidentialClientApplication:
        return msal.ConfidentialClientApplication(
            self._config.client_id,
            client_credential={"client_assertion": self._assertion},
            authority=self._config.authority,
            token_cache=cache,
            http_client=self._http,
            instance_discovery=False,
            enable_pii_log=False,
        )

    def _begin(self) -> ProviderLogin:
        cache = msal.SerializableTokenCache()
        try:
            flow = mapping(
                self._client(cache).initiate_auth_code_flow(
                    scopes=list(_GRAPH_SCOPES),
                    redirect_uri=self._config.redirect_uri,
                    response_mode="query",
                )
            )
            return ProviderLogin(
                authorization_url=text(flow.get("auth_uri")),
                flow=encode(flow).decode(),
            )
        except (ValueError, KeyError) as error:
            raise UpstreamFailureError from error

    async def begin(self) -> ProviderLogin:
        """Begin an MSAL PKCE/state/nonce flow."""
        return await asyncio.to_thread(self._begin)

    def _complete(
        self, flow: str, state: str, code: str
    ) -> tuple[dict[str, object], str]:
        cache = msal.SerializableTokenCache()
        try:
            data = decode(flow)
            for name in ("state", "nonce", "code_verifier"):
                text(data.get(name))
            result = mapping(
                self._client(cache).acquire_token_by_auth_code_flow(
                    data,
                    {"state": state, "code": code},
                )
            )
        except (ValueError, RuntimeError, KeyError) as error:
            raise InvalidCallbackError from error
        _check_token_result(result, callback=True)
        return result, cache.serialize()

    async def complete(self, *, flow: str, state: str, code: str) -> ProviderTokens:
        """Redeem the bound code using SDK state/PKCE/nonce and signed ID validation.

        Args:
            flow (str): Private serialized MSAL login flow.
            state (str): Returned browser state.
            code (str): One-time authorization code.

        Returns:
            ProviderTokens: Verified principal and private token/cache state.

        Raises:
            InvalidCallbackError: State, PKCE, nonce, code or ID token is invalid.
        """
        result, cache = await asyncio.to_thread(self._complete, flow, state, code)
        try:
            principal = await self._validator.validate(
                token=text(result.get("id_token")), audience=self._config.client_id
            )
        except (AuthenticationRequiredError, ValueError) as error:
            raise InvalidCallbackError from error
        return _tokens(result=result, cache=cache, principal=principal)

    def _refresh(self, tokens: ProviderTokens) -> tuple[dict[str, object], str]:
        cache = msal.SerializableTokenCache()
        try:
            cache.deserialize(tokens.cache)
            client = self._client(cache)
            accounts = [
                account
                for account in client.get_accounts()
                if account.get("local_account_id") == tokens.principal.subject_id
                and account.get("realm") == tokens.principal.tenant_id
            ]
            if len(accounts) != 1:
                raise AuthenticationRequiredError
            result = mapping(
                client.acquire_token_silent_with_error(
                    list(_GRAPH_SCOPES), account=accounts[0], force_refresh=True
                )
            )
        except (ValueError, RuntimeError, KeyError) as error:
            raise AuthenticationRequiredError from error
        _check_token_result(result, callback=False)
        return result, cache.serialize()

    async def refresh(self, *, tokens: ProviderTokens) -> ProviderTokens:
        """Return refreshed tokens and cache for the session's tenant and account.

        Only the session's own account is refreshed; the application persists the
        result by compare-and-swap. Raises ``AuthenticationRequiredError`` when
        the grant is revoked or the identity changed.
        """
        result, cache = await asyncio.to_thread(self._refresh, tokens)
        if result.get("id_token"):
            principal = await self._validator.validate(
                token=text(result.get("id_token")), audience=self._config.client_id
            )
            if (principal.tenant_id, principal.subject_id) != (
                tokens.principal.tenant_id,
                tokens.principal.subject_id,
            ):
                raise AuthenticationRequiredError
            tokens = replace(tokens, principal=principal)
        return _tokens(result=result, cache=cache, principal=tokens.principal)


def _check_token_result(result: dict[str, object], *, callback: bool) -> None:
    error = result.get("error")
    if error is not None and not isinstance(error, str):
        raise UpstreamFailureError
    if error in _TRANSIENT_OAUTH_ERRORS:
        raise DependencyUnavailableError
    if error in _REAUTH_OAUTH_ERRORS:
        if callback:
            raise InvalidCallbackError
        raise AuthenticationRequiredError
    if error:
        raise UpstreamFailureError


def _tokens(
    *, result: dict[str, object], cache: str, principal: Principal
) -> ProviderTokens:
    try:
        duration = finite_number(result.get("expires_in"))
        if duration <= 0 or result.get("token_type") != "Bearer":
            raise UpstreamFailureError
        return ProviderTokens(
            principal=principal,
            cache=cache,
            access_token=text(result.get("access_token")),
            expires_at=time.time() + duration,
        )
    except ValueError as error:
        raise UpstreamFailureError from error
