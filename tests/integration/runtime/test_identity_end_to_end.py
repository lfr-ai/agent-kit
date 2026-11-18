"""Actual SDK/adapter BFF flow with all network transports replaced offline."""

import asyncio

import httpx
import pytest
from tests.unit.runtime.test_identity_adapters import AtomicRedis
from tests.unit.runtime.test_identity_msal import MockAuthority, assertion

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.identity import create_identity
from platform_kit_runtime.infrastructure.identity.graph import GraphAdapter
from platform_kit_runtime.infrastructure.identity.http import HttpxIdentityTransport
from platform_kit_runtime.infrastructure.identity.jwt import EntraJWTValidator
from platform_kit_runtime.infrastructure.identity.msal import EntraIdentityProvider
from platform_kit_runtime.infrastructure.identity.msal_http import MSALHTTPTransport
from platform_kit_runtime.infrastructure.identity.redis import RedisIdentityStore

pytestmark = pytest.mark.integration


def test_bff_real_sdks_and_atomic_store_over_mock_transports() -> None:
    async def verify() -> None:
        authority, redis = MockAuthority(), AtomicRedis()
        graph_calls: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.host == "login.microsoftonline.com":
                return httpx.Response(200, json={"keys": [authority.jwk]})
            assert request.url.host == "graph.microsoft.com"
            graph_calls.append(request.url.path)
            if request.url.path.endswith("/me"):
                return httpx.Response(
                    200,
                    json={"displayName": "Synthetic", "mail": "private@example.test"},
                )
            return httpx.Response(
                200,
                content=b"\xff\xd8\xffphoto",
                headers={"Content-Type": "image/jpeg"},
            )

        with httpx.Client(
            transport=httpx.MockTransport(authority.respond)
        ) as sync_client:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(respond)
            ) as outbound:
                transport = HttpxIdentityTransport(client=outbound)
                validator = EntraJWTValidator(config=authority.config, http=transport)
                provider = EntraIdentityProvider(
                    config=authority.config,
                    validator=validator,
                    assertion=assertion,
                    http=MSALHTTPTransport(client=sync_client),
                )
                identity = create_identity(
                    config=authority.config,
                    store=RedisIdentityStore(client=redis),
                    provider=provider,
                    graph=GraphAdapter(http=transport),
                    validator=validator,
                )
                app = create_app(config=RuntimeConfig(), probes=())
                identity.install(app=app)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=authority.config.origin,
                ) as browser:
                    await _browser_flow(browser=browser, authority=authority)
        assert graph_calls.count("/v1.0/me") == 1
        assert graph_calls.count("/v1.0/me/photo/$value") == 1
        assert "GETDEL" in redis.commands
        assert "DEL" in redis.commands

    asyncio.run(verify())


async def _browser_flow(
    *, browser: httpx.AsyncClient, authority: MockAuthority
) -> None:
    with pytest.warns(UserWarning, match="response_mode='form_post' is recommended"):
        login = await browser.get("/auth/login")
    assert login.status_code == 303
    authority.authorize(login.headers["location"])
    state = authority.parameters["state"][0]
    callback = await browser.get(
        "/auth/callback", params={"state": state, "code": "synthetic-code"}
    )
    assert callback.status_code == 303
    for _ in range(2):
        me = await browser.get("/auth/me")
        assert me.status_code == 200
        assert "private" not in me.text
        photo = await browser.get("/auth/avatar")
        assert photo.content == b"\xff\xd8\xffphoto"
        assert photo.headers["X-Content-Type-Options"] == "nosniff"
        assert "server-only" not in str(browser.cookies)
    logout = await browser.post(
        "/auth/logout",
        headers={
            "Origin": authority.config.origin,
            "X-CSRF-Token": me.json()["csrf_token"],
        },
    )
    assert logout.status_code == 204
    assert (await browser.get("/auth/me")).status_code == 401
