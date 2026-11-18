"""Ingestion and cited-retrieval orchestration with one safe diagnostic boundary."""

import asyncio
from collections.abc import Coroutine
import logging

from platform_kit_runtime.core.limits import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MAX_REQUEST_TIMEOUT_SECONDS,
)
from platform_kit_runtime.core.retrieval.chunking import chunk_markdown
from platform_kit_runtime.core.retrieval.models import (
    ChunkingConfig,
    Citation,
    IndexedChunk,
    IngestionResult,
    Passage,
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalUnavailableError,
    SearchQuery,
    SourceDocument,
)
from platform_kit_runtime.core.retrieval.ocr import OCRError, TextExtractor
from platform_kit_runtime.core.retrieval.ports import DocumentIndex, Embedder, Retriever
from platform_kit_runtime.core.validation import is_bounded_seconds

_LOGGER = logging.getLogger(__name__)
_DEFAULT_CHUNKING = ChunkingConfig()
_DEFAULT_INGESTION_TIMEOUT_SECONDS = 900.0
_MAX_INGESTION_TIMEOUT_SECONDS = 3600.0


async def _within_deadline[ResultT](
    operation: Coroutine[object, object, ResultT], *, seconds: float, event: str
) -> ResultT:
    """Await ``operation`` under a deadline and log a typed failure once.

    Caller cancellation propagates without error logging.

    Args:
        operation (Coroutine[object, object, ResultT]): Unstarted use-case coroutine.
        seconds (float): Total deadline.
        event (str): Fixed log event name.

    Returns:
        ResultT: The operation result.

    Raises:
        RetrievalUnavailableError: The deadline elapsed.
        RetrievalError: Safe typed retrieval failure, logged with its code only.
        OCRError: Safe typed extraction failure, logged with its code only.
    """
    try:
        async with asyncio.timeout(seconds):
            return await operation
    except TimeoutError:
        failure = RetrievalUnavailableError()
    except (RetrievalError, OCRError) as error:
        _LOGGER.warning(event, extra={"retrieval_failure": error.code})
        raise
    _LOGGER.warning(event, extra={"retrieval_failure": failure.code})
    raise failure from RetrievalError()


class IngestionService:
    """Extract, chunk, embed and replace one document's chunks idempotently."""

    def __init__(
        self,
        *,
        extractor: TextExtractor,
        embedder: Embedder,
        index: DocumentIndex,
        chunking: ChunkingConfig = _DEFAULT_CHUNKING,
        timeout_seconds: float = _DEFAULT_INGESTION_TIMEOUT_SECONDS,
    ) -> None:
        """Bind caller-owned ports and the total ingestion deadline.

        Args:
            extractor (TextExtractor): OCR or other text-extraction port.
            embedder (Embedder): Embedding port; its vector size must match the index.
            index (DocumentIndex): Chunk store keyed by document ID.
            chunking (ChunkingConfig): Chunk size and overlap.
            timeout_seconds (float): Total deadline per document, at most one hour.

        Raises:
            RetrievalConfigurationError: The deadline is not a bounded duration.
        """
        if not is_bounded_seconds(
            timeout_seconds, maximum=_MAX_INGESTION_TIMEOUT_SECONDS
        ):
            raise RetrievalConfigurationError
        self._extractor = extractor
        self._embedder = embedder
        self._index = index
        self._chunking = chunking
        self._timeout_seconds = timeout_seconds

    async def ingest(self, *, document: SourceDocument) -> IngestionResult:
        """Replace all chunks of ``document``, logging handled failures once.

        Extraction and embedding finish before the index changes; the old chunks
        are then deleted and the new ones written, so repeating an ingestion
        converges on the same index state. Typed retrieval or OCR errors and the
        deadline (``RetrievalUnavailableError``) propagate after logging their
        code; caller cancellation propagates without logging.
        """
        return await _within_deadline(
            self._ingest(document),
            seconds=self._timeout_seconds,
            event="retrieval.ingestion_failed",
        )

    async def _ingest(self, document: SourceDocument) -> IngestionResult:
        extracted = await self._extractor.extract(data=document.data)
        chunks = chunk_markdown(text=extracted.content, config=self._chunking)
        vectors = await self._embedder.embed(
            texts=tuple(chunk.text for chunk in chunks)
        )
        if len(vectors) != len(chunks):
            raise RetrievalProtocolError
        indexed = tuple(
            IndexedChunk(
                citation=Citation(
                    document_id=document.document_id,
                    title=document.title,
                    source=document.source,
                    page=extracted.page_at(chunk.start),
                    section=chunk.section,
                ),
                ordinal=ordinal,
                text=chunk.text,
                vector=vector,
                access=document.access,
            )
            for ordinal, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        )
        await self._index.delete(document_id=document.document_id)
        await self._index.upsert(chunks=indexed)
        return IngestionResult(document_id=document.document_id, chunks=len(indexed))


class RetrievalService:
    """Embed a scoped query and return cited passages."""

    def __init__(
        self,
        *,
        embedder: Embedder,
        retriever: Retriever,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Bind caller-owned ports and the total retrieval deadline.

        Args:
            embedder (Embedder): The same embedding model used for ingestion.
            retriever (Retriever): Scoped search port.
            timeout_seconds (float): Total deadline per query, at most 300 seconds.

        Raises:
            RetrievalConfigurationError: The deadline is not a bounded duration.
        """
        if not is_bounded_seconds(timeout_seconds, maximum=MAX_REQUEST_TIMEOUT_SECONDS):
            raise RetrievalConfigurationError
        self._embedder = embedder
        self._retriever = retriever
        self._timeout_seconds = timeout_seconds

    async def retrieve(self, *, query: SearchQuery) -> tuple[Passage, ...]:
        """Return at most ``query.top_k`` cited passages visible to ``query.scope``.

        Typed retrieval errors and the deadline (``RetrievalUnavailableError``)
        propagate after logging their code; caller cancellation propagates
        without logging.
        """
        return await _within_deadline(
            self._retrieve(query),
            seconds=self._timeout_seconds,
            event="retrieval.search_failed",
        )

    async def _retrieve(self, query: SearchQuery) -> tuple[Passage, ...]:
        vectors = await self._embedder.embed(texts=(query.text,))
        if len(vectors) != 1:
            raise RetrievalProtocolError
        return await self._retriever.search(query=query, vector=vectors[0])
