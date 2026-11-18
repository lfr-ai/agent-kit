"""Async retrieval ports implemented by infrastructure adapters."""

from typing import Protocol

from platform_kit_runtime.core.retrieval.models import (
    IndexedChunk,
    Passage,
    SearchQuery,
)


class Embedder(Protocol):
    """Turns texts into embedding vectors."""

    async def embed(self, *, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """Return one equal-length vector per text in order; ``()`` for no texts.

        Implementations raise ``RetrievalConfigurationError``,
        ``RetrievalAuthenticationError``, ``RetrievalUnavailableError`` or
        ``RetrievalProtocolError``; caller cancellation propagates unchanged.
        """
        ...


class DocumentIndex(Protocol):
    """Stores chunks and removes all chunks of one document."""

    async def upsert(self, *, chunks: tuple[IndexedChunk, ...]) -> None:
        """Insert or replace ``chunks`` by key; an empty input does nothing.

        Implementations raise ``RetrievalConfigurationError`` when the index
        rejects documents, and ``RetrievalAuthenticationError``,
        ``RetrievalUnavailableError`` or ``RetrievalProtocolError`` for other
        failures; caller cancellation propagates unchanged.
        """
        ...

    async def delete(self, *, document_id: str) -> None:
        """Delete every chunk of ``document_id``; a missing document succeeds.

        Implementations raise the same typed errors as ``upsert``.
        """
        ...


class Retriever(Protocol):
    """Searches chunks visible to the query's access scope."""

    async def search(
        self, *, query: SearchQuery, vector: tuple[float, ...]
    ) -> tuple[Passage, ...]:
        """Return the best passages the query scope may read, best first.

        Args:
            query (SearchQuery): Text, required access scope and result count.
            vector (tuple[float, ...]): Embedding of ``query.text``.

        Returns:
            tuple[Passage, ...]: At most ``query.top_k`` cited passages.

        Raises:
            RetrievalConfigurationError: The index rejected the query.
            RetrievalAuthenticationError: Authentication or permission was rejected.
            RetrievalUnavailableError: Deadline, connection or service failure.
            RetrievalProtocolError: Unexpected SDK failure or malformed response.
            asyncio.CancelledError: Caller cancellation propagates unchanged.
        """
        ...


class HybridIndex(DocumentIndex, Retriever, Protocol):
    """An index that both stores chunks and serves scoped hybrid search."""
