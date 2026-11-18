"""Opt-in LiteLLM embedding adapter with strict response validation."""

import asyncio
from collections.abc import Sequence
from importlib import import_module
from itertools import batched
from math import isfinite
from typing import Protocol, runtime_checkable

from platform_kit_runtime.core.ai import AsyncTokenProvider
from platform_kit_runtime.core.retrieval.models import (
    EmbeddingConfig,
    RetrievalAuthenticationError,
    RetrievalDependencyError,
    RetrievalError,
    RetrievalProtocolError,
)
from platform_kit_runtime.core.validation import is_nonblank
from platform_kit_runtime.infrastructure.retrieval.failures import (
    FailureKind,
    classify_status,
    retrieval_failure,
)

# Conservative request size accepted by the common embedding providers.
_BATCH_SIZE = 64


@runtime_checkable
class LiteLLMEmbeddingSDK(Protocol):
    """Minimal released SDK surface used for embeddings."""

    EmbeddingResponse: type[object]

    async def aembedding(self, **kwargs: object) -> object:
        """Return one SDK embedding response for explicit per-call arguments."""
        ...


@runtime_checkable
class _Response(Protocol):
    def model_dump(self) -> object: ...


def load_litellm_embeddings() -> LiteLLMEmbeddingSDK:
    """Return the optional SDK; raise ``RetrievalDependencyError`` if unusable."""
    try:
        sdk = import_module("litellm")
    except Exception:  # noqa: BLE001 - optional import failures must not expose vendor diagnostics
        sdk = None
    if not isinstance(sdk, LiteLLMEmbeddingSDK):
        raise RetrievalDependencyError from RetrievalError()
    return sdk


def _classify(error: Exception) -> FailureKind:
    if isinstance(error, RetrievalAuthenticationError):
        return FailureKind.AUTHENTICATION
    if isinstance(error, TimeoutError):
        return FailureKind.UNAVAILABLE
    return classify_status(getattr(error, "status_code", None))


def _vector(value: object) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise RetrievalProtocolError
    numbers = tuple(value)
    for number in numbers:
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise RetrievalProtocolError
        if not isfinite(number):
            raise RetrievalProtocolError
    return tuple(float(number) for number in numbers)


def _entry(value: object) -> tuple[int, tuple[float, ...]]:
    if not isinstance(value, dict):
        raise RetrievalProtocolError
    index = value.get("index")
    if type(index) is not int:
        raise RetrievalProtocolError
    return index, _vector(value.get("embedding"))


class LiteLLMEmbedder:
    """``Embedder`` over LiteLLM with batching and a per-call deadline."""

    def __init__(
        self,
        *,
        config: EmbeddingConfig,
        sdk: LiteLLMEmbeddingSDK,
        token_provider: AsyncTokenProvider | None = None,
    ) -> None:
        """Bind validated settings, the injected SDK surface and the token source.

        Args:
            config (EmbeddingConfig): Explicit validated provider settings.
            sdk (LiteLLMEmbeddingSDK): Loaded SDK with the embedding surface.
            token_provider (AsyncTokenProvider | None): Caller-owned renewable
                Microsoft Entra bearer token source, called once per SDK call;
                validated against the configuration by the composition root.
        """
        self._config = config
        self._sdk = sdk
        self._token_provider = token_provider

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
            raise RetrievalAuthenticationError from RetrievalError()
        return token

    def _arguments(
        self, texts: Sequence[str], *, api_key: str | None
    ) -> dict[str, object]:
        config = self._config
        arguments: dict[str, object] = {
            "model": config.model,
            "input": list(texts),
            "api_key": api_key,
            "timeout": config.timeout_seconds,
            "num_retries": config.num_retries,
            "no-log": True,
        }
        optional = {
            "api_base": config.api_base,
            "api_version": config.api_version,
            "dimensions": config.dimensions,
        }
        arguments.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return arguments

    def _vectors(self, response: object, *, count: int) -> list[tuple[float, ...]]:
        if not isinstance(response, self._sdk.EmbeddingResponse) or not isinstance(
            response, _Response
        ):
            raise RetrievalProtocolError
        dumped = response.model_dump()
        data = dumped.get("data") if isinstance(dumped, dict) else None
        if not isinstance(data, list) or len(data) != count:
            raise RetrievalProtocolError
        entries = sorted(map(_entry, data), key=lambda entry: entry[0])
        if [index for index, _ in entries] != list(range(count)):
            raise RetrievalProtocolError
        return [vector for _, vector in entries]

    async def _batch(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                api_key = await self._api_key()
                response = await self._sdk.aembedding(
                    **self._arguments(texts, api_key=api_key)
                )
            vectors = self._vectors(response, count=len(texts))
        except Exception as error:  # noqa: BLE001 - all SDK exceptions require a content-free boundary
            kind = _classify(error)
        else:
            return vectors
        raise retrieval_failure(kind) from RetrievalError()

    async def embed(self, *, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one finite vector per text in order; empty input makes no call.

        With Microsoft Entra, a token is requested within each SDK call's
        deadline and sent as a bearer token, never as an API key header. Token
        acquisition failures raise ``RetrievalAuthenticationError``; token and
        call timeouts raise ``RetrievalUnavailableError``. Provider failures
        raise typed ``RetrievalError`` subclasses without provider messages;
        malformed or inconsistent vectors raise ``RetrievalProtocolError``.
        Cancellation propagates unchanged.
        """
        vectors: list[tuple[float, ...]] = []
        for batch in batched(texts, _BATCH_SIZE, strict=False):
            vectors.extend(await self._batch(batch))
        sizes = {len(vector) for vector in vectors}
        expected = self._config.dimensions
        if len(sizes) > 1 or (expected is not None and sizes - {expected}):
            raise RetrievalProtocolError
        return tuple(vectors)
