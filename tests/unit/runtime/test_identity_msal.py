"""Exercise MSAL's real PKCE/state/nonce machinery through mock HTTP transports."""

import asyncio
import base64
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from tests.unit.runtime.test_identity_adapters import (
    TENANT,
    USER,
    claims,
    settings,
    signing_material,
)

from platform_kit_runtime.core.identity.models import (
    DependencyUnavailableError,
    InvalidCallbackError,
    ProviderLogin,
    UpstreamFailureError,
)
from platform_kit_runtime.core.identity.ports import ClientAssertion
from platform_kit_runtime.infrastructure.identity.http import HttpxIdentityTransport
from platform_kit_runtime.infrastructure.identity.jwt import EntraJWTValidator
from platform_kit_runtime.infrastructure.identity.msal import EntraIdentityProvider
from platform_kit_runtime.infrastructure.identity.msal_http import MSALHTTPTransport


def assertion() -> str:
    return "synthetic-client-assertion"


class MockAuthority:
    """HTTP-only mock; MSAL and JWT verification remain real library calls."""

    def __init__(self, *, failure: str = "") -> None:
        self.config = settings()
        self.key, self.jwk = signing_material()
        self.failure = failure
        self.parameters: dict[str, list[str]] = {}
        self.token_calls: list[dict[str, list[str]]] = []

    def authorize(self, url: str) -> None:
        self.parameters = parse_qs(urlsplit(url).query)
        assert self.parameters["code_challenge_method"] == ["S256"]
        assert self.parameters["redirect_uri"] == [self.config.redirect_uri]

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": f"{self.config.authority}/oauth2/v2.0/authorize",
                    "token_endpoint": f"{self.config.authority}/oauth2/v2.0/token",
                    "issuer": self.config.issuer,
                },
            )
        assert request.url.path.endswith("/oauth2/v2.0/token")
        values = parse_qs(request.content.decode())
        self.token_calls.append(values)
        assert values["client_assertion"][0].startswith(assertion())
        assert values["client_assertion_type"] == [
            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        ]
        assert "client_secret" not in values
        if values["grant_type"] == ["authorization_code"]:
            verifier = values["code_verifier"][0]
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            if challenge != self.parameters["code_challenge"][0]:
                return httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": "private PKCE detail",
                    },
                )
        return self.token_response()

    def token_response(self) -> httpx.Response:
        nonce = "wrong" if self.failure == "nonce" else self.parameters["nonce"][0]
        key = signing_material()[0] if self.failure == "signature" else self.key
        id_token = jwt.encode(
            claims() | {"nonce": nonce},
            key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )
        client_info = (
            base64.urlsafe_b64encode(json.dumps({"uid": USER, "utid": TENANT}).encode())
            .decode()
            .rstrip("=")
        )
        return httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "access_token": "server-only-access",
                "refresh_token": "server-only-refresh",
                "expires_in": 3600,
                "id_token": id_token,
                "client_info": client_info,
                "scope": "User.Read",
            },
        )


@asynccontextmanager
async def msal_provider(
    *, authority: MockAuthority, supplier: ClientAssertion = assertion
) -> AsyncGenerator[EntraIdentityProvider]:
    with httpx.Client(transport=httpx.MockTransport(authority.respond)) as sync_client:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"keys": [authority.jwk]})
            )
        ) as client:
            validator = EntraJWTValidator(
                config=authority.config, http=HttpxIdentityTransport(client=client)
            )
            yield EntraIdentityProvider(
                config=authority.config,
                http=MSALHTTPTransport(client=sync_client),
                assertion=supplier,
                validator=validator,
            )


async def _complete(
    *, provider: EntraIdentityProvider, authority: MockAuthority, login: ProviderLogin
) -> None:
    flow = json.loads(login.flow)
    if authority.failure == "pkce":
        flow["code_verifier"] = "x" * 43
    if authority.failure == "missing-pkce":
        del flow["code_verifier"]
    state = (
        "wrong" if authority.failure == "state" else authority.parameters["state"][0]
    )
    if authority.failure:
        with pytest.raises(InvalidCallbackError):
            await provider.complete(
                flow=json.dumps(flow), state=state, code="synthetic-code"
            )
        if authority.failure in {"state", "missing-pkce"}:
            assert not authority.token_calls
        return
    tokens = await provider.complete(
        flow=login.flow, state=state, code="synthetic-code"
    )
    assert tokens.principal.subject_id == USER
    # The dummy token exercises offline bearer-token redaction.
    assert tokens.access_token == "server-only-access"  # noqa: S105
    assert "server-only-refresh" in tokens.cache
    assert "server-only" not in repr(tokens)
    refreshed = await provider.refresh(tokens=tokens)
    assert refreshed.principal == tokens.principal
    assert authority.token_calls[-1]["grant_type"] == ["refresh_token"]


@pytest.mark.parametrize(
    "failure", ["", "state", "nonce", "pkce", "missing-pkce", "signature"]
)
def test_real_msal_flow_and_proof_failures(failure: str) -> None:
    async def verify() -> None:
        authority = MockAuthority(failure=failure)
        async with msal_provider(authority=authority) as provider:
            with pytest.warns(
                UserWarning, match="response_mode='form_post' is recommended"
            ):
                login = await provider.begin()
            authority.authorize(login.authorization_url)
            await _complete(provider=provider, authority=authority, login=login)

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("status", "body", "error_type"),
    [
        (503, b"private failure", DependencyUnavailableError),
        (429, b"private failure", DependencyUnavailableError),
        (302, b"redirect", UpstreamFailureError),
        (200, b"invalid-json", UpstreamFailureError),
    ],
)
def test_msal_http_failure_contract(
    status: int, body: bytes, error_type: type[Exception]
) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, content=body))
    ) as client:
        transport = MSALHTTPTransport(client=client)
        with pytest.raises(error_type) as caught:
            transport.get("https://login.microsoftonline.com/metadata")
        assert not str(caught.value)


class FederatedAssertion:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls = 0
        self.unavailable = unavailable

    def __call__(self) -> str:
        self.calls += 1
        if self.unavailable:
            cause = OSError("private managed identity credential diagnostic")
            raise DependencyUnavailableError from cause
        return f"synthetic-client-assertion-{self.calls}"


def test_keyless_assertion_is_acquired_lazily_and_again_on_refresh() -> None:
    async def verify() -> None:
        authority, supplier = MockAuthority(), FederatedAssertion()
        async with msal_provider(authority=authority, supplier=supplier) as provider:
            assert supplier.calls == 0
            with pytest.warns(
                UserWarning, match="response_mode='form_post' is recommended"
            ):
                login = await provider.begin()
            assert supplier.calls == 0
            authority.authorize(login.authorization_url)
            await _complete(provider=provider, authority=authority, login=login)
        assert supplier.calls == 2
        assert [call["client_assertion"] for call in authority.token_calls] == [
            ["synthetic-client-assertion-1"],
            ["synthetic-client-assertion-2"],
        ]

    asyncio.run(verify())


def test_keyless_assertion_acquisition_outage_propagates_safely() -> None:
    async def verify() -> None:
        authority, supplier = MockAuthority(), FederatedAssertion(unavailable=True)
        async with msal_provider(authority=authority, supplier=supplier) as provider:
            with pytest.warns(
                UserWarning, match="response_mode='form_post' is recommended"
            ):
                login = await provider.begin()
            authority.authorize(login.authorization_url)
            with pytest.raises(DependencyUnavailableError) as caught:
                await provider.complete(
                    flow=login.flow,
                    state=authority.parameters["state"][0],
                    code="synthetic-code",
                )
        assert supplier.calls == 1
        assert not authority.token_calls
        assert not str(caught.value)
        assert isinstance(caught.value.__cause__, OSError)

    asyncio.run(verify())
