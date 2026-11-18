"""Shared fixed-window counters in Redis via one atomic script (``ratelimit`` extra)."""

from collections.abc import Awaitable
import math
from typing import Protocol

from platform_kit_runtime.core.limits import MILLISECONDS_PER_SECOND
from platform_kit_runtime.core.rate_limit import RateLimitStoreError, WindowCount

_DEFAULT_PREFIX = "platform-kit:rate-limit:"
_REPLY_LENGTH = 2  # {count, ttl}
# INCR and expiry run atomically; a key without expiry is repaired, never immortal.
_HIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('PTTL', KEYS[1])
if count == 1 or ttl < 0 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


class RedisCommands(Protocol):
    """Minimal asynchronous Redis command surface; ``redis.asyncio.Redis`` fits."""

    def execute_command(self, *args: str | bytes | int) -> Awaitable[object]:
        """Return the untrusted reply to ``args``; the adapter validates its type."""
        ...


class RedisRateLimitStore:
    """Counters shared by every replica; the caller owns the client's lifecycle.

    Configure socket timeouts on the client: a slow Redis delays requests until
    the client gives up, then the runtime fails open.
    """

    def __init__(self, *, client: RedisCommands, prefix: str = _DEFAULT_PREFIX) -> None:
        """Bind a caller-owned client; needs the ``ratelimit`` extra to import.

        Args:
            client (RedisCommands): Async client with bounded timeouts and TLS.
            prefix (str): Key namespace separating apps that share one Redis.
        """
        from redis.exceptions import RedisError  # noqa: PLC0415 - the optional extra loads only when this store is composed

        self._client = client
        self._prefix = prefix
        self._vendor_error: type[Exception] = RedisError

    async def hit(self, *, key: str, window_seconds: int) -> WindowCount:
        """Increment and expire ``key`` in one atomic script.

        Args:
            key (str): Pseudonymous client key, namespaced with the prefix.
            window_seconds (int): Positive window length for a new window.

        Returns:
            WindowCount: The updated count and the time until the window resets.

        Raises:
            RateLimitStoreError: Redis failed or returned an unexpected reply.
        """
        try:
            reply = await self._client.execute_command(
                "EVAL",
                _HIT_SCRIPT,
                1,
                self._prefix + key,
                window_seconds * MILLISECONDS_PER_SECOND,
            )
        except self._vendor_error as error:
            raise RateLimitStoreError from error
        return _window(reply=reply)


def _window(*, reply: object) -> WindowCount:
    if not isinstance(reply, list) or len(reply) != _REPLY_LENGTH:
        raise RateLimitStoreError
    count, ttl = reply
    if type(count) is not int or type(ttl) is not int or count < 1 or ttl < 0:
        raise RateLimitStoreError
    return WindowCount(
        count=count,
        reset_seconds=max(math.ceil(ttl / MILLISECONDS_PER_SECOND), 1),
    )
