"""Fixed-window rate-limit policy, decisions and the counter store port."""

from dataclasses import dataclass
from typing import Protocol

from platform_kit_runtime.core.validation import is_int_in_range

_MAX_LIMIT = 1_000_000
_MAX_WINDOW_SECONDS = 86_400


class RateLimitStoreError(Exception):
    """The counter store could not count a request.

    Adapters raise it ``from`` the vendor error. The runtime fails open: the
    request proceeds without quota headers and one warning is logged.
    """


@dataclass(frozen=True, kw_only=True, slots=True)
class WindowCount:
    """A store's count for one key in its current fixed window.

    Attributes:
        count (int): Requests counted in this window, including the current one.
        reset_seconds (int): Whole seconds, at least one, until the window resets.
    """

    count: int
    reset_seconds: int


@dataclass(frozen=True, kw_only=True, slots=True)
class RateLimitDecision:
    """Outcome of counting one request against a policy.

    Attributes:
        allowed (bool): Whether the request is within the policy's limit.
        limit (int): Requests allowed per window.
        window_seconds (int): Fixed window length in seconds.
        remaining (int): Requests left in the current window, never negative.
        reset_seconds (int): Whole seconds until the current window resets.
    """

    allowed: bool
    limit: int
    window_seconds: int
    remaining: int
    reset_seconds: int


@dataclass(frozen=True, kw_only=True, slots=True)
class RateLimitPolicy:
    """Allow at most ``limit`` requests per client key in each fixed window.

    Attributes:
        limit (int): Requests allowed per window, from 1 to 1,000,000.
        window_seconds (int): Window length in seconds, from 1 to 86,400 (a day).
    """

    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        """Reject booleans, non-integers and out-of-range values.

        Raises:
            ValueError: A field is invalid; the message names the field, never
                the supplied value.
        """
        if not is_int_in_range(self.limit, low=1, high=_MAX_LIMIT):
            message = f"limit must be an integer in [1, {_MAX_LIMIT}]."
            raise ValueError(message)
        if not is_int_in_range(self.window_seconds, low=1, high=_MAX_WINDOW_SECONDS):
            message = (
                f"window_seconds must be an integer in [1, {_MAX_WINDOW_SECONDS}]."
            )
            raise ValueError(message)

    def decide(self, *, window: WindowCount) -> RateLimitDecision:
        """Compare a store's window count with this policy."""
        return RateLimitDecision(
            allowed=window.count <= self.limit,
            limit=self.limit,
            window_seconds=self.window_seconds,
            remaining=max(self.limit - window.count, 0),
            reset_seconds=window.reset_seconds,
        )


class RateLimitStore(Protocol):
    """Atomic fixed-window counter shared by every request to one app."""

    async def hit(self, *, key: str, window_seconds: int) -> WindowCount:
        """Count one request for ``key``; a window starts at its first request.

        Args:
            key (str): Pseudonymous client key; never a raw address or principal.
            window_seconds (int): Positive window length for a new window.

        Returns:
            WindowCount: The updated count and the time until the window resets.

        Raises:
            RateLimitStoreError: The counter is unavailable or replied invalidly.
        """
        ...
