"""Atomic proof using a native process or an explicitly supplied isolated loopback URL.

Set ``RUNTIME_REDIS_TEST_URL=redis://127.0.0.1:<port>/0`` for a parent-provisioned
Redis/Valkey server. The test never starts containers, accepts credentials or
flushes a database. Only UUID-namespaced keys are written and deleted.
"""

import asyncio
import ipaddress
import os
from pathlib import Path
import re
import shutil
import socket
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from tests.unit.runtime.test_identity import MemoryStore

from platform_kit_runtime.core.identity.ports import IdentityStore
from platform_kit_runtime.infrastructure.identity.redis import RedisIdentityStore

pytestmark = pytest.mark.integration
_URL_ERROR = (
    "RUNTIME_REDIS_TEST_URL must be a credential-free redis/rediss loopback URL "
    "with a valid port and optional numeric database, without query overrides."
)


def _loopback_host(value: str) -> str:
    if value == "localhost":
        # Pin the reserved name to a literal address; never perform DNS resolution.
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError(_URL_ERROR) from None
    if not address.is_loopback:
        raise ValueError(_URL_ERROR)
    return (
        f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
    )


def _validated_test_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else 6379
    except ValueError:
        raise ValueError(_URL_ERROR) from None
    if (
        not value.isascii()
        or any(character.isspace() for character in value)
        or any(character in value for character in ("%", "\\", "?", "#"))
        or parsed.scheme not in {"redis", "rediss"}
        or parsed.username is not None
        or parsed.password is not None
        or port <= 0
        or re.fullmatch(r"(?:/[0-9]*)?", parsed.path) is None
    ):
        raise ValueError(_URL_ERROR)
    host = _loopback_host(parsed.hostname or "")
    path = parsed.path if parsed.path not in ("", "/") else "/0"
    return f"{parsed.scheme}://{host}:{port}{path}"


async def _exercise_atomic_store(*, store: IdentityStore) -> None:
    prefix = f"pk:identity:test:{uuid4().hex}"
    login, session = f"{prefix}:login", f"{prefix}:session"
    try:
        await store.put(key=login, value=b"flow", ttl=30)
        results = await asyncio.gather(*(store.take(key=login) for _ in range(16)))
        assert results.count(b"flow") == 1
        await store.put(key=session, value=b"before", ttl=30)
        assert await store.replace(
            key=session, expected=b"before", value=b"after", ttl=30
        )
        assert not await store.replace(
            key=session, expected=b"before", value=b"stale", ttl=30
        )
        await store.delete(key=session)
        assert not await store.replace(
            key=session, expected=b"after", value=b"revived", ttl=30
        )
        assert await store.get(key=session) is None
    finally:
        # Await both targeted deletions even when one fails. TTLs remain a backstop.
        cleanup = await asyncio.gather(
            store.delete(key=login), store.delete(key=session), return_exceptions=True
        )
        for result in cleanup:
            if isinstance(result, BaseException):
                raise result


async def _verify_url(url: str) -> None:
    async with Redis.from_url(
        _validated_test_url(url),
        decode_responses=False,
        socket_timeout=2,
        socket_connect_timeout=2,
    ) as client:
        await _exercise_atomic_store(store=RedisIdentityStore(client=client))


async def _ready(reader: asyncio.StreamReader) -> None:
    async with asyncio.timeout(10):
        while line := await reader.readline():
            if b"Ready to accept connections" in line:
                return
    pytest.fail("Disposable Redis exited before readiness")


async def _verify_native(*, executable: str, port: int, directory: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        executable,
        "--bind",
        "127.0.0.1",
        "--port",
        str(port),
        "--save",
        "",
        "--appendonly",
        "no",
        "--dir",
        str(directory),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        assert process.stdout is not None
        await _ready(process.stdout)
        await _verify_url(f"redis://127.0.0.1:{port}/0")
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


def test_atomic_scripts_against_disposable_redis(tmp_path: Path) -> None:
    supplied = os.environ.get("RUNTIME_REDIS_TEST_URL")
    if supplied is not None:
        asyncio.run(_verify_url(_validated_test_url(supplied)))
        return
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip(
            "No native Redis or RUNTIME_REDIS_TEST_URL; atomic command model is tested"
        )
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    asyncio.run(_verify_native(executable=executable, port=port, directory=tmp_path))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("redis://127.0.0.1:16379/0", "redis://127.0.0.1:16379/0"),
        ("redis://localhost:16379/2", "redis://127.0.0.1:16379/2"),
        ("redis://[::1]:16379/0", "redis://[::1]:16379/0"),
        ("rediss://127.0.0.1:16379", "rediss://127.0.0.1:16379/0"),
    ],
)
def test_supplied_redis_url_is_canonical_loopback(value: str, expected: str) -> None:
    assert _validated_test_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "redis://remote.test:6379/0",
        "redis://10.0.0.1:6379/0",
        "redis://localhost.example:6379/0",
        "redis://user:private@127.0.0.1:6379/0",
        "redis://:private@[::1]:6379/0",
        "redis://127.0.0.1:6379/0?host=remote.test",
        "redis://127.0.0.1:6379/0#fragment",
        "http://127.0.0.1:6379/0",
        "redis://[::1",
        "redis://127.0.0.1:private/0",
        "redis://127.0.0.1:0/0",
        "redis://127.0.0.1:6379/-1",
        "redis://127.0.0.1:6379/0/1",
        "redis://127.0.0.1:6379/%30",
        " redis://127.0.0.1:6379/0",
        "redis://127.0.0.1:\n6379/0",
        "redis://[::1%25eth0]:6379/0",
    ],
)
def test_unsafe_supplied_redis_url_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="RUNTIME_REDIS_TEST_URL") as caught:
        _validated_test_url(value)
    assert "private" not in str(caught.value)


def test_supplied_url_avoids_native_process_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    async def verify_url(url: str) -> None:
        called.append(url)

    def no_discovery(_name: str) -> None:
        pytest.fail("An explicit test URL must not discover or start a native server")

    monkeypatch.setenv("RUNTIME_REDIS_TEST_URL", "redis://localhost:16379/0")
    monkeypatch.setattr(shutil, "which", no_discovery)
    monkeypatch.setitem(globals(), "_verify_url", verify_url)
    test_atomic_scripts_against_disposable_redis(tmp_path)
    assert called == ["redis://127.0.0.1:16379/0"]


class RecordingStore(MemoryStore):
    def __init__(self, *, fail_write: bool = False) -> None:
        super().__init__()
        self.written: list[str] = []
        self.deleted: list[str] = []
        self.fail_write = fail_write

    async def put(self, *, key: str, value: bytes, ttl: int) -> None:
        self.written.append(key)
        await super().put(key=key, value=value, ttl=ttl)
        if self.fail_write and key.endswith(":session"):
            message = "Synthetic store failure"
            raise RuntimeError(message)

    async def delete(self, *, key: str) -> None:
        self.deleted.append(key)
        await super().delete(key=key)


@pytest.mark.parametrize("fail_write", [False, True])
def test_unique_keys_are_cleaned_without_touching_unrelated_state(
    fail_write: bool,
) -> None:
    async def verify() -> None:
        store = RecordingStore(fail_write=fail_write)
        store.values["unrelated"] = b"untouched"
        for _ in range(2):
            if fail_write:
                with pytest.raises(RuntimeError, match="Synthetic store failure"):
                    await _exercise_atomic_store(store=store)
            else:
                await _exercise_atomic_store(store=store)
            assert store.values == {"unrelated": b"untouched"}
        assert len(set(store.written)) == 4
        assert set(store.deleted) == set(store.written)
        assert all(key.startswith("pk:identity:test:") for key in store.deleted)
        assert store.ttls == [30] * 4

    asyncio.run(verify())
