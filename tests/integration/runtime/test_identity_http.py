"""Opt-in HTTP identity contracts over ASGI without real upstream services."""

import asyncio
import json
import logging

from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient
import pytest
from tests.unit.runtime.test_identity import (
    CLIENT,
    TENANT,
    USER,
    Graph,
    MemoryStore,
    Provider,
    config,
)

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.core.identity.models import (
    AuthenticationRequiredError,
    AvatarMissingError,
    DependencyUnavailableError,
    IdentityError,
    InvalidCallbackError,
    PermissionDeniedError,
    Principal,
    UpstreamFailureError,
)
from platform_kit_runtime.identity import BearerGuard, SessionGuard, create_identity

pytestmark = pytest.mark.integration


class Validator:
    async def validate(self, *, token: str, audience: str) -> Principal:
        assert audience == CLIENT
        if token != "synthetic-bearer":  # noqa: S105 - synthetic test credential
            raise AuthenticationRequiredError
        return Principal(
            tenant_id=TENANT,
            subject_id=USER,
            scopes=frozenset({"read"}),
            roles=frozenset({"Reader"}),
        )


def test_browser_routes_cookies_redaction_csrf_and_replay(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def verify() -> None:
        app = create_app(config=RuntimeConfig(), probes=())
        identity = create_identity(
            config=config(),
            store=MemoryStore(),
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        )
        identity.install(app=app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as client:
            login = await client.get(
                "/auth/login?return_to=/home",
                headers={"X-Forwarded-Host": "evil.test", "X-Forwarded-Proto": "http"},
            )
            assert login.status_code == 303
            assert "__Host-pk-login=" in login.headers["set-cookie"]
            assert all(
                item in login.headers["set-cookie"]
                for item in ("Secure", "HttpOnly", "SameSite=lax", "Path=/")
            )
            callback = await client.get(
                "/auth/callback?code=valid-code&state=valid-state"
            )
            assert callback.status_code == 303
            assert callback.headers["location"] == "/home"
            assert "__Host-pk-session=" in callback.headers["set-cookie"]
            assert "private" not in json.dumps(dict(callback.headers))
            me = await client.get("/auth/me")
            assert me.status_code == 200
            assert me.json()["identity"] == {"tenant_id": TENANT, "subject_id": USER}
            csrf = me.json()["csrf_token"]
            assert me.json()["profile"] == {"display_name": "Synthetic User"}
            assert "private" not in me.text
            assert "access_token" not in me.text
            replay = await client.get(
                "/auth/callback?code=valid-code&state=valid-state"
            )
            assert replay.status_code == 400
            assert (await client.get("/auth/logout")).status_code == 405
            for headers in (
                {},
                {"Origin": "https://evil.test", "X-CSRF-Token": csrf},
                {"Origin": "https://app.test", "X-CSRF-Token": "wrong"},
            ):
                assert (
                    await client.post("/auth/logout", headers=headers)
                ).status_code == 403
            assert (await client.get("/auth/me")).status_code == 200
            logout = await client.post(
                "/auth/logout",
                headers={"Origin": "https://app.test", "X-CSRF-Token": csrf},
            )
            assert logout.status_code == 204
            assert "Max-Age=0" in logout.headers["set-cookie"]
            assert (await client.get("/auth/me")).status_code == 401
        assert "private" not in caplog.text
        assert "valid-code" not in caplog.text
        assert csrf not in caplog.text
        records = [
            record
            for record in caplog.records
            if getattr(record, "event", "") == "runtime.identity.problem"
        ]
        assert len(records) == 5
        assert all(record.exc_info is None for record in records)

    with caplog.at_level(logging.WARNING):
        asyncio.run(verify())


def test_api_requires_valid_bearer_and_all_scopes_roles() -> None:
    async def verify() -> None:
        app = create_app(config=RuntimeConfig(), probes=())
        identity = create_identity(
            config=config(),
            store=MemoryStore(),
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        )
        identity.install(app=app)
        allowed = BearerGuard(
            config=config(),
            validator=Validator(),
            scopes=frozenset({"read"}),
            roles=frozenset({"Reader"}),
        )
        forbidden = BearerGuard(
            config=config(),
            validator=Validator(),
            scopes=frozenset({"write"}),
            roles=frozenset({"Admin"}),
        )

        async def endpoint(request: Request) -> dict[str, str]:
            assert request
            return {"ok": "yes"}

        app.add_api_route("/protected", endpoint, dependencies=[Depends(allowed)])
        app.add_api_route("/forbidden", endpoint, dependencies=[Depends(forbidden)])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as client:
            for headers in (
                {},
                {"Authorization": "Bearer wrong"},
                {"Authorization": "Basic synthetic"},
            ):
                response = await client.get("/protected", headers=headers)
                assert response.status_code == 401
                assert response.headers["WWW-Authenticate"] == "Bearer"
            headers = {"Authorization": "Bearer synthetic-bearer"}
            assert (await client.get("/protected", headers=headers)).status_code == 200
            denied = await client.get("/forbidden", headers=headers)
            assert denied.status_code == 403
            assert denied.json()["code"] == "permission_denied"

    asyncio.run(verify())


def test_redis_outage_is_sanitized_503(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenStore(MemoryStore):
        async def put(self, *, key: str, value: bytes, ttl: int) -> None:
            assert key
            assert value
            assert ttl
            raise DependencyUnavailableError

    async def verify() -> None:
        app = create_app(config=RuntimeConfig(), probes=())
        identity = create_identity(
            config=config(),
            store=BrokenStore(),
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        )
        identity.install(app=app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as client:
            response = await client.get("/auth/login")
            assert response.status_code == 503
            assert response.headers["Content-Type"] == "application/problem+json"
            assert response.headers["Cache-Control"] == "no-store"
            assert response.json()["code"] == "identity_unavailable"
            assert "redis" not in response.text

    asyncio.run(verify())
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    ("error_type", "status", "code"),
    [
        (InvalidCallbackError, 400, "invalid_callback"),
        (AuthenticationRequiredError, 401, "authentication_required"),
        (PermissionDeniedError, 403, "permission_denied"),
        (DependencyUnavailableError, 503, "identity_unavailable"),
        (UpstreamFailureError, 502, "identity_upstream_failure"),
        (AvatarMissingError, 404, "avatar_missing"),
    ],
)
def test_each_identity_error_is_logged_once_without_details(
    error_type: type[IdentityError],
    status: int,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def verify() -> None:
        app = create_app(config=RuntimeConfig(), probes=())
        identity = create_identity(
            config=config(),
            store=MemoryStore(),
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        )
        identity.install(app=app)

        async def failing() -> None:
            message = "private-token-and-personal-data"
            raise error_type(message)

        app.add_api_route("/failure", failing)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as client:
            response = await client.get("/failure")
        assert response.status_code == status
        assert response.json()["code"] == code
        assert response.json()["instance"].startswith("urn:uuid:")
        assert "private" not in response.text
        assert "private" not in caplog.text
        assert len(caplog.records) == 1

    asyncio.run(verify())


@pytest.mark.parametrize(
    "query",
    ["code=a&state=a&state=b", "error=access_denied&state=a", "state=a", "code=a"],
)
def test_malformed_callback_consumes_binding_even_if_cookie_is_reused(
    query: str,
) -> None:
    async def verify() -> None:
        store = MemoryStore()
        app = create_app(config=RuntimeConfig(), probes=())
        create_identity(
            config=config(),
            store=store,
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        ).install(app=app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as client:
            await client.get("/auth/login")
            binding = client.cookies.get("__Host-pk-login")
            assert (await client.get(f"/auth/callback?{query}")).status_code == 400
            replay = await client.get(
                "/auth/callback?state=valid-state&code=valid-code",
                headers={"Cookie": f"__Host-pk-login={binding}"},
            )
            assert replay.status_code == 400
        assert not store.values

    asyncio.run(verify())


def test_localhost_cookie_mode_and_mutation_guard() -> None:
    async def verify() -> None:
        local = config(origin="http://localhost:8000", allow_insecure_loopback=True)
        app = create_app(config=RuntimeConfig(), probes=())
        identity = create_identity(
            config=local,
            store=MemoryStore(),
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        )
        identity.install(app=app)
        guard = SessionGuard(config=local, service=identity.service)

        async def mutate(request: Request) -> dict[str, str]:
            principal = await guard(request)
            assert principal.subject_id == USER
            return {"status": "ok"}

        app.add_api_route("/mutation", mutate, methods=["POST"])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=local.origin
        ) as client:
            login = await client.get("/auth/login")
            assert "pk-local-login=" in login.headers["set-cookie"]
            assert "Secure" not in login.headers["set-cookie"]
            await client.get("/auth/callback?state=valid-state&code=valid-code")
            me = await client.get("/auth/me")
            assert (await client.post("/mutation")).status_code == 403
            result = await client.post(
                "/mutation",
                headers={
                    "Origin": local.origin,
                    "X-CSRF-Token": me.json()["csrf_token"],
                },
            )
            assert result.status_code == 200

    asyncio.run(verify())


def test_logout_delete_outage_clears_cookies_but_does_not_claim_revocation() -> None:
    class BrokenDeleteStore(MemoryStore):
        async def delete(self, *, key: str) -> None:
            assert key
            raise DependencyUnavailableError

    async def verify() -> None:
        store = BrokenDeleteStore()
        app = create_app(config=RuntimeConfig(), probes=())
        create_identity(
            config=config(),
            store=store,
            provider=Provider(),
            graph=Graph(),
            validator=Validator(),
        ).install(app=app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as browser:
            await browser.get("/auth/login")
            await browser.get("/auth/callback?state=valid-state&code=valid-code")
            me = await browser.get("/auth/me")
            response = await browser.post(
                "/auth/logout",
                headers={
                    "Origin": "https://app.test",
                    "X-CSRF-Token": me.json()["csrf_token"],
                },
            )
            assert response.status_code == 503
            assert response.json()["code"] == "identity_unavailable"
            assert browser.cookies.get("__Host-pk-session") is None
            assert "Max-Age=0" in response.headers["set-cookie"]
        assert any(":session:" in key for key in store.values)

    asyncio.run(verify())
