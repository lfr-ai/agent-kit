"""Public lifespan/guard usage and fail-closed configuration without live resources."""

import asyncio

from fastapi import FastAPI
import httpx
import pytest
from redis.asyncio import Redis
from tests.unit.runtime.test_identity import config
from tests.unit.runtime.test_identity_msal import assertion

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.identity import (
    BearerGuard,
    open_entra_bearer,
    open_entra_identity,
)

pytestmark = pytest.mark.integration


def _check_route_paths(app: FastAPI) -> None:
    for name in ("login", "callback", "logout", "me", "avatar"):
        assert str(app.url_path_for(name)) == f"/auth/{name}"


def test_public_lifespans_create_close_clients_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_clients: list[httpx.AsyncClient] = []
    sync_clients: list[httpx.Client] = []
    original_async, original_sync = httpx.AsyncClient, httpx.Client

    def no_http(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"Unexpected network request to {request.url.host}")

    async def no_redis(_self: Redis, *args: object, **kwargs: object) -> object:
        pytest.fail("Unexpected Redis operation during composition")

    def async_client(**kwargs: object) -> httpx.AsyncClient:
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 10
        client = original_async(transport=httpx.MockTransport(no_http))
        async_clients.append(client)
        return client

    def sync_client(**kwargs: object) -> httpx.Client:
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 10
        client = original_sync(transport=httpx.MockTransport(no_http))
        sync_clients.append(client)
        return client

    async def verify() -> None:
        async with open_entra_identity(
            config=config(), redis_url="rediss://localhost:6379/0", assertion=assertion
        ) as identity:
            app = create_app(config=RuntimeConfig(), probes=())
            identity.install(app=app)
            _check_route_paths(app)
            async with original_async(
                transport=httpx.ASGITransport(app=app), base_url=config().origin
            ) as browser:
                assert (await browser.get("/health/live")).status_code == 200
                assert (await browser.get("/auth/logout")).status_code == 405
        async with open_entra_bearer(config=config()) as validator:
            guard = BearerGuard(
                config=config(),
                validator=validator,
                scopes=frozenset({"read"}),
                roles=frozenset(),
            )
            assert callable(guard)
            with pytest.raises(ValueError, match="permissions"):
                BearerGuard(
                    config=config(),
                    validator=validator,
                    scopes=frozenset(),
                    roles=frozenset(),
                )

    monkeypatch.setattr(httpx, "AsyncClient", async_client)
    monkeypatch.setattr(httpx, "Client", sync_client)
    monkeypatch.setattr(Redis, "execute_command", no_redis)
    asyncio.run(verify())
    assert len(async_clients) == 2
    assert len(sync_clients) == 1
    assert all(client.is_closed for client in async_clients)
    assert all(client.is_closed for client in sync_clients)


def test_public_lifespans_share_one_bounded_http_client_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options: list[dict[str, object]] = []
    original_async, original_sync = httpx.AsyncClient, httpx.Client

    def no_http(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"Unexpected network request to {request.url.host}")

    async def no_redis(_self: Redis, *args: object, **kwargs: object) -> object:
        pytest.fail("Unexpected Redis operation during composition")

    def async_client(**kwargs: object) -> httpx.AsyncClient:
        options.append(kwargs)
        return original_async(transport=httpx.MockTransport(no_http))

    def sync_client(**kwargs: object) -> httpx.Client:
        options.append(kwargs)
        return original_sync(transport=httpx.MockTransport(no_http))

    async def open_lifespans() -> None:
        async with open_entra_bearer(config=config()):
            pass
        async with open_entra_identity(
            config=config(), redis_url="rediss://localhost:6379/0", assertion=assertion
        ):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", async_client)
    monkeypatch.setattr(httpx, "Client", sync_client)
    monkeypatch.setattr(Redis, "execute_command", no_redis)
    asyncio.run(open_lifespans())
    expected = {
        "timeout": 10,
        "follow_redirects": False,
        "trust_env": False,
        "limits": httpx.Limits(max_connections=32),
    }
    assert options == [expected, expected, expected]


@pytest.mark.parametrize(
    "redis_url",
    [
        "redis://remote.test",
        "redis://localhost",
        "rediss://host?ssl_cert_reqs=none",
        "rediss://host?",
        "rediss://host:private-value",
        "https://host",
        "rediss://host/#fragment",
        "rediss://host#",
    ],
)
def test_public_redis_configuration_rejects_unsafe_transport(redis_url: str) -> None:
    async def verify() -> None:
        with pytest.raises(ValueError, match=r"[Ii]dentity.*Redis") as caught:
            async with open_entra_identity(
                config=config(), redis_url=redis_url, assertion=assertion
            ):
                pytest.fail("Unsafe configuration was accepted")
        assert "private-value" not in str(caught.value)

    asyncio.run(verify())


@pytest.mark.parametrize(
    "redis_url",
    [
        "rediss://",
        "redis://remote.test",
        "rediss://host\x7f",
        "redis://localhost/?db=1",
        "redis://localhost?",
        "redis://localhost#",
        "redis://[::1]#fragment",
        # A mistyped bytes URL must fail closed, not reach str-only checks.
        pytest.param(b"rediss://host", id="bytes-url"),
    ],
)
def test_loopback_mode_still_rejects_unsafe_redis_targets(redis_url: str) -> None:
    async def verify() -> None:
        with pytest.raises(
            ValueError,
            match=r"^Identity Redis requires TLS or explicit loopback development mode\.$",
        ):
            async with open_entra_identity(
                config=config(allow_insecure_loopback=True),
                redis_url=redis_url,
                assertion=assertion,
            ):
                pytest.fail("Unsafe configuration was accepted")

    asyncio.run(verify())


@pytest.mark.parametrize(
    "redis_url",
    ["redis://localhost:6379/0", "redis://127.0.0.1", "redis://[::1]:6379"],
)
def test_loopback_mode_permits_plain_loopback_redis(
    monkeypatch: pytest.MonkeyPatch, redis_url: str
) -> None:
    async def no_redis(_self: Redis, *args: object, **kwargs: object) -> object:
        pytest.fail("Unexpected Redis operation during composition")

    async def verify() -> None:
        async with open_entra_identity(
            config=config(allow_insecure_loopback=True),
            redis_url=redis_url,
            assertion=assertion,
        ) as identity:
            assert identity.config.allow_insecure_loopback is True

    monkeypatch.setattr(Redis, "execute_command", no_redis)
    asyncio.run(verify())
