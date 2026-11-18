"""Run consumer probes concurrently under one cooperative deadline."""

import asyncio
from enum import StrEnum, auto, unique

from platform_kit_runtime.core.readiness import ProbeUnavailableError, ReadinessProbe


@unique
class ReadinessFailure(StrEnum):
    """Safe diagnostic categories, never vendor details."""

    PROBE_FAILED = auto()
    TIMEOUT = auto()


class ReadinessUnavailableError(Exception):
    """Readiness failed with a safe, machine-readable reason."""

    def __init__(self, *, reason: ReadinessFailure) -> None:
        """Store the safe failure reason without vendor error text.

        Args:
            reason (ReadinessFailure): Probe failure or cooperative deadline expiry.
        """
        super().__init__("The runtime is not ready.")
        self.reason = reason


class ReadinessService:
    """Aggregate readiness; owns no clients, environment, or global state."""

    def __init__(
        self, *, probes: tuple[ReadinessProbe, ...], timeout_seconds: float
    ) -> None:
        """Bind the required checks and a validated deadline.

        Args:
            probes (tuple[ReadinessProbe, ...]): Consumer-owned checks. An explicit
                empty tuple declares no dependencies and is immediately ready.
            timeout_seconds (float): Positive finite deadline validated at
                composition. Includes every check, not a budget per check.
        """
        self._probes = probes
        self._timeout_seconds = timeout_seconds

    async def check(self) -> None:
        """Require all probes to succeed; cancel and await unfinished tasks.

        Completes without a result only when every dependency is ready, and
        raises ``ReadinessUnavailableError`` when a probe is unavailable or the
        deadline expires; timeout errors retain their cause. A probe defect or
        invalid return type propagates as an ``ExceptionGroup`` after sibling
        tasks are cancelled and awaited; caller cancellation propagates.
        """
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with asyncio.TaskGroup() as group:
                    tasks = [
                        group.create_task(_run_probe(probe=probe))
                        for probe in self._probes
                    ]
        except TimeoutError as error:
            raise ReadinessUnavailableError(reason=ReadinessFailure.TIMEOUT) from error
        if not all(task.result() for task in tasks):
            raise ReadinessUnavailableError(reason=ReadinessFailure.PROBE_FAILED)


async def _run_probe(*, probe: ReadinessProbe) -> bool:
    try:
        result = await probe.check()
    except ProbeUnavailableError:
        # Expected unavailability is a negative result, never a successful fallback.
        return False
    if not isinstance(result, bool):
        message = "ReadinessProbe.check must return bool."
        raise TypeError(message)
    return result
