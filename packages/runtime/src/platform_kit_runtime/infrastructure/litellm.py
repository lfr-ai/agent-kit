"""Opt-in LiteLLM boundary; no global SDK configuration or raw exception chains."""

import asyncio
from http import HTTPStatus
from importlib import import_module
from typing import Protocol, runtime_checkable

from platform_kit_runtime.core.ai import (
    AIAuthenticationError,
    AIConfigurationError,
    AIDependencyError,
    AIError,
    AIFinishReason,
    AIProtocolError,
    AIRole,
    AIUnavailableError,
    AIUsage,
    AsyncTokenProvider,
    TextGenerationConfig,
    TextRequest,
    TextResult,
)
from platform_kit_runtime.core.telemetry import InferenceTracer, SilentInferenceTracer
from platform_kit_runtime.core.validation import is_nonblank


@runtime_checkable
class LiteLLMSDK(Protocol):
    """Minimal released SDK surface, isolated from its dynamically typed exports."""

    ModelResponse: type[object]
    AuthenticationError: type[Exception]
    PermissionDeniedError: type[Exception]
    BadRequestError: type[Exception]
    NotFoundError: type[Exception]
    UnprocessableEntityError: type[Exception]
    UnsupportedParamsError: type[Exception]
    Timeout: type[Exception]
    APIConnectionError: type[Exception]
    ServiceUnavailableError: type[Exception]
    InternalServerError: type[Exception]
    RateLimitError: type[Exception]
    APIError: type[Exception]

    async def acompletion(self, **kwargs: object) -> object:
        """Return one untrusted SDK completion for the explicit ``kwargs``."""
        ...


@runtime_checkable
class _Response(Protocol):
    def model_dump(self) -> object: ...


def load_litellm() -> LiteLLMSDK:
    """Return the optional SDK module; raise ``AIDependencyError`` if unusable."""
    try:
        sdk = import_module("litellm")
    except Exception:  # noqa: BLE001 - optional import failures must not expose vendor diagnostics
        sdk = None
    if not isinstance(sdk, LiteLLMSDK):
        raise AIDependencyError from AIError()
    return sdk


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AIProtocolError
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise AIProtocolError
        result[key] = item
    return result


def _tokens(value: object) -> int:
    if type(value) is not int or value < 0:
        raise AIProtocolError
    return value


def _usage(value: object) -> AIUsage:
    data = _mapping(value)
    prompt = _tokens(data.get("prompt_tokens"))
    completion = _tokens(data.get("completion_tokens"))
    total = _tokens(data.get("total_tokens"))
    if total != prompt + completion:
        raise AIProtocolError
    return AIUsage(input_tokens=prompt, output_tokens=completion, total_tokens=total)


def _has_non_text_output(message: dict[str, object]) -> bool:
    return (
        message.get("tool_calls") not in (None, [])
        or message.get("function_call") is not None
        or message.get("refusal") is not None
    )


def _text_choice(value: object) -> tuple[str, AIFinishReason]:
    if not isinstance(value, list) or len(value) != 1:
        raise AIProtocolError
    choice = _mapping(value[0])
    message = _mapping(choice.get("message"))
    content = message.get("content")
    role = message.get("role")
    non_assistant_text = role != AIRole.ASSISTANT or not isinstance(content, str)
    # Output fields are compared only for an assistant text reply, as before.
    if non_assistant_text or _has_non_text_output(message):
        raise AIProtocolError
    reason = choice.get("finish_reason")
    if reason == AIFinishReason.STOP:
        return content, AIFinishReason.STOP
    if reason == AIFinishReason.LENGTH:
        return content, AIFinishReason.LENGTH
    raise AIProtocolError


def _classify_status(error: Exception) -> AIError | None:
    status = getattr(error, "status_code", None)
    if type(status) is not int:
        return None
    if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
        return AIAuthenticationError()
    if (
        status in (HTTPStatus.REQUEST_TIMEOUT, HTTPStatus.TOO_MANY_REQUESTS)
        or status >= HTTPStatus.INTERNAL_SERVER_ERROR
    ):
        return AIUnavailableError()
    return None


class LiteLLMTextGenerator:
    """Text-only SDK adapter with a cooperative total deadline."""

    def __init__(
        self,
        *,
        config: TextGenerationConfig,
        sdk: LiteLLMSDK,
        tracer: InferenceTracer | None = None,
        token_provider: AsyncTokenProvider | None = None,
    ) -> None:
        """Bind validated configuration and the injected SDK surface.

        Args:
            config (TextGenerationConfig): Explicit validated provider settings.
            sdk (LiteLLMSDK): Loaded SDK with the required callable/error surface.
            tracer (InferenceTracer | None): Content-free span recorder for each
                call; ``None`` records nothing.
            token_provider (AsyncTokenProvider | None): Caller-owned renewable
                bearer token source; validated by the composition root.
        """
        self._config = config
        self._sdk = sdk
        self._tracer = SilentInferenceTracer() if tracer is None else tracer
        self._token_provider = token_provider

    def _classify(self, error: Exception) -> AIError:
        if isinstance(error, AIError):
            return error
        status_failure = _classify_status(error)
        if status_failure is not None:
            return status_failure
        if isinstance(
            error, (self._sdk.AuthenticationError, self._sdk.PermissionDeniedError)
        ):
            return AIAuthenticationError()
        if isinstance(
            error,
            (
                self._sdk.BadRequestError,
                self._sdk.NotFoundError,
                self._sdk.UnprocessableEntityError,
                self._sdk.UnsupportedParamsError,
            ),
        ):
            return AIConfigurationError()
        if isinstance(
            error,
            (
                TimeoutError,
                self._sdk.Timeout,
                self._sdk.APIConnectionError,
                self._sdk.ServiceUnavailableError,
                self._sdk.InternalServerError,
                self._sdk.RateLimitError,
                self._sdk.APIError,
            ),
        ):
            return AIUnavailableError()
        return AIProtocolError()

    async def _api_key(self) -> str | None:
        if self._token_provider is None:
            return self._config.api_key
        try:
            token = await self._token_provider()
        except TimeoutError:
            raise
        except Exception:  # noqa: BLE001 - token providers can expose credential-bearing vendor diagnostics
            token = None
        if not isinstance(token, str) or not is_nonblank(token):
            raise AIAuthenticationError from AIError()
        return token

    def _arguments(
        self, *, request: TextRequest, api_key: str | None
    ) -> dict[str, object]:
        arguments: dict[str, object] = {
            "model": self._config.model,
            "api_key": api_key,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": request.max_output_tokens,
            "timeout": self._config.timeout_seconds,
            "num_retries": self._config.num_retries,
            "stream": False,
            "n": 1,
            "no-log": True,
        }
        if self._config.api_base is not None:
            arguments["api_base"] = self._config.api_base
        if self._config.api_version is not None:
            arguments["api_version"] = self._config.api_version
        return arguments

    def _result(self, response: object) -> TextResult:
        if not isinstance(response, self._sdk.ModelResponse) or not isinstance(
            response, _Response
        ):
            raise AIProtocolError
        data = _mapping(response.model_dump())
        text, finish_reason = _text_choice(data.get("choices"))
        return TextResult(
            text=text,
            finish_reason=finish_reason,
            usage=_usage(data.get("usage")),
        )

    async def generate(self, *, request: TextRequest) -> TextResult:
        """Return validated text for ``request`` within a deadline, or a typed error.

        Token acquisition failures become ``AIAuthenticationError``; token
        timeouts share the inference deadline and become ``AIUnavailableError``.
        SDK failures become ``AIConfigurationError``, ``AIAuthenticationError``,
        ``AIUnavailableError`` (deadline, throttling, transport or service) or
        ``AIProtocolError`` (unexpected failure or a malformed, non-text
        result). Cancellation propagates unchanged and is never retried here.
        """
        with self._tracer.span(
            model=self._config.model, max_output_tokens=request.max_output_tokens
        ) as span:
            try:
                async with asyncio.timeout(self._config.timeout_seconds):
                    api_key = await self._api_key()
                    response = await self._sdk.acompletion(
                        **self._arguments(request=request, api_key=api_key)
                    )
                    result = self._result(response)
            except Exception as error:  # noqa: BLE001 - all SDK exceptions require a content-free boundary
                failure = self._classify(error)
            else:
                span.succeeded(result=result)
                return result
            span.failed(error=failure)
        raise failure from AIError()
