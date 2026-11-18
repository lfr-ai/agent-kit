import asyncio
from collections.abc import Callable, Sequence
import math
import sys
import traceback
from types import ModuleType
from typing import Final

import pytest

from platform_kit_runtime import retrieval as retrieval_facade
from platform_kit_runtime.ai import AsyncTokenProvider
from platform_kit_runtime.retrieval import (
    AccessScope,
    EmbeddingConfig,
    Passage,
    RetrievalAuthenticationError,
    RetrievalConfigurationError,
    RetrievalDependencyError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalService,
    RetrievalUnavailableError,
    SearchQuery,
    create_litellm_embedder,
)

pytestmark = pytest.mark.unit

SENSITIVE: Final[str] = "provider-diagnostic-abc123"
API_KEY: Final[str] = "sk-test-embedding-key-0001"
V1_BASE: Final[str] = "https://resource.openai.azure.com/openai/v1/"

type Responder = Callable[[list[str]], object]


class FakeEmbeddingResponse:
    def __init__(self, dumped: object) -> None:
        self.dumped = dumped

    def model_dump(self) -> object:
        return self.dumped


class ProviderError(Exception):
    def __init__(self, *, status_code: object) -> None:
        super().__init__(SENSITIVE)
        self.status_code = status_code


def reversed_vectors(texts: list[str]) -> object:
    data = [
        {"index": index, "embedding": [float(len(text)), 1]}
        for index, text in enumerate(texts)
    ]
    return FakeEmbeddingResponse({"data": data[::-1]})


class FakeLiteLLM:
    def __init__(
        self, *, respond: Responder = reversed_vectors, failure: Exception | None = None
    ) -> None:
        self.respond = respond
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    async def aembedding(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        texts = kwargs["input"]
        assert isinstance(texts, list)
        return self.respond([str(text) for text in texts])


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeLiteLLM) -> None:
    module = ModuleType("litellm")
    vars(module).update(
        EmbeddingResponse=FakeEmbeddingResponse, aembedding=fake.aembedding
    )
    monkeypatch.setitem(sys.modules, "litellm", module)


def embed(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeLiteLLM,
    texts: Sequence[str],
    *,
    config: EmbeddingConfig | None = None,
    token_provider: AsyncTokenProvider | None = None,
) -> tuple[tuple[float, ...], ...]:
    install(monkeypatch, fake)
    settings = config or EmbeddingConfig(model="azure/embeddings", api_key=API_KEY)
    embedder = create_litellm_embedder(config=settings, token_provider=token_provider)
    return asyncio.run(embedder.embed(texts=tuple(texts)))


def entra_config(*, timeout_seconds: float = 30) -> EmbeddingConfig:
    return EmbeddingConfig(
        model="openai/embedding-deployment",
        api_base=V1_BASE,
        entra_authentication=True,
        dimensions=2,
        timeout_seconds=timeout_seconds,
    )


def test_request_uses_explicit_settings_and_disables_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeLiteLLM()
    config = EmbeddingConfig(
        model="azure/embeddings",
        api_key=API_KEY,
        api_base="https://ai.example.net",
        api_version="2024-10-21",
        dimensions=2,
        timeout_seconds=12,
        num_retries=2,
    )
    assert embed(monkeypatch, fake, ["abc", "de"], config=config) == (
        (3.0, 1.0),
        (2.0, 1.0),
    )
    assert fake.calls == [
        {
            "model": "azure/embeddings",
            "input": ["abc", "de"],
            "api_key": API_KEY,
            "timeout": 12,
            "num_retries": 2,
            "no-log": True,
            "api_base": "https://ai.example.net",
            "api_version": "2024-10-21",
            "dimensions": 2,
        }
    ]


def test_unset_optional_settings_are_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLiteLLM()
    embed(monkeypatch, fake, ["abc"])
    assert set(fake.calls[0]) == {
        "model",
        "input",
        "api_key",
        "timeout",
        "num_retries",
        "no-log",
    }


def test_large_inputs_are_batched_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLiteLLM()
    texts = ["x" * (n + 1) for n in range(65)]
    vectors = embed(monkeypatch, fake, texts)
    assert [
        len(call["input"]) for call in fake.calls if isinstance(call["input"], list)
    ] == [
        64,
        1,
    ]
    assert [vector[0] for vector in vectors] == [float(n + 1) for n in range(65)]


def test_empty_input_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLiteLLM()
    assert embed(monkeypatch, fake, []) == ()
    assert fake.calls == []


def respond_with(*data: object) -> Responder:
    return lambda _texts: FakeEmbeddingResponse({"data": list(data)})


MALFORMED: Final[dict[str, Responder]] = {
    "foreign-type": lambda _texts: {"data": []},
    "dump-not-dict": lambda _texts: FakeEmbeddingResponse([]),
    "data-not-list": lambda _texts: FakeEmbeddingResponse({"data": None}),
    "too-few": respond_with(),
    "too-many": respond_with(
        {"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0]}
    ),
    "bool-index": respond_with({"index": True, "embedding": [1.0]}),
    "wrong-index": respond_with({"index": 1, "embedding": [1.0]}),
    "empty-vector": respond_with({"index": 0, "embedding": []}),
    "tuple-vector": respond_with({"index": 0, "embedding": (1.0,)}),
    "nan": respond_with({"index": 0, "embedding": [math.nan]}),
    "bool-value": respond_with({"index": 0, "embedding": [True]}),
    "text-value": respond_with({"index": 0, "embedding": ["1"]}),
    "entry-not-dict": respond_with([0, [1.0]]),
}


@pytest.mark.parametrize("respond", list(MALFORMED.values()), ids=list(MALFORMED))
def test_malformed_responses_raise_protocol_errors(
    monkeypatch: pytest.MonkeyPatch, respond: Responder
) -> None:
    with pytest.raises(RetrievalProtocolError):
        embed(monkeypatch, FakeLiteLLM(respond=respond), ["text"])


def test_vector_sizes_must_be_consistent(monkeypatch: pytest.MonkeyPatch) -> None:
    uneven = respond_with(
        {"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0, 2.0]}
    )
    with pytest.raises(RetrievalProtocolError):
        embed(monkeypatch, FakeLiteLLM(respond=uneven), ["a", "b"])
    config = EmbeddingConfig(model="azure/embeddings", api_key=API_KEY, dimensions=3)
    with pytest.raises(RetrievalProtocolError):
        embed(monkeypatch, FakeLiteLLM(), ["a"], config=config)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ProviderError(status_code=401), RetrievalAuthenticationError),
        (ProviderError(status_code=403), RetrievalAuthenticationError),
        (ProviderError(status_code=429), RetrievalUnavailableError),
        (ProviderError(status_code=500), RetrievalUnavailableError),
        (ProviderError(status_code=400), RetrievalConfigurationError),
        (ProviderError(status_code=404), RetrievalConfigurationError),
        (ProviderError(status_code=True), RetrievalProtocolError),
        (TimeoutError(SENSITIVE), RetrievalUnavailableError),
        (RuntimeError(SENSITIVE), RetrievalProtocolError),
    ],
)
def test_provider_failures_are_typed_and_sanitized(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, expected: type[RetrievalError]
) -> None:
    with pytest.raises(expected) as caught:
        embed(monkeypatch, FakeLiteLLM(failure=failure), ["text"])
    error = caught.value
    assert type(error) is expected
    assert type(error.__cause__) is RetrievalError
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert SENSITIVE not in rendered
    assert API_KEY not in rendered


def test_deadline_is_enforced_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowLiteLLM(FakeLiteLLM):
        async def aembedding(self, **kwargs: object) -> object:
            await asyncio.sleep(10)
            return None

    config = EmbeddingConfig(
        model="azure/embeddings", api_key=API_KEY, timeout_seconds=0.01
    )
    with pytest.raises(RetrievalUnavailableError):
        embed(monkeypatch, SlowLiteLLM(), ["text"], config=config)


def test_missing_or_incompatible_sdk_is_a_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = EmbeddingConfig(model="azure/embeddings", api_key=API_KEY)
    monkeypatch.setitem(sys.modules, "litellm", None)
    with pytest.raises(RetrievalDependencyError) as caught:
        create_litellm_embedder(config=config)
    assert type(caught.value.__cause__) is RetrievalError
    assert caught.value.__context__ is None

    monkeypatch.setitem(sys.modules, "litellm", ModuleType("litellm"))
    with pytest.raises(RetrievalDependencyError):
        create_litellm_embedder(config=config)


def test_entra_mode_sends_a_renewed_token_per_call_without_key_or_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = iter(("synthetic-first-token", "synthetic-renewed-token"))

    async def token_provider() -> str:
        return next(tokens)

    fake = FakeLiteLLM(
        respond=lambda texts: FakeEmbeddingResponse(
            {
                "data": [
                    {"index": index, "embedding": [1.0, 2.0]}
                    for index in range(len(texts))
                ]
            }
        )
    )
    texts = ["x"] * 65
    vectors = embed(
        monkeypatch, fake, texts, config=entra_config(), token_provider=token_provider
    )
    assert len(vectors) == 65
    assert [call["api_key"] for call in fake.calls] == [
        "synthetic-first-token",
        "synthetic-renewed-token",
    ]
    for call in fake.calls:
        assert set(call) == {
            "model",
            "input",
            "api_key",
            "timeout",
            "num_retries",
            "no-log",
            "api_base",
            "dimensions",
        }
        assert call["model"] == "openai/embedding-deployment"
        assert call["api_base"] == V1_BASE
        assert call["no-log"] is True


@pytest.mark.parametrize("entra", [True, False])
def test_token_provider_and_auth_mode_must_match(
    monkeypatch: pytest.MonkeyPatch, *, entra: bool
) -> None:
    async def token_provider() -> str:
        return SENSITIVE

    # Configuration is rejected before the optional SDK is loaded.
    monkeypatch.setitem(sys.modules, "litellm", None)
    key_config = EmbeddingConfig(model="azure/embeddings", api_key=API_KEY)
    with pytest.raises(RetrievalConfigurationError) as caught:
        create_litellm_embedder(
            config=entra_config() if entra else key_config,
            token_provider=None if entra else token_provider,
        )
    assert SENSITIVE not in "".join(traceback.format_exception(caught.value))


def test_token_provider_must_be_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "litellm", None)
    # The untyped lookup models a dynamically wired caller passing a plain token.
    factory = vars(retrieval_facade)["create_litellm_embedder"]
    with pytest.raises(RetrievalConfigurationError) as caught:
        factory(config=entra_config(), token_provider=SENSITIVE)
    assert SENSITIVE not in "".join(traceback.format_exception(caught.value))


class RecordingRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[SearchQuery, tuple[float, ...]]] = []

    async def search(
        self, *, query: SearchQuery, vector: tuple[float, ...]
    ) -> tuple[Passage, ...]:
        self.calls.append((query, vector))
        return ()


@pytest.mark.parametrize(
    "failure", ["exception", "empty", "blank", "newline", "timeout"]
)
def test_token_failures_are_typed_sanitized_and_logged_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, failure: str
) -> None:
    async def token_provider() -> str:
        if failure == "exception":
            raise RuntimeError(SENSITIVE)
        if failure == "timeout":
            raise TimeoutError(SENSITIVE)
        return {"empty": "", "blank": "  ", "newline": f"{SENSITIVE}\n"}[failure]

    fake = FakeLiteLLM()
    install(monkeypatch, fake)
    retriever = RecordingRetriever()
    service = RetrievalService(
        embedder=create_litellm_embedder(
            config=entra_config(), token_provider=token_provider
        ),
        retriever=retriever,
    )
    query = SearchQuery(text="refund policy", scope=AccessScope(public=True))
    expected = (
        RetrievalUnavailableError
        if failure == "timeout"
        else RetrievalAuthenticationError
    )
    with pytest.raises(expected) as caught:
        asyncio.run(service.retrieve(query=query))
    assert fake.calls == []
    assert retriever.calls == []
    assert type(caught.value) is expected
    assert type(caught.value.__cause__) is RetrievalError
    assert caught.value.__context__ is None
    assert SENSITIVE not in "".join(traceback.format_exception(caught.value))
    assert SENSITIVE not in caplog.text
    assert len(caplog.records) == 1
    assert vars(caplog.records[0])["retrieval_failure"] == caught.value.code


@pytest.mark.parametrize("cancel", [True, False])
def test_token_acquisition_shares_deadline_and_cancellation(
    monkeypatch: pytest.MonkeyPatch, *, cancel: bool
) -> None:
    finished: list[bool] = []

    async def token_provider() -> str:
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(True)
        return "unreachable"

    fake = FakeLiteLLM()
    install(monkeypatch, fake)
    embedder = create_litellm_embedder(
        config=entra_config(timeout_seconds=0.01), token_provider=token_provider
    )

    async def scenario() -> None:
        task = asyncio.create_task(embedder.embed(texts=("text",)))
        if cancel:
            await asyncio.sleep(0)
            task.cancel()
        expected = asyncio.CancelledError if cancel else RetrievalUnavailableError
        with pytest.raises(expected):
            await task

    asyncio.run(scenario())
    assert finished == [True]
    assert fake.calls == []
