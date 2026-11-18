import asyncio

import pytest

from platform_kit_runtime.application.readiness import (
    ReadinessFailure,
    ReadinessService,
    ReadinessUnavailableError,
)

pytestmark = pytest.mark.unit


def test_timeout_error_preserves_cause_and_safe_reason() -> None:
    class WaitingProbe:
        async def check(self) -> bool:
            await asyncio.Event().wait()
            return True

    service = ReadinessService(probes=(WaitingProbe(),), timeout_seconds=0.01)

    with pytest.raises(ReadinessUnavailableError) as caught:
        asyncio.run(service.check())

    assert caught.value.reason is ReadinessFailure.TIMEOUT
    assert isinstance(caught.value.__cause__, TimeoutError)
