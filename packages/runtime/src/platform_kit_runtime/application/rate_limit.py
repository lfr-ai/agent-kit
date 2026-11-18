"""Count requests per pseudonymous key and fail open when the store is down."""

import hashlib
import logging

from platform_kit_runtime.core.rate_limit import (
    RateLimitDecision,
    RateLimitPolicy,
    RateLimitStore,
    RateLimitStoreError,
)

_LOGGER = logging.getLogger(__name__)


class RateLimitService:
    """Apply one policy through one store; owns no clients or background work."""

    def __init__(self, *, policy: RateLimitPolicy, store: RateLimitStore) -> None:
        """Bind the validated policy and a caller-owned or per-app store.

        Args:
            policy (RateLimitPolicy): Limit and fixed window applied to every key.
            store (RateLimitStore): Atomic counter; per replica or shared.
        """
        self._policy = policy
        self._store = store

    async def check(self, *, key: str) -> RateLimitDecision | None:
        """Decide one request for ``key``; return ``None`` when the store fails.

        The key is hashed before it reaches the store, so stores never hold raw
        addresses or principals. A store failure is a deliberate fail-open: the
        request proceeds without quota information and one warning without
        vendor details is logged.
        """
        digest = hashlib.sha256(key.encode()).hexdigest()
        try:
            window = await self._store.hit(
                key=digest, window_seconds=self._policy.window_seconds
            )
        except RateLimitStoreError:
            _LOGGER.warning(
                "Rate limit store unavailable; request allowed",
                extra={"event": "runtime.rate_limit_unavailable"},
            )
            return None
        return self._policy.decide(window=window)
