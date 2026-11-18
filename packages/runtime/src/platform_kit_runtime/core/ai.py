"""Provider-neutral, immutable text inference contracts; stdlib only."""

from dataclasses import dataclass, field
from enum import StrEnum, auto, unique
from typing import Protocol

from platform_kit_runtime.core.limits import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MAX_REQUEST_TIMEOUT_SECONDS,
    MAX_SDK_RETRIES,
)
from platform_kit_runtime.core.validation import (
    is_bounded_seconds,
    is_int_in_range,
    is_nonblank,
    is_openai_v1_deployment,
    is_service_endpoint,
)

_DEFAULT_MAX_OUTPUT_TOKENS = 1024


class AIError(Exception):
    """Base inference failure with a fixed, content-free message."""

    message = "AI inference failed."
    code = "ai_failure"

    def __init__(self) -> None:
        """Construct an error without accepting sensitive diagnostic values."""
        super().__init__(self.message)


class AIConfigurationError(AIError):
    """Invalid local settings/request, or the provider rejected their configuration."""

    message = "AI configuration is invalid."
    code = "ai_configuration"


class AIAuthenticationError(AIError):
    """The provider rejected authentication or permission."""

    message = "AI authentication failed."
    code = "ai_authentication"


class AIUnavailableError(AIError):
    """The deadline elapsed, or the provider is unreachable, throttled or unavailable."""

    message = "AI provider is unavailable."
    code = "ai_unavailable"


class AIProtocolError(AIError):
    """The SDK failed unexpectedly or did not return the required text response."""

    message = "AI provider returned an invalid text response."
    code = "ai_protocol"


class AIDependencyError(AIError):
    """The optional AI SDK is missing or incompatible."""

    message = "The optional AI dependency is unavailable."
    code = "ai_dependency"


@unique
class AIRole(StrEnum):
    """Supported text conversation roles."""

    SYSTEM = auto()
    USER = auto()
    ASSISTANT = auto()


@unique
class AIFinishReason(StrEnum):
    """Successful text outcomes; ``length`` explicitly indicates truncation."""

    STOP = auto()
    LENGTH = auto()


@dataclass(frozen=True, kw_only=True, slots=True)
class AIMessage:
    """One text message.

    Attributes:
        role (AIRole): The speaker; tools and multimodal messages are unsupported.
        content (str): Text sent to the selected provider; omitted from repr.
    """

    role: AIRole
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        """Validate the message without copying its content into diagnostics.

        Raises:
            AIConfigurationError: The role or content has an invalid type.
        """
        if not isinstance(self.role, AIRole) or not isinstance(self.content, str):
            raise AIConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class TextRequest:
    """A bounded text-generation request.

    Attributes:
        messages (tuple[AIMessage, ...]): Nonempty immutable conversation.
        max_output_tokens (int): Positive output token cap passed to the SDK.
    """

    messages: tuple[AIMessage, ...] = field(repr=False)
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        """Reject mutable messages and nonpositive or boolean token limits.

        Raises:
            AIConfigurationError: Messages or the token cap are invalid.
        """
        # Each group short-circuits on its type check before inspecting values.
        valid_messages = (
            isinstance(self.messages, tuple)
            and bool(self.messages)
            and all(isinstance(message, AIMessage) for message in self.messages)
        )
        positive_token_cap = (
            type(self.max_output_tokens) is int and self.max_output_tokens > 0
        )
        if not valid_messages or not positive_token_cap:
            raise AIConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class TextGenerationConfig:
    """Explicit SDK provider settings; no environment discovery by the runtime.

    Attributes:
        model (str): LiteLLM model selector, for example ``azure/deployment``.
        api_key (str | None): Caller-resolved API key, never included in repr or
            errors. Must be absent when ``entra_authentication`` is enabled.
        api_base (str | None): Optional HTTPS endpoint; HTTP only for loopback.
        api_version (str | None): Optional provider API version, notably Azure.
        timeout_seconds (float): Positive finite overall and SDK deadline, at
            most 300 seconds, including SDK retries.
        num_retries (int): SDK retry cap from zero to three; defaults to zero.
        entra_authentication (bool): Require a caller-owned async token provider,
            an ``openai/<deployment>`` model and an HTTPS ``/openai/v1/`` base.
            No API version or key is accepted. Defaults to ``False``.
    """

    model: str = field(repr=False)
    api_key: str | None = field(default=None, repr=False)
    api_base: str | None = field(default=None, repr=False)
    api_version: str | None = field(default=None, repr=False)
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    num_retries: int = 0
    entra_authentication: bool = False

    def __post_init__(self) -> None:
        """Validate settings before optional SDK import or network access.

        Raises:
            AIConfigurationError: A supplied value is invalid.
        """
        if not is_nonblank(self.model):
            raise AIConfigurationError
        if self.api_base is not None and not is_service_endpoint(
            self.api_base, allow_loopback_http=True
        ):
            raise AIConfigurationError
        if self.api_version is not None and not is_nonblank(self.api_version):
            raise AIConfigurationError
        bounded_timeout = is_bounded_seconds(
            self.timeout_seconds, maximum=MAX_REQUEST_TIMEOUT_SECONDS
        )
        bounded_retries = is_int_in_range(self.num_retries, low=0, high=MAX_SDK_RETRIES)
        if not bounded_timeout or not bounded_retries:
            raise AIConfigurationError
        self._validate_authentication()

    def _validate_authentication(self) -> None:
        if not isinstance(self.entra_authentication, bool):
            raise AIConfigurationError
        if not self.entra_authentication:
            if not is_nonblank(self.api_key):
                raise AIConfigurationError
            return
        self._validate_entra_endpoint()

    def _validate_entra_endpoint(self) -> None:
        if self.api_key is not None or self.api_version is not None:
            raise AIConfigurationError
        if not is_openai_v1_deployment(model=self.model, api_base=self.api_base):
            raise AIConfigurationError


class AsyncTokenProvider(Protocol):
    """Caller-owned renewable authentication port; never closed by the runtime."""

    async def __call__(self) -> str:
        """Return a current bearer token; adapters turn failures into safe errors."""
        ...


@dataclass(frozen=True, kw_only=True, slots=True)
class AIUsage:
    """SDK-reported token counts, not estimates.

    Attributes:
        input_tokens (int): Nonnegative prompt count.
        output_tokens (int): Nonnegative completion count.
        total_tokens (int): Sum of prompt and completion counts.
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, kw_only=True, slots=True)
class TextResult:
    """Validated text response; no raw SDK response or provider metadata.

    Attributes:
        text (str): Generated content, omitted from repr.
        finish_reason (AIFinishReason): Stop or explicit token-limit truncation.
        usage (AIUsage): Required provider-reported usage, never fabricated.
    """

    text: str = field(repr=False)
    finish_reason: AIFinishReason
    usage: AIUsage


class TextGenerator(Protocol):
    """Async provider-neutral text inference port."""

    async def generate(self, *, request: TextRequest) -> TextResult:
        """Return one text response with its finish reason and reported usage.

        Implementations raise ``AIConfigurationError``, ``AIAuthenticationError``,
        ``AIUnavailableError`` or ``AIProtocolError``; caller cancellation
        propagates unchanged.
        """
        ...
