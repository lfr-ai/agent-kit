"""Text inference orchestration and its single safe diagnostic boundary."""

import logging

from platform_kit_runtime.core.ai import (
    AIError,
    TextGenerator,
    TextRequest,
    TextResult,
)

_LOGGER = logging.getLogger(__name__)


class TextGenerationService:
    """Delegate inference through a port without importing a provider SDK."""

    def __init__(self, *, generator: TextGenerator) -> None:
        """Bind the caller-owned text generator.

        Args:
            generator (TextGenerator): Port whose caller owns configuration and lifetime.
        """
        self._generator = generator

    async def generate(self, *, request: TextRequest) -> TextResult:
        """Return the provider's text response and log a handled failure once.

        A typed ``AIError`` is logged with its fixed code only and re-raised,
        without fallback or repair; caller cancellation propagates unlogged.
        """
        try:
            return await self._generator.generate(request=request)
        except AIError as error:
            _LOGGER.warning("ai.inference_failed", extra={"ai_failure": error.code})
            raise
