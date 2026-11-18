"""Per-process fixed-window counters; each replica enforces its own limit."""

from collections.abc import Callable
import math
import time

from platform_kit_runtime.core.rate_limit import WindowCount

_DEFAULT_MAX_KEYS = 100_000


class InMemoryRateLimitStore:
    """Bounded in-process counters for a single event loop.

    With N replicas a client may receive up to N times the policy limit; use a
    shared store when that matters. At capacity, expired windows are evicted
    first, then the oldest window, which resets that client's count.
    """

    def __init__(
        self,
        *,
        max_keys: int = _DEFAULT_MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Bind the capacity and a monotonic clock.

        Args:
            max_keys (int): Positive number of concurrently tracked keys.
            clock (Callable[[], float]): Monotonic seconds; injectable for tests.

        Raises:
            ValueError: ``max_keys`` is not a positive integer.
        """
        if type(max_keys) is not int or max_keys < 1:
            message = "max_keys must be a positive integer."
            raise ValueError(message)
        self._max_keys = max_keys
        self._clock = clock
        # Insertion order equals window start order, so eviction scans the front.
        self._windows: dict[str, tuple[float, int]] = {}

    async def hit(self, *, key: str, window_seconds: int) -> WindowCount:
        """Count one request for ``key`` without awaiting, so it is atomic.

        Args:
            key (str): Pseudonymous client key.
            window_seconds (int): Positive window length for a new window.

        Returns:
            WindowCount: The updated count and the time until the window resets.
        """
        now = self._clock()
        expires, count = self._windows.get(key, (now, 0))
        if expires <= now:
            self._windows.pop(key, None)
            self._evict(now=now)
            expires, count = now + window_seconds, 0
        count += 1
        self._windows[key] = (expires, count)
        return WindowCount(count=count, reset_seconds=max(math.ceil(expires - now), 1))

    def _evict(self, *, now: float) -> None:
        while self._windows:
            oldest = next(iter(self._windows))
            expired = self._windows[oldest][0] <= now
            if not expired and len(self._windows) < self._max_keys:
                return
            del self._windows[oldest]
