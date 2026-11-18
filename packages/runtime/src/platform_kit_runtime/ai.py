"""Public opt-in AI facade and composition root; import does not load LiteLLM."""

from typing import Final

from platform_kit_runtime.application.ai import TextGenerationService
from platform_kit_runtime.core.ai import (
    AIAuthenticationError,
    AIConfigurationError,
    AIDependencyError,
    AIError,
    AIFinishReason,
    AIMessage,
    AIProtocolError,
    AIRole,
    AIUnavailableError,
    AIUsage,
    AsyncTokenProvider,
    TextGenerationConfig,
    TextGenerator,
    TextRequest,
    TextResult,
)

__all__: Final[list[str]] = [
    "AIAuthenticationError",
    "AIConfigurationError",
    "AIDependencyError",
    "AIError",
    "AIFinishReason",
    "AIMessage",
    "AIProtocolError",
    "AIRole",
    "AIUnavailableError",
    "AIUsage",
    "AsyncTokenProvider",
    "TextGenerationConfig",
    "TextGenerator",
    "TextRequest",
    "TextResult",
    "create_text_generator",
]


def create_text_generator(
    *, config: TextGenerationConfig, token_provider: AsyncTokenProvider | None = None
) -> TextGenerator:
    """Return an async text generator composed over the optional LiteLLM SDK.

    It is a plain interface, not an HTTP endpoint or agent, and sets no SDK
    settings or callbacks globally. SDK loading can raise ``AIDependencyError``
    when the optional dependency is unavailable or incompatible.

    Args:
        config (TextGenerationConfig): Explicit provider and authentication settings.
        token_provider (AsyncTokenProvider | None): Required only with Entra mode.
            Called for every inference within its total deadline; the caller owns
            credential renewal and cleanup, including failed application startup.

    Returns:
        TextGenerator: Typed text-only inference with sanitized errors.

    Raises:
        AIConfigurationError: Authentication mode and token provider disagree.
    """
    if config.entra_authentication != (token_provider is not None):
        raise AIConfigurationError
    if token_provider is not None and not callable(token_provider):
        raise AIConfigurationError
    from platform_kit_runtime.infrastructure.litellm import (  # noqa: PLC0415 - SDK adapter is opt-in composition only
        LiteLLMTextGenerator,
        load_litellm,
    )

    return TextGenerationService(
        generator=LiteLLMTextGenerator(
            config=config, sdk=load_litellm(), token_provider=token_provider
        )
    )
