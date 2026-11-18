"""Readiness interaction contract, independent of transport and vendors."""

from typing import Final, Protocol

# Upper bound for any readiness deadline, whether for all probes or one probe.
MAX_READINESS_TIMEOUT_SECONDS: Final[float] = 60.0


class ProbeUnavailableError(Exception):
    """A dependency is temporarily unavailable; retry on the next health request.

    Adapters should translate known vendor availability failures with
    ``raise ProbeUnavailableError(...) from error``. Neither the message nor
    the cause is sent to clients or logged by this runtime.
    """


class ReadinessProbe(Protocol):
    """A consumer-owned async, cancellation-cooperative dependency check."""

    async def check(self) -> bool:
        """Return whether the dependency is available, without blocking the loop.

        Only ``True`` or ``False`` is valid, and checks may run concurrently and
        repeatedly. Raise ``ProbeUnavailableError`` for a known availability
        failure; any other exception is a defect that the runtime turns into a
        sanitized 500. Cancellation propagates and is not unavailability.
        """
        ...
