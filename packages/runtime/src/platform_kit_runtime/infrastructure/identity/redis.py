"""Redis private state with GETDEL and a single existing-only compare/update."""

from collections.abc import Awaitable
from typing import Protocol

from redis.exceptions import RedisError

from platform_kit_runtime.core.identity.models import DependencyUnavailableError

_REPLACE_EXISTING_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    local saved = redis.call('SET', KEYS[1], ARGV[2], 'XX', 'EX', ARGV[3])
    if saved then
        return 1
    end
end
return 0
"""


class RedisCommands(Protocol):
    """Minimal asynchronous binary Redis command surface (Redis 6.2+)."""

    def execute_command(self, *args: str | bytes | int) -> Awaitable[object]:
        """Return the untrusted reply to ``args``; raise ``RedisError`` when awaited."""
        ...


class RedisIdentityStore:
    """Never use get-then-delete or get-then-set for one-time or refreshed state."""

    def __init__(self, *, client: RedisCommands) -> None:
        """Bind a caller-owned private Redis client.

        Args:
            client (RedisCommands): Binary client with bounded timeouts and TLS.
        """
        self._client = client

    async def get(self, *, key: str) -> bytes | None:
        """Return the bytes at ``key``, or ``None`` when absent or expired.

        Raises ``DependencyUnavailableError`` when Redis does not complete the
        read.
        """
        try:
            return _binary_reply(await self._client.execute_command("GET", key))
        except RedisError as error:
            raise DependencyUnavailableError from error

    async def put(self, *, key: str, value: bytes, ttl: int) -> None:
        """Write private state with a positive expiry.

        Args:
            key (str): Namespaced private storage key.
            value (bytes): Private serialized state.
            ttl (int): Positive expiry in seconds.

        Raises:
            DependencyUnavailableError: Redis did not acknowledge the write.
        """
        try:
            if (
                await self._client.execute_command("SET", key, value, "EX", ttl)
                is not True
            ):
                raise DependencyUnavailableError
        except RedisError as error:
            raise DependencyUnavailableError from error

    async def take(self, *, key: str) -> bytes | None:
        """Atomically consume and return the one-time bytes at ``key``, or ``None``.

        Raises ``DependencyUnavailableError`` when Redis does not complete the
        command.
        """
        try:
            return _binary_reply(await self._client.execute_command("GETDEL", key))
        except RedisError as error:
            raise DependencyUnavailableError from error

    async def delete(self, *, key: str) -> None:
        """Delete the session at ``key``, even if it has already expired.

        Raises ``DependencyUnavailableError`` when Redis does not confirm
        deletion.
        """
        try:
            result = await self._client.execute_command("DEL", key)
            _boolean_reply(result)
        except RedisError as error:
            raise DependencyUnavailableError from error

    async def replace(
        self, *, key: str, expected: bytes, value: bytes, ttl: int
    ) -> bool:
        """CAS an existing session in one atomic command; never revive logout.

        Return False on a stale/missing key; positive ``ttl`` bounds the update.

        Args:
            key (str): Namespaced session key.
            expected (bytes): Previously read private state.
            value (bytes): Replacement private state.
            ttl (int): Positive remaining absolute lifetime in seconds.

        Returns:
            bool: Whether the matching existing state was replaced.

        Raises:
            DependencyUnavailableError: Redis did not complete the script.
        """
        try:
            result = await self._client.execute_command(
                "EVAL", _REPLACE_EXISTING_SCRIPT, 1, key, expected, value, ttl
            )
        except RedisError as error:
            raise DependencyUnavailableError from error
        return _boolean_reply(result)


def _binary_reply(value: object) -> bytes | None:
    if value is not None and not isinstance(value, bytes):
        raise DependencyUnavailableError
    return value


def _boolean_reply(value: object) -> bool:
    if type(value) is not int or value not in (0, 1):
        raise DependencyUnavailableError
    return value == 1
