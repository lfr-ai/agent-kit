import asyncio
from collections.abc import Awaitable
from dataclasses import replace
import hashlib
import json
import logging
import sys

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.authentication import BaseUser, SimpleUser, UnauthenticatedUser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.application.rate_limit import RateLimitService
from platform_kit_runtime.core.rate_limit import RateLimitDecision
from platform_kit_runtime.middleware import (
    InMemoryRateLimitStore,
    RateLimitPolicy,
    RateLimitStoreError,
    RedisRateLimitStore,
    WindowCount,
)
from platform_kit_runtime.presentation.rate_limit import RateLimitMiddleware

pytestmark = pytest.mark.unit

_PRIVATE = "synthetic-secret-user@example.invalid"


class RecordingStore:
    def __init__(self, *, count: int = 1, error: bool = False) -> None:
        self.count = count
        self.error = error
        self.keys: list[str] = []

    async def hit(self, *, key: str, window_seconds: int) -> WindowCount:
        self.keys.append(key)
        if self.error:
            raise RateLimitStoreError
        return WindowCount(count=self.count, reset_seconds=window_seconds)


class FakeRedis:
    def __init__(self, *, reply: object = None, error: Exception | None = None) -> None:
        self.reply = [1, 60_000] if reply is None else reply
        self.error = error
        self.commands: list[tuple[str | bytes | int, ...]] = []

    def execute_command(self, *args: str | bytes | int) -> Awaitable[object]:
        self.commands.append(args)

        async def reply() -> object:
            if self.error is not None:
                raise self.error
            return self.reply

        return reply()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class BrokenUser(BaseUser):
    pass


def digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def http_scope(
    *,
    path: str = "/items",
    forwarded: tuple[str, ...] = (),
    client: tuple[str, int] | None = ("192.0.2.10", 5000),
    user: BaseUser | None = None,
) -> Scope:
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": [(b"x-forwarded-for", value.encode()) for value in forwarded],
        "client": client,
    }
    if user is not None:
        scope["user"] = user
    return scope


async def ok(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def call(app: ASGIApp, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def run() -> None:
        await app(scope, receive, send)

    asyncio.run(run())
    return sent


def limited(
    *, store: RecordingStore, limit: int = 5, hops: int = 0
) -> RateLimitMiddleware:
    policy = RateLimitPolicy(limit=limit, window_seconds=60)
    return RateLimitMiddleware(
        ok,
        limiter=RateLimitService(policy=policy, store=store),
        trusted_proxy_hops=hops,
    )


def headers_of(message: Message) -> dict[str, str]:
    return {name.decode(): value.decode() for name, value in message["headers"]}


@pytest.mark.parametrize(
    ("field", "values", "message"),
    [
        (
            "limit",
            [0, -1, 1_000_001, True, 1.5, "private-value", None],
            "limit must be an integer in [1, 1000000].",
        ),
        (
            "window_seconds",
            [0, -1, 86_401, False, 2.0, "private-value", None],
            "window_seconds must be an integer in [1, 86400].",
        ),
    ],
)
def test_policy_rejects_invalid_values_without_echoing(
    field: str, values: list[object], message: str
) -> None:
    for value in values:
        with pytest.raises(ValueError, match=field) as caught:
            replace(RateLimitPolicy(limit=10, window_seconds=60), **{field: value})
        assert str(caught.value) == message


def test_policy_bounds_are_inclusive() -> None:
    assert RateLimitPolicy(limit=1, window_seconds=1).limit == 1
    assert RateLimitPolicy(limit=1_000_000, window_seconds=86_400).window_seconds == (
        86_400
    )


def test_policy_decides_and_never_reports_negative_remaining() -> None:
    policy = RateLimitPolicy(limit=2, window_seconds=60)

    decisions = [
        policy.decide(window=WindowCount(count=count, reset_seconds=7))
        for count in (1, 2, 3, 9)
    ]

    assert [decision.allowed for decision in decisions] == [True, True, False, False]
    assert [decision.remaining for decision in decisions] == [1, 0, 0, 0]
    assert decisions[0] == RateLimitDecision(
        allowed=True, limit=2, window_seconds=60, remaining=1, reset_seconds=7
    )


def test_memory_store_counts_within_a_window_and_resets_after_it() -> None:
    clock = Clock()
    store = InMemoryRateLimitStore(clock=clock)

    async def scenario() -> list[WindowCount]:
        counts = [await store.hit(key="a", window_seconds=10)]
        clock.now += 2.5
        counts.append(await store.hit(key="a", window_seconds=10))
        counts.append(await store.hit(key="b", window_seconds=10))
        clock.now += 7.5
        counts.append(await store.hit(key="a", window_seconds=10))
        clock.now += 9.99
        counts.append(await store.hit(key="a", window_seconds=10))
        return counts

    assert asyncio.run(scenario()) == [
        WindowCount(count=1, reset_seconds=10),
        WindowCount(count=2, reset_seconds=8),
        WindowCount(count=1, reset_seconds=10),
        WindowCount(count=1, reset_seconds=10),
        WindowCount(count=2, reset_seconds=1),
    ]


def test_memory_store_evicts_expired_then_oldest_windows_at_capacity() -> None:
    clock = Clock()
    store = InMemoryRateLimitStore(max_keys=2, clock=clock)

    async def scenario() -> list[int]:
        await store.hit(key="a", window_seconds=5)
        await store.hit(key="a", window_seconds=5)
        clock.now += 1
        await store.hit(key="b", window_seconds=5)
        await store.hit(key="c", window_seconds=5)
        b = await store.hit(key="b", window_seconds=5)
        a = await store.hit(key="a", window_seconds=5)
        clock.now += 10
        d = await store.hit(key="d", window_seconds=5)
        return [b.count, a.count, d.count]

    assert asyncio.run(scenario()) == [2, 1, 1]


@pytest.mark.parametrize("max_keys", [0, -1, True, 1.5, "10"])
def test_memory_store_rejects_invalid_capacity(max_keys: int) -> None:
    with pytest.raises(ValueError, match="max_keys"):
        InMemoryRateLimitStore(max_keys=max_keys)


def test_redis_store_runs_one_atomic_script_with_a_prefixed_key() -> None:
    client = FakeRedis(reply=[3, 1_500])
    store = RedisRateLimitStore(client=client, prefix="app:")

    window = asyncio.run(store.hit(key="abc", window_seconds=60))

    assert window == WindowCount(count=3, reset_seconds=2)
    [command] = client.commands
    assert command[0] == "EVAL"
    assert "INCR" in str(command[1])
    assert "PEXPIRE" in str(command[1])
    assert command[2:] == (1, "app:abc", 60_000)


def test_redis_store_rounds_a_short_ttl_up_to_one_second() -> None:
    store = RedisRateLimitStore(client=FakeRedis(reply=[1, 0]))

    assert asyncio.run(store.hit(key="k", window_seconds=1)).reset_seconds == 1


@pytest.mark.parametrize(
    "reply",
    [b"OK", {"count": 1}, [], [1], [1, 2, 3], [0, 10], [1, -1], [True, 10], ["1", 10]],
)
def test_redis_store_rejects_unexpected_replies(reply: object) -> None:
    store = RedisRateLimitStore(client=FakeRedis(reply=reply))

    with pytest.raises(RateLimitStoreError):
        asyncio.run(store.hit(key="k", window_seconds=1))


def test_redis_store_translates_vendor_errors() -> None:
    vendor = RedisConnectionError(_PRIVATE)
    store = RedisRateLimitStore(client=FakeRedis(error=vendor))

    with pytest.raises(RateLimitStoreError) as caught:
        asyncio.run(store.hit(key="k", window_seconds=1))

    assert caught.value.__cause__ is vendor
    assert _PRIVATE not in str(caught.value)


def test_redis_store_requires_the_ratelimit_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "redis.exceptions", None)

    with pytest.raises(ImportError):
        RedisRateLimitStore(client=FakeRedis())


def test_service_hashes_keys_before_they_reach_the_store() -> None:
    store = RecordingStore(count=2)
    service = RateLimitService(
        policy=RateLimitPolicy(limit=1, window_seconds=30), store=store
    )

    decision = asyncio.run(service.check(key=f"principal:{_PRIVATE}"))

    assert decision is not None
    assert not decision.allowed
    assert store.keys == [digest(f"principal:{_PRIVATE}")]


def test_service_fails_open_with_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    service = RateLimitService(
        policy=RateLimitPolicy(limit=1, window_seconds=30),
        store=RecordingStore(error=True),
    )

    assert asyncio.run(service.check(key=f"address:{_PRIVATE}")) is None

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert vars(record)["event"] == "runtime.rate_limit_unavailable"
    assert _PRIVATE not in repr(vars(record))


def test_allowed_responses_carry_quota_headers() -> None:
    store = RecordingStore(count=2)

    start, body = call(limited(store=store), http_scope())

    assert start["status"] == 200
    assert headers_of(start) == {
        "ratelimit-policy": '"default";q=5;w=60',
        "ratelimit": '"default";r=3;t=60',
    }
    assert body["body"] == b"ok"


def test_over_limit_requests_get_a_429_problem(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RecordingStore(count=6)

    start, body = call(limited(store=store), http_scope())

    headers = headers_of(start)
    document = json.loads(body["body"])
    assert start["status"] == 429
    assert headers["content-type"] == "application/problem+json"
    assert headers["cache-control"] == "no-store"
    assert headers["retry-after"] == "60"
    assert headers["ratelimit-policy"] == '"default";q=5;w=60'
    assert headers["ratelimit"] == '"default";r=0;t=60'
    assert document["type"] == "about:blank"
    assert document["title"] == "Too Many Requests"
    assert document["status"] == 429
    assert document["code"] == "rate_limited"
    assert document["instance"].startswith("urn:uuid:")
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert vars(record)["event"] == "runtime.problem"
    assert vars(record)["problem_code"] == "rate_limited"
    assert vars(record)["instance"] == document["instance"]


def test_store_failure_lets_requests_through_without_headers() -> None:
    start, _ = call(limited(store=RecordingStore(error=True)), http_scope())

    assert start["status"] == 200
    assert headers_of(start) == {}


def test_health_and_non_http_scopes_are_not_counted() -> None:
    store = RecordingStore(count=99)
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    policy = RateLimitPolicy(limit=1, window_seconds=60)
    app = RateLimitMiddleware(
        inner,
        limiter=RateLimitService(policy=policy, store=store),
        trusted_proxy_hops=0,
    )

    [start, _] = call(limited(store=store), http_scope(path="/health/ready"))
    call(app, {"type": "lifespan"})
    call(app, {**http_scope(), "type": "websocket"})

    assert start["status"] == 200
    assert seen == ["lifespan", "websocket"]
    assert store.keys == []


def test_authenticated_principals_are_keyed_by_identity() -> None:
    store = RecordingStore()

    call(limited(store=store), http_scope(user=SimpleUser(_PRIVATE)))

    assert store.keys == [digest(f"principal:{_PRIVATE}")]


@pytest.mark.parametrize("user", [UnauthenticatedUser(), BrokenUser()])
def test_anonymous_or_unusable_users_are_keyed_by_address(user: BaseUser) -> None:
    store = RecordingStore()

    call(limited(store=store), http_scope(user=user))

    assert store.keys == [digest("address:192.0.2.10")]


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (0, ("198.51.100.1",), "192.0.2.10"),
        (1, ("198.51.100.1",), "198.51.100.1"),
        (1, ("6.6.6.6, 198.51.100.1",), "198.51.100.1"),
        (1, ("6.6.6.6", "198.51.100.1"), "198.51.100.1"),
        (2, ("6.6.6.6, 198.51.100.1, 10.0.0.2",), "198.51.100.1"),
        (2, ("6.6.6.6, 198.51.100.1", "10.0.0.2"), "198.51.100.1"),
        (1, ("198.51.100.1:443",), "198.51.100.1"),
        (1, ("[2001:DB8::1]:443",), "2001:db8::1"),
        (1, ("2001:db8:0::1",), "2001:db8::1"),
        (2, ("198.51.100.1",), "192.0.2.10"),
        (1, ("not-an-address",), "192.0.2.10"),
        (1, ("unknown, ",), "192.0.2.10"),
        (1, (), "192.0.2.10"),
    ],
)
def test_forwarded_addresses_are_trusted_only_for_configured_hops(
    hops: int, forwarded: tuple[str, ...], expected: str
) -> None:
    store = RecordingStore()

    call(limited(store=store, hops=hops), http_scope(forwarded=forwarded))

    assert store.keys == [digest(f"address:{expected}")]


def test_requests_without_a_peer_share_one_key() -> None:
    store = RecordingStore()

    call(limited(store=store), http_scope(client=None))

    assert store.keys == [digest("address:unknown")]


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"rate_limit": {"limit": 1}}, TypeError),
        ({"tracing": "yes"}, TypeError),
        ({"tracing": 1}, TypeError),
        ({"trusted_proxy_hops": -1}, ValueError),
        ({"trusted_proxy_hops": 17}, ValueError),
        ({"trusted_proxy_hops": True}, ValueError),
        ({"trusted_proxy_hops": 1.0}, ValueError),
    ],
)
def test_config_rejects_invalid_http_settings(
    overrides: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error, match=next(iter(overrides))):
        replace(RuntimeConfig(), **overrides)


def test_config_defaults_keep_rate_limiting_and_tracing_off() -> None:
    config = RuntimeConfig()

    assert config.rate_limit is None
    assert config.trusted_proxy_hops == 0
    assert config.tracing is False


def test_a_store_without_a_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="rate_limit"):
        create_app(config=RuntimeConfig(), probes=(), rate_limit_store=RecordingStore())
