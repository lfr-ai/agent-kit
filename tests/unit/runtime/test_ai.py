import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest

from platform_kit_runtime.ai import (
    AIConfigurationError,
    AIFinishReason,
    AIMessage,
    AIRole,
    AIUsage,
    TextGenerationConfig,
    TextRequest,
    TextResult,
)
from platform_kit_runtime.application.ai import TextGenerationService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_key": "secret"},
        {"api_key": ""},
        {"entra_authentication": "true"},
        {"entra_authentication": False},
        {"model": "azure/deployment"},
        {"model": "openai/"},
        {"api_base": None},
        {"api_base": "https://provider.invalid"},
        {"api_base": "http://localhost/openai/v1/"},
        {"api_version": "2024-10-21"},
    ],
)
def test_entra_requires_keyless_explicit_openai_v1(
    overrides: dict[str, object],
) -> None:
    config = TextGenerationConfig(
        model="openai/deployment",
        api_base="https://provider.invalid/openai/v1/",
        entra_authentication=True,
    )
    with pytest.raises(AIConfigurationError, match="AI configuration is invalid"):
        replace(config, **overrides)


def test_omitted_key_never_enables_ambient_authentication() -> None:
    with pytest.raises(AIConfigurationError):
        TextGenerationConfig(model="openai/deployment")


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": ""},
        {"model": "secret\nmodel"},
        {"api_key": ""},
        {"api_base": "https://user:secret@private.invalid"},
        {"api_base": "https://private.invalid?key=secret"},
        {"api_base": "https://private.invalid/#secret"},
        {"api_base": "http://private.invalid"},
        {"api_base": "file:///secret"},
        {"api_base": "https://private.invalid:bad"},
        {"api_version": ""},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": True},
        {"timeout_seconds": 301},
        {"timeout_seconds": 10**1000},
        {"num_retries": -1},
        {"num_retries": True},
        {"num_retries": 4},
    ],
)
def test_invalid_configuration_is_safe(overrides: dict[str, object]) -> None:
    config = TextGenerationConfig(model="openai/test", api_key="secret")
    with pytest.raises(AIConfigurationError, match="AI configuration is invalid"):
        replace(config, **overrides)


@pytest.mark.parametrize(
    "fields",
    [
        {"messages": ()},
        {"messages": []},
        {"messages": ("secret",)},
        {
            "messages": (AIMessage(role=AIRole.USER, content="hello"),),
            "max_output_tokens": 0,
        },
        {
            "messages": (AIMessage(role=AIRole.USER, content="hello"),),
            "max_output_tokens": True,
        },
    ],
)
def test_invalid_request_fails_before_dispatch(fields: dict[str, object]) -> None:
    request = TextRequest(messages=(AIMessage(role=AIRole.USER, content="hello"),))
    with pytest.raises(AIConfigurationError):
        replace(request, **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"messages": None},
        {"max_output_tokens": "5"},
        {"max_output_tokens": 1.0},
        {"messages": None, "max_output_tokens": "5"},
    ],
)
def test_untyped_request_fields_fail_closed(fields: dict[str, object]) -> None:
    request = TextRequest(messages=(AIMessage(role=AIRole.USER, content="hello"),))
    with pytest.raises(AIConfigurationError, match="AI configuration is invalid"):
        replace(request, **fields)


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout_seconds": "30"},
        {"timeout_seconds": None},
        {"num_retries": "1"},
        {"num_retries": 1.0},
        {"timeout_seconds": "30", "num_retries": None},
    ],
)
def test_untyped_limits_fail_closed(overrides: dict[str, object]) -> None:
    config = TextGenerationConfig(model="openai/test", api_key="secret")
    with pytest.raises(AIConfigurationError, match="AI configuration is invalid"):
        replace(config, **overrides)


@pytest.mark.parametrize(("timeout", "retries"), [(300, 3), (0.001, 0), (300.0, 1)])
def test_limit_bounds_are_inclusive(timeout: float, retries: int) -> None:
    config = TextGenerationConfig(
        model="openai/test",
        api_key="secret",
        timeout_seconds=timeout,
        num_retries=retries,
    )
    assert (config.timeout_seconds, config.num_retries) == (timeout, retries)


def test_records_are_immutable_and_reprs_exclude_sensitive_values() -> None:
    config = TextGenerationConfig(
        model="azure/private-deployment",
        api_key="secret-key",
        api_base="https://private.invalid",
        api_version="private-version",
    )
    message = AIMessage(role=AIRole.USER, content="private-prompt")
    request = TextRequest(messages=(message,))
    assert "private" not in repr(config)
    assert "secret" not in repr(config)
    assert "private" not in repr(request)
    with pytest.raises(FrozenInstanceError):
        setattr(message, "content", "changed")  # noqa: B010 - frozen-record test


def test_message_rejects_non_text_and_untyped_role() -> None:
    message = AIMessage(role=AIRole.USER, content="private-prompt")
    with pytest.raises(AIConfigurationError):
        replace(message, role="user")
    with pytest.raises(AIConfigurationError):
        replace(message, content=None)


def test_service_accepts_a_port_without_optional_sdk() -> None:
    result = TextResult(
        text="answer",
        finish_reason=AIFinishReason.STOP,
        usage=AIUsage(input_tokens=1, output_tokens=2, total_tokens=3),
    )

    class FakeGenerator:
        async def generate(self, *, request: TextRequest) -> TextResult:
            assert request.messages
            return result

    service = TextGenerationService(generator=FakeGenerator())
    assert (
        asyncio.run(
            service.generate(
                request=TextRequest(
                    messages=(AIMessage(role=AIRole.USER, content="hello"),)
                )
            )
        )
        is result
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:8080/v1",
        "http://127.0.0.1:8080/v1",
        "http://[::1]:8080/v1",
        "https://private.invalid/v1",
    ],
)
def test_local_and_on_premises_endpoints_are_explicit(endpoint: str) -> None:
    assert (
        TextGenerationConfig(
            model="openai/test", api_key="synthetic", api_base=endpoint
        ).api_base
        == endpoint
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https:///v1",
        "https://user@private.invalid",
        "https://:synthetic@private.invalid",
        "https://private.invalid:0",
        "http://localhost:0/v1",
        "https://private.invalid/\x00",
        "https://private.invalid/a b",
        " https://private.invalid",
    ],
)
def test_endpoint_rejects_each_unsafe_part(endpoint: str) -> None:
    with pytest.raises(AIConfigurationError, match="AI configuration is invalid"):
        TextGenerationConfig(
            model="openai/test", api_key="synthetic", api_base=endpoint
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://private.invalid?",
        "https://private.invalid#",
        "https://private.invalid/v1?",
        "http://localhost:8080/v1#",
        "https://private.invalid/?#",
    ],
)
def test_endpoint_rejects_empty_query_or_fragment(endpoint: str) -> None:
    with pytest.raises(AIConfigurationError, match="AI configuration is invalid"):
        TextGenerationConfig(
            model="openai/test", api_key="synthetic", api_base=endpoint
        )
