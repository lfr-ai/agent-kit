"""Offline application contracts, using ephemeral ports rather than live services."""

import asyncio
from dataclasses import replace
import json
from typing import Final

import pytest

from platform_kit_runtime.application.identity import IdentityService
from platform_kit_runtime.core.identity.data import decode_session, encode_session
from platform_kit_runtime.core.identity.models import (
    REFRESH_MARGIN_SECONDS,
    AuthenticationRequiredError,
    IdentityConfig,
    InvalidCallbackError,
    PermissionDeniedError,
    Principal,
    ProviderLogin,
    ProviderTokens,
    SafeProfile,
    safe_return_path,
)


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: list[int] = []
        self.updates = 0

    async def get(self, *, key: str) -> bytes | None:
        return self.values.get(key)

    async def put(self, *, key: str, value: bytes, ttl: int) -> None:
        assert ttl > 0
        self.ttls.append(ttl)
        self.values[key] = value

    async def take(self, *, key: str) -> bytes | None:
        return self.values.pop(key, None)

    async def delete(self, *, key: str) -> None:
        self.values.pop(key, None)

    async def replace(
        self, *, key: str, expected: bytes, value: bytes, ttl: int
    ) -> bool:
        assert ttl > 0
        self.updates += 1
        if self.values.get(key) != expected:
            return False
        self.values[key] = value
        return True


TENANT: Final[str] = "11111111-1111-4111-8111-111111111111"
CLIENT: Final[str] = "22222222-2222-4222-8222-222222222222"
USER: Final[str] = "33333333-3333-4333-8333-333333333333"


def config(**changes: object) -> IdentityConfig:
    return replace(
        IdentityConfig(
            tenant_id=TENANT,
            client_id=CLIENT,
            api_audience=CLIENT,
            origin="https://app.test",
        ),
        **changes,
    )


class Provider:
    def __init__(self) -> None:
        self.tokens = ProviderTokens(
            principal=Principal(tenant_id=TENANT, subject_id=USER),
            access_token="private-access",  # noqa: S106 - synthetic offline token
            cache="private-refresh-cache",
            expires_at=4_000_000_000,
        )
        self.refresh_started = asyncio.Event()
        self.refresh_finish = asyncio.Event()

    async def begin(self) -> ProviderLogin:
        return ProviderLogin(
            authorization_url="https://login.microsoftonline.com/authorize",
            flow='{"state":"valid-state","nonce":"private-nonce","code_verifier":"private-pkce"}',
        )

    async def complete(self, *, flow: str, state: str, code: str) -> ProviderTokens:
        if state != json.loads(flow)["state"] or code != "valid-code":
            raise InvalidCallbackError
        return self.tokens

    async def refresh(self, *, tokens: ProviderTokens) -> ProviderTokens:
        self.refresh_started.set()
        await self.refresh_finish.wait()
        return replace(tokens, expires_at=4_000_000_000)


class Graph:
    def __init__(self) -> None:
        self.calls = 0

    async def profile(self, *, access_token: str) -> SafeProfile:
        assert access_token
        self.calls += 1
        return SafeProfile(display_name="Synthetic User")

    async def avatar(self, *, access_token: str) -> None:
        assert access_token
        self.calls += 1


def service(*, store: MemoryStore, provider: Provider, graph: Graph) -> IdentityService:
    return IdentityService(config=config(), store=store, provider=provider, graph=graph)


def test_login_is_bound_one_time_and_rotates_existing_session() -> None:
    async def verify() -> None:
        store, provider, graph = MemoryStore(), Provider(), Graph()
        identity = service(store=store, provider=provider, graph=graph)
        login = await identity.login(return_to="/home?tab=1")
        authenticated = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        assert authenticated.return_to == "/home?tab=1"
        assert "private" not in repr(authenticated)
        with pytest.raises(InvalidCallbackError):
            await identity.callback(
                binding=login.binding,
                state="valid-state",
                code="valid-code",
                previous=None,
            )
        again = await identity.login(return_to="/")
        rotated = await identity.callback(
            binding=again.binding,
            state="valid-state",
            code="valid-code",
            previous=authenticated.session_id,
        )
        assert rotated.session_id != authenticated.session_id
        with pytest.raises(AuthenticationRequiredError):
            await identity.session(session_id=authenticated.session_id)

    asyncio.run(verify())


def test_invalid_state_consumes_login() -> None:
    async def verify() -> None:
        identity = service(store=MemoryStore(), provider=Provider(), graph=Graph())
        login = await identity.login(return_to="/")
        for state in ("wrong-state", "valid-state"):
            with pytest.raises(InvalidCallbackError):
                await identity.callback(
                    binding=login.binding, state=state, code="valid-code", previous=None
                )

    asyncio.run(verify())


def test_graph_cache_is_per_user_and_cached_concurrent_miss() -> None:
    async def verify() -> None:
        provider, graph = Provider(), Graph()
        identity = service(store=MemoryStore(), provider=provider, graph=graph)
        login = await identity.login(return_to="/")
        result = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        session = await identity.session(session_id=result.session_id)
        profiles = await asyncio.gather(
            *(identity.profile(session=session) for _ in range(8))
        )
        assert all(item.display_name == "Synthetic User" for item in profiles)
        assert graph.calls == 1
        other = replace(
            session,
            tokens=replace(
                provider.tokens,
                principal=Principal(
                    tenant_id=TENANT, subject_id="44444444-4444-4444-8444-444444444444"
                ),
            ),
        )
        await identity.profile(session=other)
        assert graph.calls == 2

    asyncio.run(verify())


def test_logout_during_refresh_cannot_revive_session() -> None:
    async def verify() -> None:
        store, provider = MemoryStore(), Provider()
        identity = service(store=store, provider=provider, graph=Graph())
        provider.tokens = replace(provider.tokens, expires_at=0)
        login = await identity.login(return_to="/")
        result = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        refreshing = asyncio.create_task(identity.session(session_id=result.session_id))
        await provider.refresh_started.wait()
        await identity.logout(session_id=result.session_id)
        provider.refresh_finish.set()
        with pytest.raises(AuthenticationRequiredError):
            await refreshing
        assert store.updates == 1
        with pytest.raises(AuthenticationRequiredError):
            await identity.session(session_id=result.session_id)

    asyncio.run(verify())


def test_clock_bounds_refresh_margin_and_absolute_expiry() -> None:
    async def verify() -> None:
        now = [1_000_000.0]
        store, provider = MemoryStore(), Provider()
        identity = IdentityService(
            config=config(),
            store=store,
            provider=provider,
            graph=Graph(),
            clock=lambda: now[0],
        )
        provider.tokens = replace(
            provider.tokens, expires_at=int(now[0]) + REFRESH_MARGIN_SECONDS + 1
        )
        login = await identity.login(return_to="/")
        result = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        await identity.session(session_id=result.session_id)
        assert store.updates == 0
        now[0] += 1
        provider.refresh_finish.set()
        refreshed = await identity.session(session_id=result.session_id)
        assert store.updates == 1
        assert refreshed.tokens.expires_at == 4_000_000_000
        now[0] = refreshed.expires_at
        with pytest.raises(AuthenticationRequiredError):
            await identity.session(session_id=result.session_id, refresh=False)

    asyncio.run(verify())


def test_session_expiring_during_refresh_is_not_extended() -> None:
    async def verify() -> None:
        now = [1_000_000.0]
        store, provider = MemoryStore(), Provider()
        identity = IdentityService(
            config=config(),
            store=store,
            provider=provider,
            graph=Graph(),
            clock=lambda: now[0],
        )
        provider.tokens = replace(provider.tokens, expires_at=0)
        login = await identity.login(return_to="/")
        result = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        stored = decode_session(next(iter(store.values.values())))
        refreshing = asyncio.create_task(identity.session(session_id=result.session_id))
        await provider.refresh_started.wait()
        now[0] = stored.expires_at
        provider.refresh_finish.set()
        with pytest.raises(AuthenticationRequiredError):
            await refreshing
        assert store.updates == 0

    asyncio.run(verify())


@pytest.mark.parametrize(
    "path",
    [
        "//evil.test",
        "/\\evil.test",
        "https://evil.test",
        "/%2f/evil",
        "/%5c/evil",
        "/\nfoo",
        "/%252f/evil",
    ],
)
def test_unsafe_returns_are_rejected(path: str) -> None:
    with pytest.raises(InvalidCallbackError):
        safe_return_path(path)


@pytest.mark.parametrize("path", ["//[evil", "evil://[", "/%2F/[evil"])
def test_unparsable_returns_fail_closed_before_url_parsing(path: str) -> None:
    with pytest.raises(InvalidCallbackError):
        safe_return_path(path)


@pytest.mark.parametrize("path", ["/a:b", "/[", "/next?to=//[x"])
def test_relative_returns_with_url_delimiters_are_unchanged(path: str) -> None:
    assert safe_return_path(path) == path


def test_permissions_are_all_required_and_explicit() -> None:
    principal = Principal(
        tenant_id=TENANT,
        subject_id=USER,
        scopes=frozenset({"read"}),
        roles=frozenset({"Reader"}),
    )
    principal.require(scopes=frozenset({"read"}), roles=frozenset({"Reader"}))
    for scopes, roles in (
        (frozenset({"write"}), frozenset()),
        (frozenset(), frozenset({"Admin"})),
    ):
        with pytest.raises(PermissionDeniedError):
            principal.require(scopes=scopes, roles=roles)
    with pytest.raises(ValueError, match="permissions"):
        principal.require(scopes=frozenset(), roles=frozenset())


@pytest.mark.parametrize(
    "origin",
    [
        "http://app.test",
        "https://app.test/path",
        "https://user@app.test",
        "https://app.test?x=1",
        "https://app.test/#x",
    ],
)
def test_invalid_origin_rejected(origin: str) -> None:
    with pytest.raises(ValueError, match="origin"):
        config(origin=origin)


def test_http_requires_explicit_loopback_mode() -> None:
    with pytest.raises(ValueError, match="origin"):
        config(origin="http://localhost:8000")
    assert config(origin="http://localhost:8000", allow_insecure_loopback=True)
    with pytest.raises(ValueError, match="origin"):
        config(origin="http://evil.test", allow_insecure_loopback=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "common"},
        {"client_id": "organizations"},
        {"session_ttl_seconds": 0},
        {"session_ttl_seconds": True},
        {"session_ttl_seconds": 86401},
        {"cache_ttl_seconds": 901},
        {"cache_ttl_seconds": -1},
        {"allow_insecure_loopback": "true"},
    ],
)
def test_configuration_trust_boundaries_and_ttl_bounds(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match=r"[Ii]dentity"):
        config(**changes)


def test_absolute_expiry_even_if_store_returns_expired_state() -> None:
    async def verify() -> None:
        store = MemoryStore()
        identity = service(store=store, provider=Provider(), graph=Graph())
        login = await identity.login(return_to="/")
        result = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        key = next(key for key in store.values if ":session:" in key)
        store.values[key] = encode_session(
            replace(decode_session(store.values[key]), expires_at=0)
        )
        with pytest.raises(AuthenticationRequiredError):
            await identity.session(session_id=result.session_id)
        assert store.ttls == [300, 3600]

    asyncio.run(verify())


def test_missing_avatars_are_cached_per_tenant_and_user() -> None:
    async def verify() -> None:
        store, provider, graph = MemoryStore(), Provider(), Graph()
        identity = service(store=store, provider=provider, graph=graph)
        login = await identity.login(return_to="/")
        result = await identity.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        session = await identity.session(session_id=result.session_id)
        for _ in range(2):
            assert await identity.avatar(session=session) is None
        assert graph.calls == 1
        other_tenant = replace(
            session,
            tokens=replace(
                session.tokens,
                principal=replace(session.tokens.principal, tenant_id=CLIENT),
            ),
        )
        await identity.avatar(session=other_tenant)
        assert graph.calls == 2
        assert store.ttls[-2:] == [300, 300]

    asyncio.run(verify())


@pytest.mark.parametrize(
    "changes",
    [
        {"client_id": USER},
        {"tenant_id": USER},
        {"api_audience": "api://other"},
        {"origin": "https://other.test"},
        {"session_ttl_seconds": 1800},
        {"cache_ttl_seconds": 60},
        {"allow_insecure_loopback": True},
    ],
)
def test_shared_redis_cannot_authenticate_a_different_configuration(
    changes: dict[str, object],
) -> None:
    async def verify() -> None:
        store, provider, graph = MemoryStore(), Provider(), Graph()
        first = service(store=store, provider=provider, graph=graph)
        login = await first.login(return_to="/")
        second = IdentityService(
            config=config(**changes), store=store, provider=provider, graph=graph
        )
        with pytest.raises(InvalidCallbackError):
            await second.callback(
                binding=login.binding,
                state="valid-state",
                code="valid-code",
                previous=None,
            )
        await second.cancel_login(binding=login.binding)
        result = await first.callback(
            binding=login.binding, state="valid-state", code="valid-code", previous=None
        )
        with pytest.raises(AuthenticationRequiredError):
            await second.session(session_id=result.session_id)
        await second.logout(session_id=result.session_id)
        assert await first.session(session_id=result.session_id)

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("origin", "canonical"),
    [
        ("https://APP.TEST", "https://app.test"),
        ("https://app.test:443", "https://app.test"),
        ("https://APP.TEST:8443", "https://app.test:8443"),
        ("http://LOCALHOST:80", "http://localhost"),
        ("https://[0:0:0:0:0:0:0:1]:443", "https://[::1]"),
    ],
)
def test_config_normalizes_browser_origin(origin: str, canonical: str) -> None:
    configured = config(origin=origin, allow_insecure_loopback=True)
    assert configured.origin == canonical
    assert configured.redirect_uri == f"{canonical}/auth/callback"


@pytest.mark.parametrize(
    "origin",
    [
        "https://%61pp.test",
        "https://127.1",
        "https://0x7f000001",
        "https://app .test",
    ],
)
def test_config_rejects_ambiguous_browser_origin(origin: str) -> None:
    with pytest.raises(ValueError, match="origin"):
        config(origin=origin)


@pytest.mark.parametrize(
    "origin",
    [
        "https://",
        "https://:synthetic@app.test",
        "https://app.test/",
        "https://app.test?",
        "https://app.test#",
        "HTTPS://app.test",
        "https://\u00e4pp.test",
        "https://app.test\x7f",
        "https://app\\test",
    ],
)
def test_origin_rejects_each_unsafe_part(origin: str) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity origin\.$"):
        config(origin=origin)


@pytest.mark.parametrize("origin", [b"https://app.test", None])
def test_non_text_origin_fails_closed_before_text_checks(origin: object) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity origin\.$"):
        config(origin=origin)


@pytest.mark.parametrize(
    "origin",
    [
        "https://app.test:0",
        "https://app.test:00",
        "http://localhost:0",
        "http://[::1]:0",
    ],
)
def test_origin_rejects_port_zero(origin: str) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity origin\.$"):
        config(origin=origin, allow_insecure_loopback=origin.startswith("http:"))


@pytest.mark.parametrize(
    "origin",
    [
        "https://app.test:65536",
        "https://app.test:99999999999",
        "https://app.test:secret",
    ],
)
def test_out_of_range_origin_port_raises_the_runtime_message(origin: str) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity origin port\.$") as caught:
        config(origin=origin)
    assert "out of range" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "origin",
    ["https://[private-host-name]", "https://[::1", "https://[127.0.0.1]"],
)
def test_malformed_bracketed_origin_uses_sanitized_error_without_cause(
    origin: str,
) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity origin\.$") as caught:
        config(origin=origin)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "origin",
    [
        *(f"https://app{character}test" for character in "!\"$&'()*+,;<=>^_`{|}~"),
        "https://app.test;x",
        "https://[v1.app]",
        "https://.",
        "https://a..b",
        "https://-a.test",
        "https://a-.test",
        f"https://{'a' * 64}.test",
        "https://" + ".".join(("a" * 63, "b" * 63, "c" * 63, "d" * 63)),
    ],
)
def test_origin_host_rejects_non_hostname_characters(origin: str) -> None:
    with pytest.raises(ValueError, match=r"^Invalid identity origin\.$"):
        config(origin=origin)


@pytest.mark.parametrize(
    ("origin", "canonical"),
    [
        ("https://xn--bcher-kva.example", "https://xn--bcher-kva.example"),
        ("https://App-1.Test.", "https://app-1.test."),
        (
            "https://" + ".".join(("a" * 63, "b" * 63, "c" * 63, "d" * 61)),
            "https://" + ".".join(("a" * 63, "b" * 63, "c" * 63, "d" * 61)),
        ),
        ("https://192.0.2.1:8443", "https://192.0.2.1:8443"),
        ("https://[FE80::1]", "https://[fe80::1]"),
        ("https://[::ffff:192.0.2.1]", "https://[::ffff:192.0.2.1]"),
    ],
)
def test_origin_keeps_hostname_and_bracketed_ipv6_hosts(
    origin: str, canonical: str
) -> None:
    assert config(origin=origin).origin == canonical
