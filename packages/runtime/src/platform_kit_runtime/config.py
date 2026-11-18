"""Explicit configuration values; no environment or file discovery."""

from dataclasses import dataclass

from platform_kit_runtime.core.rate_limit import RateLimitPolicy
from platform_kit_runtime.core.readiness import MAX_READINESS_TIMEOUT_SECONDS
from platform_kit_runtime.core.validation import is_bounded_seconds, is_int_in_range

_DEFAULT_READINESS_TIMEOUT_SECONDS = 2.0
_MAX_TRUSTED_PROXY_HOPS = 16


@dataclass(frozen=True, kw_only=True, slots=True)
class RuntimeConfig:
    """Validated, immutable runtime settings.

    Attributes:
        readiness_timeout_seconds (float): Total cooperative deadline for all
            probes per request, greater than zero and at most 60 seconds.
            Defaults to two seconds. Booleans and non-finite values are invalid.
        rate_limit (RateLimitPolicy | None): Per-client limit for non-health
            HTTP requests; ``None``, the default, disables rate limiting.
        trusted_proxy_hops (int): Reverse proxies, 0 to 16, in front of the app
            that append to ``X-Forwarded-For``. Rate limiting keys anonymous
            clients by the address those proxies saw. Defaults to ``0``, which
            ignores the header and uses the connection's peer address.
        tracing (bool): Export HTTP and inference spans configured by standard
            ``OTEL_*`` variables when the ``telemetry`` extra is installed.
            Defaults to ``False``.
    """

    readiness_timeout_seconds: float = _DEFAULT_READINESS_TIMEOUT_SECONDS
    rate_limit: RateLimitPolicy | None = None
    trusted_proxy_hops: int = 0
    tracing: bool = False

    def __post_init__(self) -> None:
        """Reject invalid values before any application is built.

        Raises:
            ValueError: The timeout or proxy hop count is not a number in its
                allowed range. The diagnostic names the field, never the value.
            TypeError: ``rate_limit`` or ``tracing`` has the wrong type.
        """
        if not is_bounded_seconds(
            self.readiness_timeout_seconds, maximum=MAX_READINESS_TIMEOUT_SECONDS
        ):
            message = (
                "readiness_timeout_seconds must be finite and in "
                f"(0, {MAX_READINESS_TIMEOUT_SECONDS:g}]."
            )
            raise ValueError(message)
        if not isinstance(self.rate_limit, (RateLimitPolicy, type(None))):
            message = "rate_limit must be a RateLimitPolicy or None."
            raise TypeError(message)
        if not is_int_in_range(
            self.trusted_proxy_hops, low=0, high=_MAX_TRUSTED_PROXY_HOPS
        ):
            message = f"trusted_proxy_hops must be an integer in [0, {_MAX_TRUSTED_PROXY_HOPS}]."
            raise ValueError(message)
        if not isinstance(self.tracing, bool):
            message = "tracing must be a boolean."
            raise TypeError(message)
