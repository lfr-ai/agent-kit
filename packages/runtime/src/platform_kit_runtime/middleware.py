"""Public request correlation, access logging and rate-limit store API.

``create_app`` installs the middleware itself; this module exposes what callers
configure: log enrichment, the rate-limit policy and the counter stores.
Importing it loads no optional SDKs.
"""

from typing import Final

from platform_kit_runtime.core.correlation import REQUEST_ID_HEADER, current_request_id
from platform_kit_runtime.core.rate_limit import (
    RateLimitPolicy,
    RateLimitStore,
    RateLimitStoreError,
    WindowCount,
)
from platform_kit_runtime.infrastructure.rate_limit.memory import InMemoryRateLimitStore
from platform_kit_runtime.infrastructure.rate_limit.redis import (
    RedisCommands,
    RedisRateLimitStore,
)
from platform_kit_runtime.infrastructure.telemetry import RequestContextFilter
from platform_kit_runtime.presentation.middleware import ACCESS_LOGGER_NAME

__all__: Final[list[str]] = [
    "ACCESS_LOGGER_NAME",
    "REQUEST_ID_HEADER",
    "InMemoryRateLimitStore",
    "RateLimitPolicy",
    "RateLimitStore",
    "RateLimitStoreError",
    "RedisCommands",
    "RedisRateLimitStore",
    "RequestContextFilter",
    "WindowCount",
    "current_request_id",
]
