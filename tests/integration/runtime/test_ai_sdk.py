import asyncio
from collections.abc import Iterator
from copy import copy
import importlib
import importlib.util
import json
import socket
import traceback
from types import ModuleType
from typing import Final

import pytest

from platform_kit_runtime.ai import (
    AIAuthenticationError,
    AIConfigurationError,
    AIError,
    AIMessage,
    AIRole,
    AIUnavailableError,
    TextGenerationConfig,
    TextRequest,
    create_text_generator,
)
from platform_kit_runtime.core.ai import TextGenerator
from platform_kit_runtime.retrieval import EmbeddingConfig, create_litellm_embedder

pytestmark = [
    pytest.mark.integration,
    # Keep the SDK's known schema warning visible; unrelated warnings remain errors.
    pytest.mark.filterwarnings(
        "default:Item 'summary' on TypedDict class 'ChatCompletionReasoningItem' "
        "is using the `ReadOnly` qualifier:UserWarning"
    ),
]

SENSITIVE_VALUE: Final[str] = "synthetic-private-provider-diagnostic"
# These wire-contract tests include cold SDK initialization, not deadline behavior.
_SDK_WIRE_TIMEOUT_SECONDS = 120


def _mock_response_payload(*, status: int) -> dict[str, object]:
    if status == 200:
        return {
            "id": "offline-response",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "synthetic answer"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    return {"error": {"message": SENSITIVE_VALUE, "type": "invalid_request_error"}}


def _config_for_provider(*, provider: str) -> TextGenerationConfig:
    return TextGenerationConfig(
        model=f"{provider}/gpt-4o-mini",
        api_key=SENSITIVE_VALUE,
        api_base="https://provider.invalid",
        api_version="2024-10-21" if provider == "azure" else None,
        timeout_seconds=_SDK_WIRE_TIMEOUT_SECONDS,
    )


async def _assert_generation(
    *,
    generator: TextGenerator,
    request: TextRequest,
    error_type: type[AIError] | None,
) -> None:
    if error_type is None:
        result = await generator.generate(request=request)
        assert result.text == "synthetic answer"
        assert result.usage.total_tokens == 3
        return
    with pytest.raises(error_type) as caught:
        await generator.generate(request=request)
    assert SENSITIVE_VALUE not in "".join(traceback.format_exception(caught.value))


@pytest.fixture
def sdk_runner() -> Iterator[asyncio.Runner]:
    with asyncio.Runner() as runner:
        yield runner


@pytest.fixture
def released_sdk(
    monkeypatch: pytest.MonkeyPatch, sdk_runner: asyncio.Runner
) -> ModuleType:
    if importlib.util.find_spec("litellm") is None:
        pytest.skip("parent-managed optional AI dependency is not installed")

    def no_network(*args: object, **kwargs: object) -> object:
        pytest.fail("AI contract tests must not access the network")

    sdk_runner.get_loop()
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    return importlib.import_module("litellm")


def test_released_sdk_response_contract(
    released_sdk: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    sdk_runner: asyncio.Runner,
) -> None:
    response_type = vars(released_sdk)["ModelResponse"]
    response = response_type(
        model="openai/test",
        choices=[
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "synthetic answer"},
            }
        ],
        usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    )

    async def complete(**kwargs: object) -> object:
        return response

    monkeypatch.setattr(released_sdk, "acompletion", complete)
    names = (
        "api_key",
        "api_base",
        "api_version",
        "num_retries",
        "set_verbose",
        "callbacks",
        "input_callback",
        "success_callback",
        "failure_callback",
    )
    before = {name: copy(vars(released_sdk).get(name)) for name in names}
    generator = create_text_generator(
        config=TextGenerationConfig(model="openai/test", api_key=SENSITIVE_VALUE)
    )
    result = sdk_runner.run(
        generator.generate(
            request=TextRequest(
                messages=(AIMessage(role=AIRole.USER, content="hello"),)
            )
        )
    )
    assert result.text == "synthetic answer"
    assert result.usage.total_tokens == 3
    assert {name: vars(released_sdk).get(name) for name in names} == before


@pytest.mark.parametrize(
    ("vendor_name", "error_type"),
    [
        ("AuthenticationError", AIAuthenticationError),
        ("BadRequestError", AIConfigurationError),
        ("APIConnectionError", AIUnavailableError),
    ],
)
def test_released_sdk_errors_are_sanitized(
    released_sdk: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    sdk_runner: asyncio.Runner,
    vendor_name: str,
    error_type: type[Exception],
) -> None:
    vendor_type = vars(released_sdk)[vendor_name]

    async def complete(**kwargs: object) -> object:
        raise vendor_type(
            message=SENSITIVE_VALUE, model="openai/test", llm_provider="openai"
        )

    monkeypatch.setattr(released_sdk, "acompletion", complete)
    generator = create_text_generator(
        config=TextGenerationConfig(model="openai/test", api_key=SENSITIVE_VALUE)
    )
    with pytest.raises(error_type) as caught:
        sdk_runner.run(
            generator.generate(
                request=TextRequest(
                    messages=(AIMessage(role=AIRole.USER, content="hello"),)
                )
            )
        )
    assert SENSITIVE_VALUE not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None


@pytest.mark.parametrize("provider", ["openai", "azure"])
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (200, None),
        (400, AIConfigurationError),
        (401, AIAuthenticationError),
        (429, AIUnavailableError),
        (503, AIUnavailableError),
    ],
)
def test_real_acompletion_over_mock_http(
    released_sdk: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    sdk_runner: asyncio.Runner,
    caplog: pytest.LogCaptureFixture,
    provider: str,
    status: int,
    error_type: type[AIError] | None,
) -> None:
    httpx = importlib.import_module("httpx")
    openai = importlib.import_module("openai")
    original_completion = vars(released_sdk)["acompletion"]
    requests: list[object] = []
    config = _config_for_provider(provider=provider)

    def handle(request: object) -> object:
        requests.append(request)
        return vars(httpx)["Response"](
            status, json=_mock_response_payload(status=status)
        )

    async def scenario() -> None:
        async with vars(httpx)["AsyncClient"](
            transport=vars(httpx)["MockTransport"](handle)
        ) as http:
            if provider == "azure":
                client = vars(openai)["AsyncAzureOpenAI"](
                    api_key=config.api_key,
                    azure_endpoint=config.api_base,
                    api_version=config.api_version,
                    http_client=http,
                    max_retries=0,
                )
            else:
                client = vars(openai)["AsyncOpenAI"](
                    api_key=config.api_key,
                    base_url=config.api_base,
                    http_client=http,
                    max_retries=0,
                )
            async with client:

                async def complete(**kwargs: object) -> object:
                    return await original_completion(**kwargs, client=client)

                monkeypatch.setattr(released_sdk, "acompletion", complete)
                generator = create_text_generator(config=config)
                request = TextRequest(
                    messages=(AIMessage(role=AIRole.USER, content=SENSITIVE_VALUE),)
                )
                await _assert_generation(
                    generator=generator, request=request, error_type=error_type
                )

    sdk_runner.run(scenario())
    assert len(requests) == 1
    request = requests[0]
    assert isinstance(request, vars(httpx)["Request"])
    body = json.loads(request.content)
    assert body["messages"] == [{"role": "user", "content": SENSITIVE_VALUE}]
    assert body["max_tokens"] == 1024
    if provider == "azure":
        assert request.headers["api-key"] == SENSITIVE_VALUE
        assert request.url.params["api-version"] == "2024-10-21"
        assert request.url.path == "/openai/deployments/gpt-4o-mini/chat/completions"
    else:
        assert request.headers["authorization"] == f"Bearer {SENSITIVE_VALUE}"
        assert request.url.path == "/chat/completions"
    assert SENSITIVE_VALUE not in caplog.text


def test_real_v1_sdk_uses_renewed_bearer_tokens_without_api_version(
    released_sdk: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    sdk_runner: asyncio.Runner,
    caplog: pytest.LogCaptureFixture,
) -> None:
    httpx = importlib.import_module("httpx")
    adapter = importlib.import_module("litellm.llms.openai.openai")
    requests: list[object] = []
    tokens = iter(("synthetic-initial-token", "synthetic-renewed-token"))

    async def token_provider() -> str:
        return next(tokens)

    def handle(request: object) -> object:
        requests.append(request)
        return vars(httpx)["Response"](200, json=_mock_response_payload(status=200))

    async def scenario() -> None:
        async with vars(httpx)["AsyncClient"](
            transport=vars(httpx)["MockTransport"](handle)
        ) as http:

            def http_client(**kwargs: object) -> object:
                return http

            monkeypatch.setattr(
                vars(adapter)["OpenAIChatCompletion"],
                "_get_async_http_client",
                staticmethod(http_client),
            )
            generator = create_text_generator(
                config=TextGenerationConfig(
                    model="openai/deployment",
                    api_base="https://v1-provider.invalid/openai/v1/",
                    entra_authentication=True,
                    timeout_seconds=_SDK_WIRE_TIMEOUT_SECONDS,
                ),
                token_provider=token_provider,
            )
            for _ in range(2):
                result = await generator.generate(
                    request=TextRequest(
                        messages=(AIMessage(role=AIRole.USER, content="hello"),)
                    )
                )
                assert result.text == "synthetic answer"

    sdk_runner.run(scenario())
    _assert_v1_requests(requests=requests, httpx=httpx, caplog=caplog)


def _assert_v1_requests(
    *,
    requests: list[object],
    httpx: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert len(requests) == 2
    expected_tokens = ("synthetic-initial-token", "synthetic-renewed-token")
    for request, token in zip(requests, expected_tokens, strict=True):
        assert isinstance(request, vars(httpx)["Request"])
        assert request.url.path == "/openai/v1/chat/completions"
        assert not request.url.query
        assert request.headers["authorization"] == f"Bearer {token}"
        assert "api-key" not in request.headers
        assert json.loads(request.content)["model"] == "deployment"
        assert token not in caplog.text


def _embedding_payload() -> dict[str, object]:
    return {
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": [0.5, 0.25]}],
        "model": "embedding-deployment",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def test_real_v1_embeddings_use_renewed_bearer_tokens_without_key_header(
    released_sdk: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    sdk_runner: asyncio.Runner,
    caplog: pytest.LogCaptureFixture,
) -> None:
    httpx = importlib.import_module("httpx")
    adapter = importlib.import_module("litellm.llms.openai.openai")
    requests: list[object] = []
    tokens = ("synthetic-embedding-token", "synthetic-renewed-embedding-token")
    issued = iter(tokens)
    texts = ("first passage", "second passage")

    async def token_provider() -> str:
        return next(issued)

    def handle(request: object) -> object:
        requests.append(request)
        return vars(httpx)["Response"](200, json=_embedding_payload())

    async def scenario() -> None:
        async with vars(httpx)["AsyncClient"](
            transport=vars(httpx)["MockTransport"](handle)
        ) as http:

            def http_client(**kwargs: object) -> object:
                return http

            monkeypatch.setattr(
                vars(adapter)["OpenAIChatCompletion"],
                "_get_async_http_client",
                staticmethod(http_client),
            )
            embedder = create_litellm_embedder(
                config=EmbeddingConfig(
                    model="openai/embedding-deployment",
                    api_base="https://v1-embeddings.invalid/openai/v1/",
                    entra_authentication=True,
                    timeout_seconds=_SDK_WIRE_TIMEOUT_SECONDS,
                ),
                token_provider=token_provider,
            )
            for text in texts:
                assert await embedder.embed(texts=(text,)) == ((0.5, 0.25),)

    sdk_runner.run(scenario())
    _assert_v1_embedding_requests(
        requests=requests,
        expected=tuple(zip(tokens, texts, strict=True)),
        httpx=httpx,
        caplog=caplog,
    )


def _assert_v1_embedding_requests(
    *,
    requests: list[object],
    expected: tuple[tuple[str, str], ...],
    httpx: ModuleType,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert len(requests) == len(expected)
    for request, (token, text) in zip(requests, expected, strict=True):
        assert isinstance(request, vars(httpx)["Request"])
        assert request.url.path == "/openai/v1/embeddings"
        assert not request.url.query
        assert request.headers["authorization"] == "Bearer " + token
        assert "api-key" not in request.headers
        body = json.loads(request.content)
        assert body["model"] == "embedding-deployment"
        assert body["input"] == [text]
        assert token not in caplog.text
