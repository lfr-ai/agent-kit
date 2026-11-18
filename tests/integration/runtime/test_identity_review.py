"""Regressions for independently reproduced lifecycle, logout and origin defects."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
import httpx
import pytest
from tests.integration.runtime.test_identity_http import Validator
from tests.unit.runtime.test_identity import Graph, MemoryStore, Provider, config

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.core.identity.models import DependencyUnavailableError
from platform_kit_runtime.identity import (
    IdentityRuntime,
    create_identity,
    install_identity_handlers,
)

pytestmark = pytest.mark.integration


def _runtime() -> IdentityRuntime:
    return create_identity(
        config=config(),
        store=MemoryStore(),
        provider=Provider(),
        graph=Graph(),
        validator=Validator(),
    )


async def _get_in_lifespan(*, app: FastAPI, path: str) -> httpx.Response:
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://app.test"
        ) as client,
    ):
        return await client.get(path)


def test_lifespan_routes_use_handlers_registered_before_startup() -> None:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        _runtime().install(app=app)
        yield

    app = create_app(config=RuntimeConfig(), probes=(), lifespan=lifespan)
    install_identity_handlers(app=app)
    response = asyncio.run(_get_in_lifespan(app=app, path="/auth/me"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "authentication_required"


def test_lifespan_install_without_prestart_handlers_fails_explicitly() -> None:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        _runtime().install(app=app)
        yield

    app = create_app(config=RuntimeConfig(), probes=(), lifespan=lifespan)
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()

    async def verify() -> None:
        with pytest.raises(RuntimeError, match="before startup"):
            async with app.router.lifespan_context(app):
                pytest.fail("Missing handler registration must fail before serving")

    asyncio.run(verify())


def test_direct_late_handler_registration_is_rejected() -> None:
    app = create_app(config=RuntimeConfig(), probes=())
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()

    async def verify() -> None:
        async with app.router.lifespan_context(app):
            with pytest.raises(RuntimeError, match="before startup"):
                install_identity_handlers(app=app)

    asyncio.run(verify())


def test_prestart_install_remains_convenient() -> None:
    app = create_app(config=RuntimeConfig(), probes=())
    _runtime().install(app=app)
    response = asyncio.run(_get_in_lifespan(app=app, path="/auth/me"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_raw_router_requires_prestart_handlers() -> None:
    app = create_app(config=RuntimeConfig(), probes=())
    app.include_router(_runtime().router())
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()

    async def verify() -> None:
        with pytest.raises(RuntimeError, match="before startup"):
            async with app.router.lifespan_context(app):
                pytest.fail(
                    "A raw identity router must reject missing handler registration"
                )

    asyncio.run(verify())


def test_raw_router_with_prestart_handlers_returns_401() -> None:
    app = create_app(config=RuntimeConfig(), probes=())
    install_identity_handlers(app=app)
    app.include_router(_runtime().router())
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()
    response = asyncio.run(_get_in_lifespan(app=app, path="/auth/me"))
    assert response.status_code == 401


class ReadOutageStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.unavailable = False
        self.reads = 0
        self.deletes = 0

    async def get(self, *, key: str) -> bytes | None:
        self.reads += 1
        if self.unavailable:
            raise DependencyUnavailableError
        return await super().get(key=key)

    async def delete(self, *, key: str) -> None:
        self.deletes += 1
        await super().delete(key=key)


def test_logout_read_outage_clears_cookies_and_never_deletes_without_csrf() -> None:
    async def verify() -> None:
        store = ReadOutageStore()
        app = create_app(config=RuntimeConfig(), probes=())
        create_identity(
            config=config(),
            store=store,
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        ).install(app=app)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://app.test"
        ) as browser:
            await browser.get("/auth/login")
            await browser.get("/auth/callback?state=valid-state&code=valid-code")
            assert browser.cookies.get("__Host-pk-session") is not None
            store.unavailable = True
            response = await browser.post(
                "/auth/logout", headers={"Origin": "https://app.test"}
            )
            assert response.status_code == 503
            assert browser.cookies.get("__Host-pk-session") is None
            assert browser.cookies.get("__Host-pk-login") is None
            assert store.deletes == 0
            store.unavailable = False
            assert (await browser.get("/auth/me")).status_code == 401

    asyncio.run(verify())


@pytest.mark.parametrize("origin", [None, "https://evil.test"])
def test_logout_checks_origin_before_reading_an_unavailable_store(
    origin: str | None,
) -> None:
    async def verify() -> None:
        store = ReadOutageStore()
        store.unavailable = True
        app = create_app(config=RuntimeConfig(), probes=())
        create_identity(
            config=config(),
            store=store,
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        ).install(app=app)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://app.test"
        ) as browser:
            browser.cookies.set("__Host-pk-session", "x" * 43)
            response = await browser.post(
                "/auth/logout", headers={} if origin is None else {"Origin": origin}
            )
            assert response.status_code == 403
            assert browser.cookies.get("__Host-pk-session") == "x" * 43
        assert store.reads == 0
        assert store.deletes == 0

    asyncio.run(verify())


@pytest.mark.parametrize(
    "configured", ["https://APP.TEST", "https://app.test:443", "https://APP.TEST:443"]
)
def test_browser_normalized_origin_can_logout(configured: str) -> None:
    async def verify() -> None:
        canonical_url = httpx.URL(configured)
        browser_origin = f"{canonical_url.scheme}://{canonical_url.netloc.decode()}"
        assert browser_origin == "https://app.test"
        app = create_app(config=RuntimeConfig(), probes=())
        create_identity(
            config=config(origin=configured),
            store=MemoryStore(),
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        ).install(app=app)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=browser_origin
        ) as browser:
            await browser.get("/auth/login")
            await browser.get("/auth/callback?state=valid-state&code=valid-code")
            me = await browser.get("/auth/me")
            response = await browser.post(
                "/auth/logout",
                headers={
                    "Origin": browser_origin,
                    "X-CSRF-Token": me.json()["csrf_token"],
                },
            )
            assert response.status_code == 204

    asyncio.run(verify())
