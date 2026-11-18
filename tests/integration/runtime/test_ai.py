import asyncio
from copy import deepcopy
import logging
import subprocess
import sys
import traceback
from types import ModuleType
from typing import Final

import pytest

from platform_kit_runtime.ai import (
    AIAuthenticationError,
    AIConfigurationError,
    AIDependencyError,
    AIFinishReason,
    AIMessage,
    AIProtocolError,
    AIRole,
    AIUnavailableError,
    TextGenerationConfig,
    TextRequest,
    create_text_generator,
)

pytestmark = pytest.mark.integration

SENSITIVE_VALUE: Final[str] = "private-key-prompt-completion-endpoint"


class FakeSDKError(Exception):
    pass


class FakeAuthenticationError(FakeSDKError):
    pass


class FakeBadRequestError(FakeSDKError):
    pass


class FakeConnectionError(FakeSDKError):
    pass


class FakeResponse:
    def __init__(self, *, payload: object) -> None:
        self.payload = payload

    def model_dump(self) -> object:
        return self.payload


def response_payload() -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": "answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = ModuleType("litellm")
    for name in (
        "AuthenticationError",
        "PermissionDeniedError",
    ):
        setattr(module, name, FakeAuthenticationError)
    for name in (
        "BadRequestError",
        "NotFoundError",
        "UnprocessableEntityError",
        "UnsupportedParamsError",
    ):
        setattr(module, name, FakeBadRequestError)
    for name in (
        "Timeout",
        "APIConnectionError",
        "ServiceUnavailableError",
        "InternalServerError",
        "RateLimitError",
        "APIError",
    ):
        setattr(module, name, FakeConnectionError)
    vars(module).update(
        ModelResponse=FakeResponse,
        callbacks=[],
        api_key="unchanged",
        set_verbose=False,
    )
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def config() -> TextGenerationConfig:
    return TextGenerationConfig(model="openai/test", api_key=SENSITIVE_VALUE)


def request() -> TextRequest:
    return TextRequest(messages=(AIMessage(role=AIRole.USER, content=SENSITIVE_VALUE),))


def entra_config(*, timeout_seconds: float = 30) -> TextGenerationConfig:
    return TextGenerationConfig(
        model="openai/deployment",
        api_base="https://provider.invalid/openai/v1/",
        entra_authentication=True,
        timeout_seconds=timeout_seconds,
    )


def test_caller_owned_token_provider_is_renewed_per_call(sdk: ModuleType) -> None:
    calls: list[dict[str, object]] = []
    tokens = iter(("synthetic-first", "synthetic-renewed"))

    async def token_provider() -> str:
        return next(tokens)

    async def complete(**kwargs: object) -> FakeResponse:
        calls.append(kwargs)
        return FakeResponse(payload=response_payload())

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(
        config=entra_config(), token_provider=token_provider
    )

    async def scenario() -> None:
        for _ in range(2):
            assert (await generator.generate(request=request())).text == "answer"

    asyncio.run(scenario())
    assert [call["api_key"] for call in calls] == [
        "synthetic-first",
        "synthetic-renewed",
    ]
    assert all(call["model"] == "openai/deployment" for call in calls)
    assert all(call["stream"] is False for call in calls)
    assert all("api_version" not in call for call in calls)


@pytest.mark.parametrize("configured", [True, False])
def test_token_provider_and_auth_mode_must_match(configured: bool) -> None:
    async def token_provider() -> str:
        return SENSITIVE_VALUE

    with pytest.raises(AIConfigurationError):
        create_text_generator(
            config=entra_config() if configured else config(),
            token_provider=None if configured else token_provider,
        )


@pytest.mark.parametrize("failure", ["exception", "empty", "newline", "timeout"])
def test_token_failures_are_safe_and_logged_once(
    sdk: ModuleType, caplog: pytest.LogCaptureFixture, failure: str
) -> None:
    async def token_provider() -> str:
        if failure == "exception":
            raise RuntimeError(SENSITIVE_VALUE)
        if failure == "timeout":
            raise TimeoutError(SENSITIVE_VALUE)
        return "" if failure == "empty" else f"{SENSITIVE_VALUE}\n"

    async def complete(**kwargs: object) -> object:
        pytest.fail("Failed token acquisition must not call LiteLLM")

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(
        config=entra_config(), token_provider=token_provider
    )
    expected = AIUnavailableError if failure == "timeout" else AIAuthenticationError
    with pytest.raises(expected) as caught:
        asyncio.run(generator.generate(request=request()))
    assert SENSITIVE_VALUE not in "".join(traceback.format_exception(caught.value))
    assert SENSITIVE_VALUE not in caplog.text
    assert len(caplog.records) == 1
    assert vars(caplog.records[0])["ai_failure"] == caught.value.code


@pytest.mark.parametrize("cancel", [True, False])
def test_token_acquisition_shares_deadline_and_cancellation(
    sdk: ModuleType, caplog: pytest.LogCaptureFixture, cancel: bool
) -> None:
    finished: list[bool] = []

    async def token_provider() -> str:
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(True)
        return "unreachable"

    async def complete(**kwargs: object) -> object:
        pytest.fail("Unfinished token acquisition must not call LiteLLM")

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(
        config=entra_config(timeout_seconds=0.01), token_provider=token_provider
    )

    async def scenario() -> None:
        task = asyncio.create_task(generator.generate(request=request()))
        if cancel:
            await asyncio.sleep(0)
            task.cancel()
        expected = asyncio.CancelledError if cancel else AIUnavailableError
        with pytest.raises(expected):
            await task

    asyncio.run(scenario())
    assert finished == [True]
    assert len(caplog.records) == (0 if cancel else 1)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"choices": []},
        {**response_payload(), "choices": [response_payload()["choices"]]},
        {
            **response_payload(),
            "choices": [
                {
                    "message": {"role": "assistant", "content": None},
                    "finish_reason": "stop",
                }
            ],
        },
        {
            **response_payload(),
            "choices": [
                {
                    "message": {"role": "assistant", "content": "answer"},
                    "finish_reason": None,
                }
            ],
        },
        {
            **response_payload(),
            "choices": [
                {
                    "message": {"role": "assistant", "content": "answer"},
                    "finish_reason": "tool_calls",
                }
            ],
        },
        {**response_payload(), "usage": None},
        {
            **response_payload(),
            "usage": {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
        },
        {
            **response_payload(),
            "usage": {"prompt_tokens": -1, "completion_tokens": 2, "total_tokens": 1},
        },
        {
            **response_payload(),
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 8},
        },
    ],
)
def test_malformed_responses_never_fall_back(sdk: ModuleType, payload: object) -> None:
    async def complete(**kwargs: object) -> FakeResponse:
        return FakeResponse(payload=payload)

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(config=config())
    with pytest.raises(AIProtocolError):
        asyncio.run(generator.generate(request=request()))


@pytest.mark.parametrize(
    ("vendor_error", "safe_error"),
    [
        (FakeAuthenticationError, AIAuthenticationError),
        (FakeBadRequestError, AIConfigurationError),
        (FakeConnectionError, AIUnavailableError),
        (RuntimeError, AIProtocolError),
    ],
)
def test_sensitive_failures_have_no_vendor_exception_chain(
    sdk: ModuleType,
    caplog: pytest.LogCaptureFixture,
    vendor_error: type[Exception],
    safe_error: type[Exception],
) -> None:
    async def complete(**kwargs: object) -> object:
        try:
            fail()
        except ValueError as error:
            raise vendor_error(SENSITIVE_VALUE) from error

    def fail() -> None:
        raise ValueError(SENSITIVE_VALUE)

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(config=config())
    with caplog.at_level(logging.WARNING), pytest.raises(safe_error) as caught:
        asyncio.run(generator.generate(request=request()))
    assert SENSITIVE_VALUE not in "".join(traceback.format_exception(caught.value))
    assert SENSITIVE_VALUE not in caplog.text
    assert len(caplog.records) == 1
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is not None
    assert caught.value.__cause__.__context__ is None


def test_call_is_explicit_and_does_not_mutate_sdk_globals(sdk: ModuleType) -> None:
    calls: list[dict[str, object]] = []

    async def complete(**kwargs: object) -> FakeResponse:
        calls.append(kwargs)
        return FakeResponse(payload=response_payload())

    vars(sdk)["acompletion"] = complete
    before = deepcopy(vars(sdk))
    generator = create_text_generator(config=config())
    result = asyncio.run(generator.generate(request=request()))
    assert result.text == "answer"
    assert result.usage.total_tokens == 3
    assert vars(sdk) == before
    assert calls[0]["api_key"] == SENSITIVE_VALUE
    assert calls[0]["model"] == "openai/test"
    assert calls[0]["stream"] is False
    assert calls[0]["num_retries"] == 0
    assert calls[0]["timeout"] == 30
    assert calls[0]["max_tokens"] == 1024
    assert calls[0]["no-log"] is True


def test_cancellation_propagates_and_deadline_cancels_sdk(sdk: ModuleType) -> None:
    cancelled: list[bool] = []

    async def complete(**kwargs: object) -> object:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(
        config=TextGenerationConfig(
            model="openai/test", api_key=SENSITIVE_VALUE, timeout_seconds=0.01
        )
    )
    with pytest.raises(AIUnavailableError):
        asyncio.run(generator.generate(request=request()))
    assert cancelled == [True]

    async def cancel() -> None:
        task = asyncio.create_task(generator.generate(request=request()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert cancelled == [True, True]


def test_missing_optional_dependency_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> ModuleType:
        raise ModuleNotFoundError(SENSITIVE_VALUE)

    monkeypatch.setattr(
        "platform_kit_runtime.infrastructure.litellm.import_module", missing
    )
    with pytest.raises(AIDependencyError) as caught:
        create_text_generator(config=config())
    assert SENSITIVE_VALUE not in "".join(traceback.format_exception(caught.value))


def test_health_and_ai_facade_import_without_optional_dependencies() -> None:
    script = """
import importlib.abc
import sys
class BlockSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'litellm', 'openai', 'httpx', 'aiohttp', 'azure'}:
            raise AssertionError('optional SDK imported')
sys.meta_path.insert(0, BlockSDK())
from platform_kit_runtime import RuntimeConfig, create_app
import platform_kit_runtime.ai
app = create_app(config=RuntimeConfig(), probes=())
assert app is not None
"""
    result = subprocess.run(  # noqa: S603 - fixed offline interpreter probe
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "provider", ["azure/deployment", "anthropic/test", "openai/test"]
)
def test_provider_configuration_passes_through(sdk: ModuleType, provider: str) -> None:
    calls: list[dict[str, object]] = []

    async def complete(**kwargs: object) -> FakeResponse:
        calls.append(kwargs)
        return FakeResponse(payload=response_payload())

    vars(sdk)["acompletion"] = complete
    generator = create_text_generator(
        config=TextGenerationConfig(
            model=provider,
            api_key=SENSITIVE_VALUE,
            api_base="https://private.invalid",
            api_version="version",
            num_retries=2,
        )
    )
    asyncio.run(generator.generate(request=request()))
    assert calls[0]["model"] == provider
    assert calls[0]["api_base"] == "https://private.invalid"
    assert calls[0]["api_version"] == "version"
    assert calls[0]["num_retries"] == 2


@pytest.mark.parametrize("result", [None, {}, "answer", []])
def test_non_sdk_response_is_rejected(sdk: ModuleType, result: object) -> None:
    async def complete(**kwargs: object) -> object:
        return result

    vars(sdk)["acompletion"] = complete
    with pytest.raises(AIProtocolError):
        asyncio.run(create_text_generator(config=config()).generate(request=request()))


def test_response_serialization_failure_is_sanitized(sdk: ModuleType) -> None:
    class BrokenResponse(FakeResponse):
        def model_dump(self) -> object:
            raise ValueError(SENSITIVE_VALUE)

    async def complete(**kwargs: object) -> BrokenResponse:
        return BrokenResponse(payload=None)

    vars(sdk)["acompletion"] = complete
    with pytest.raises(AIProtocolError) as caught:
        asyncio.run(create_text_generator(config=config()).generate(request=request()))
    assert SENSITIVE_VALUE not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "message",
    [
        {"role": "user", "content": "answer"},
        {"role": "assistant", "content": ["answer"]},
        {"role": "assistant", "content": "answer", "tool_calls": [{"id": "tool"}]},
        {"role": "assistant", "content": "answer", "function_call": {}},
        {"role": "assistant", "content": "answer", "refusal": ""},
    ],
)
def test_non_text_message_shapes_are_rejected(
    sdk: ModuleType, message: dict[str, object]
) -> None:
    async def complete(**kwargs: object) -> FakeResponse:
        return FakeResponse(
            payload={
                **response_payload(),
                "choices": [{"message": message, "finish_reason": "stop"}],
            }
        )

    vars(sdk)["acompletion"] = complete
    with pytest.raises(AIProtocolError):
        asyncio.run(create_text_generator(config=config()).generate(request=request()))


@pytest.mark.parametrize(
    "fields",
    [
        {"tool_calls": []},
        {"tool_calls": None},
        {"function_call": None},
        {"refusal": None},
        {"tool_calls": [], "function_call": None, "refusal": None},
    ],
)
def test_empty_tool_and_refusal_fields_keep_text(
    sdk: ModuleType, fields: dict[str, object]
) -> None:
    async def complete(**kwargs: object) -> FakeResponse:
        message = {"role": "assistant", "content": "answer", **fields}
        return FakeResponse(
            payload={
                **response_payload(),
                "choices": [{"message": message, "finish_reason": "stop"}],
            }
        )

    vars(sdk)["acompletion"] = complete
    result = asyncio.run(
        create_text_generator(config=config()).generate(request=request())
    )
    assert (result.text, result.finish_reason) == ("answer", AIFinishReason.STOP)


@pytest.mark.parametrize("content", ["", "truncated answer"])
def test_explicit_empty_text_and_truncation_are_not_fabricated(
    sdk: ModuleType, content: str
) -> None:
    async def complete(**kwargs: object) -> FakeResponse:
        return FakeResponse(
            payload={
                **response_payload(),
                "choices": [
                    {
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "length",
                    }
                ],
            }
        )

    vars(sdk)["acompletion"] = complete
    result = asyncio.run(
        create_text_generator(config=config()).generate(request=request())
    )
    assert result.text == content
    assert result.finish_reason is AIFinishReason.LENGTH


def test_incompatible_optional_sdk_is_rejected(sdk: ModuleType) -> None:
    with pytest.raises(AIDependencyError):
        create_text_generator(config=config())
