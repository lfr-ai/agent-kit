"""Real JWT verification and transport/atomic-store contracts, all offline."""

import asyncio
import base64
import json
import time
from typing import TYPE_CHECKING, Final

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from platform_kit_runtime.core.identity.models import (
    MAX_AVATAR_BYTES,
    AuthenticationRequiredError,
    DependencyUnavailableError,
    IdentityConfig,
    UpstreamFailureError,
)
from platform_kit_runtime.infrastructure.identity import jwt as jwt_adapter
from platform_kit_runtime.infrastructure.identity.graph import GraphAdapter
from platform_kit_runtime.infrastructure.identity.http import HttpxIdentityTransport
from platform_kit_runtime.infrastructure.identity.jwt import EntraJWTValidator
from platform_kit_runtime.infrastructure.identity.redis import (
    _REPLACE_EXISTING_SCRIPT,
    RedisIdentityStore,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

TENANT: Final[str] = "11111111-1111-4111-8111-111111111111"
CLIENT: Final[str] = "22222222-2222-4222-8222-222222222222"
USER: Final[str] = "33333333-3333-4333-8333-333333333333"


def settings() -> IdentityConfig:
    return IdentityConfig(
        tenant_id=TENANT,
        client_id=CLIENT,
        api_audience=CLIENT,
        origin="https://app.test",
    )


def signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    return key, jwk


def claims() -> dict[str, object]:
    now = int(time.time())
    return {
        "iss": settings().issuer,
        "aud": CLIENT,
        "tid": TENANT,
        "oid": USER,
        "sub": USER,
        "exp": now + 3600,
        "nbf": now - 1,
        "iat": now,
        "scp": "read write",
        "roles": ["Reader"],
    }


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"tid": CLIENT},
        {"aud": "wrong"},
        {"iss": "https://evil.test"},
        {"exp": 1},
        {"nbf": 4_000_000_000},
        {"roles": "Admin"},
        {"oid": "not-an-id"},
    ],
)
def test_bearer_claim_validation(change: dict[str, object]) -> None:
    async def verify() -> None:
        key, jwk = signing_material()
        token = jwt.encode(
            claims() | change, key, algorithm="RS256", headers={"kid": "test-key"}
        )
        calls = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            assert request.url == f"{settings().authority}/discovery/v2.0/keys"
            return httpx.Response(200, json={"keys": [jwk]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            validator = EntraJWTValidator(
                config=settings(), http=HttpxIdentityTransport(client=client)
            )
            if change:
                with pytest.raises(AuthenticationRequiredError):
                    await validator.validate(token=token, audience=CLIENT)
            else:
                principal = await validator.validate(token=token, audience=CLIENT)
                assert principal.tenant_id == TENANT
                assert principal.scopes == frozenset({"read", "write"})
                await validator.validate(token=token, audience=CLIENT)
                assert len(calls) == 1

    asyncio.run(verify())


@pytest.mark.parametrize("algorithm", ["none", "HS256", "RS256"])
def test_unsigned_wrong_algorithm_and_wrong_signature_fail(algorithm: str) -> None:
    async def verify() -> None:
        _, jwk = signing_material()
        signing_key, _ = signing_material()
        key = (
            signing_key
            if algorithm == "RS256"
            else (
                "offline-hmac-secret-at-least-32-bytes" if algorithm == "HS256" else ""
            )
        )
        token = jwt.encode(
            claims(), key, algorithm=algorithm, headers={"kid": "test-key"}
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"keys": [jwk]})
            )
        ) as client:
            validator = EntraJWTValidator(
                config=settings(), http=HttpxIdentityTransport(client=client)
            )
            with pytest.raises(AuthenticationRequiredError):
                await validator.validate(token=token, audience=CLIENT)

    asyncio.run(verify())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="secret provider failure"),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"keys": []}),
    ],
)
def test_jwks_outages_and_bad_data(response: httpx.Response) -> None:
    async def verify() -> None:
        key, _ = signing_material()
        token = jwt.encode(
            claims(), key, algorithm="RS256", headers={"kid": "test-key"}
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: response)
        ) as client:
            validator = EntraJWTValidator(
                config=settings(), http=HttpxIdentityTransport(client=client)
            )
            expected = (
                DependencyUnavailableError
                if response.status_code == 503
                else UpstreamFailureError
            )
            with pytest.raises(expected):
                await validator.validate(token=token, audience=CLIENT)

    asyncio.run(verify())


def test_graph_only_allowlisted_data_and_bounded_images() -> None:
    async def verify() -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer offline-graph"
            if request.url.path.endswith("/me"):
                assert request.url.params["$select"] == "displayName"
                return httpx.Response(
                    200,
                    json={
                        "displayName": "Synthetic",
                        "mail": "private@example.test",
                        "access_token": "leak",
                    },
                )
            return httpx.Response(
                200,
                content=b"\xff\xd8\xffphoto",
                headers={"Content-Type": "image/jpeg"},
            )

        token = "offline-graph"  # noqa: S105 - synthetic delegated credential
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            graph = GraphAdapter(http=HttpxIdentityTransport(client=client))
            profile = await graph.profile(access_token=token)
            assert profile.display_name == "Synthetic"
            assert "private" not in repr(profile)
            avatar = await graph.avatar(access_token=token)
            assert avatar is not None
            assert avatar.content == b"\xff\xd8\xffphoto"

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("content", "media"),
    [
        (b"<svg/>", "image/svg+xml"),
        (b"<html/>", "image/jpeg"),
        (b"\xff\xd8\xff" + b"x" * MAX_AVATAR_BYTES, "image/jpeg"),
    ],
    ids=["active-svg", "mislabeled-html", "oversized-jpeg"],
)
def test_graph_rejects_active_mislabeled_and_oversized_images(
    content: bytes, media: str
) -> None:
    async def verify() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, content=content, headers={"Content-Type": media}
                )
            )
        ) as client:
            graph = GraphAdapter(http=HttpxIdentityTransport(client=client))
            with pytest.raises(UpstreamFailureError):
                await graph.avatar(access_token=base64.b64encode(b"offline").decode())

    asyncio.run(verify())


class AtomicRedis:
    """Model Redis's atomic command boundary, not a get-then-set approximation."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.commands: list[str] = []

    async def execute_command(self, *args: str | bytes | int) -> object:
        match args:
            case ("GET", str(key)):
                return await self.get(key)
            case ("GETDEL", str(key)):
                return await self.getdel(key)
            case ("SET", str(key), bytes(value), "EX", int(ttl)):
                return await self.set(key, value, ex=ttl)
            case ("DEL", str(key)):
                return await self.delete(key)
            case ("EVAL", str(script), int(numkeys), *values):
                return await self.eval(script, numkeys, *values)
        pytest.fail("Unexpected Redis command shape")

    async def get(self, name: str) -> bytes | None:
        self.commands.append("GET")
        return self.values.get(name)

    async def getdel(self, name: str) -> bytes | None:
        self.commands.append("GETDEL")
        return self.values.pop(name, None)

    async def set(self, name: str, value: bytes, *, ex: int) -> bool:
        assert ex > 0
        self.commands.append("SET")
        self.values[name] = value
        return True

    async def delete(self, name: str) -> int:
        self.commands.append("DEL")
        return int(self.values.pop(name, None) is not None)

    async def eval(self, script: str, numkeys: int, *args: str | bytes | int) -> int:
        assert script == _REPLACE_EXISTING_SCRIPT
        assert "redis.call('GET', KEYS[1]) == ARGV[1]" in script
        assert "'XX'" in script
        assert "'EX'" in script
        assert numkeys == 1
        key, expected, value, ttl = args
        assert isinstance(key, str)
        assert isinstance(value, bytes)
        assert isinstance(ttl, int)
        assert ttl > 0
        self.commands.append("EVAL")
        if self.values.get(key) != expected:
            return 0
        self.values[key] = value
        return 1


def test_redis_single_use_and_compare_existing_atomic_commands() -> None:
    async def verify() -> None:
        client = AtomicRedis()
        store = RedisIdentityStore(client=client)
        await store.put(key="login", value=b"state", ttl=300)
        results = await asyncio.gather(*(store.take(key="login") for _ in range(8)))
        assert results.count(b"state") == 1
        await store.put(key="session", value=b"old", ttl=300)
        assert not await store.replace(
            key="session", expected=b"stale", value=b"new", ttl=300
        )
        assert await store.replace(
            key="session", expected=b"old", value=b"new", ttl=300
        )
        await store.delete(key="session")
        assert not await store.replace(
            key="session", expected=b"new", value=b"revived", ttl=300
        )
        assert "GET" not in client.commands
        assert client.commands.count("EVAL") == 3

    asyncio.run(verify())


def test_redis_exception_is_chained_and_sanitized() -> None:
    class BrokenRedis(AtomicRedis):
        async def get(self, name: str) -> bytes | None:
            assert name
            message = "private redis credential"
            raise RedisConnectionError(message)

    async def verify() -> None:
        store = RedisIdentityStore(client=BrokenRedis())
        with pytest.raises(DependencyUnavailableError) as caught:
            await store.get(key="session")
        assert isinstance(caught.value.__cause__, RedisConnectionError)
        assert str(caught.value) == ""

    asyncio.run(verify())


@pytest.mark.parametrize("operation", ["get", "getdel", "set", "delete", "eval"])
def test_each_redis_operation_fails_closed(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*args: object, **kwargs: object) -> object:
        message = "redis-secret-and-host"
        raise RedisConnectionError(message)

    async def verify() -> None:
        client = AtomicRedis()
        monkeypatch.setattr(client, operation, broken)
        store = RedisIdentityStore(client=client)
        calls: dict[str, Callable[[], Awaitable[object]]] = {
            "get": lambda: store.get(key="k"),
            "getdel": lambda: store.take(key="k"),
            "set": lambda: store.put(key="k", value=b"v", ttl=30),
            "delete": lambda: store.delete(key="k"),
            "eval": lambda: store.replace(key="k", expected=b"v", value=b"n", ttl=30),
        }
        with pytest.raises(DependencyUnavailableError) as caught:
            await calls[operation]()
        assert isinstance(caught.value.__cause__, RedisConnectionError)
        assert not str(caught.value)

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, AuthenticationRequiredError),
        (403, UpstreamFailureError),
        (429, DependencyUnavailableError),
        (503, DependencyUnavailableError),
        (302, UpstreamFailureError),
    ],
)
def test_graph_upstream_status_mapping(
    status: int, error_type: type[Exception]
) -> None:
    async def verify() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="private upstream response")
            )
        ) as client:
            graph = GraphAdapter(http=HttpxIdentityTransport(client=client))
            with pytest.raises(error_type) as caught:
                await graph.profile(access_token=base64.b64encode(b"offline").decode())
            assert not str(caught.value)

    asyncio.run(verify())


def test_http_network_errors_are_chained() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        message = "private transport detail"
        raise httpx.ConnectError(message, request=request)

    async def verify() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unavailable)
        ) as client:
            transport = HttpxIdentityTransport(client=client)
            with pytest.raises(DependencyUnavailableError) as caught:
                await transport.get(
                    url="https://graph.microsoft.com/v1.0/me",
                    access_token=None,
                    max_bytes=100,
                )
            assert isinstance(caught.value.__cause__, httpx.ConnectError)
            assert not str(caught.value)

    asyncio.run(verify())


@pytest.mark.parametrize(
    "document",
    [
        b"invalid-json",
        b'{"displayName":{"nested":"private"}}',
        b'{"displayName":"' + b"x" * 257 + b'"}',
    ],
)
def test_graph_malformed_profile_is_not_exposed(document: bytes) -> None:
    async def verify() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, content=document)
            )
        ) as client:
            graph = GraphAdapter(http=HttpxIdentityTransport(client=client))
            with pytest.raises(UpstreamFailureError):
                await graph.profile(access_token=base64.b64encode(b"offline").decode())

    asyncio.run(verify())


def test_jwks_key_issuer_cannot_override_configured_tenant() -> None:
    async def verify() -> None:
        key, jwk = signing_material()
        jwk["issuer"] = f"https://login.microsoftonline.com/{CLIENT}/v2.0"
        token = jwt.encode(
            claims(), key, algorithm="RS256", headers={"kid": "test-key"}
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"keys": [jwk]})
            )
        ) as client:
            validator = EntraJWTValidator(
                config=settings(), http=HttpxIdentityTransport(client=client)
            )
            with pytest.raises(UpstreamFailureError):
                await validator.validate(token=token, audience=CLIENT)

    asyncio.run(verify())


class DiscoveryClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def test_jwks_refresh_cooldown_covers_failures_without_extending_key_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def verify() -> None:
        clock = DiscoveryClock()
        monkeypatch.setattr(jwt_adapter, "time", clock)
        key, jwk = signing_material()
        known = jwt.encode(
            claims(), key, algorithm="RS256", headers={"kid": "test-key"}
        )
        unknown = jwt.encode(
            claims(), key, algorithm="RS256", headers={"kid": "unknown"}
        )
        expired = jwt.encode(
            claims() | {"exp": 1}, key, algorithm="RS256", headers={"kid": "test-key"}
        )
        calls: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if len(calls) == 1:
                return httpx.Response(200, json={"keys": [jwk]})
            return httpx.Response(503, text="private discovery detail")

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            validator = EntraJWTValidator(
                config=settings(), http=HttpxIdentityTransport(client=client)
            )
            assert await validator.validate(token=known, audience=CLIENT)
            clock.now = 31
            for _ in range(5):
                with pytest.raises(DependencyUnavailableError):
                    await validator.validate(token=unknown, audience=CLIENT)
            assert len(calls) == 2
            assert await validator.validate(token=known, audience=CLIENT)
            with pytest.raises(AuthenticationRequiredError):
                await validator.validate(token=expired, audience=CLIENT)
            clock.now = 61
            with pytest.raises(DependencyUnavailableError):
                await validator.validate(token=unknown, audience=CLIENT)
            assert len(calls) == 3
            clock.now = 301
            for _ in range(5):
                with pytest.raises(DependencyUnavailableError):
                    await validator.validate(token=known, audience=CLIENT)
            assert len(calls) == 4

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (503, DependencyUnavailableError),
        (200, UpstreamFailureError),
    ],
)
def test_initial_discovery_failure_is_also_rate_limited(
    status: int,
    error_type: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def verify() -> None:
        clock = DiscoveryClock()
        monkeypatch.setattr(jwt_adapter, "time", clock)
        key, _ = signing_material()
        token = jwt.encode(
            claims(), key, algorithm="RS256", headers={"kid": "test-key"}
        )
        calls: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(status, content=b"private invalid discovery")

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            validator = EntraJWTValidator(
                config=settings(), http=HttpxIdentityTransport(client=client)
            )
            for _ in range(5):
                with pytest.raises(error_type) as caught:
                    await validator.validate(token=token, audience=CLIENT)
                assert not str(caught.value)
            assert len(calls) == 1
            clock.now = 31
            with pytest.raises(error_type):
                await validator.validate(token=token, audience=CLIENT)
            assert len(calls) == 2

    asyncio.run(verify())
