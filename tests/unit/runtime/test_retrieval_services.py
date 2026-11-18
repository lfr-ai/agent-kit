import asyncio
import logging
from typing import Final

import pytest

from platform_kit_runtime.documents import (
    ExtractedPage,
    ExtractedText,
    OCRDocumentError,
)
from platform_kit_runtime.retrieval import (
    AccessScope,
    ChunkingConfig,
    Citation,
    IndexedChunk,
    IngestionResult,
    IngestionService,
    Passage,
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalService,
    RetrievalUnavailableError,
    SearchQuery,
    SourceDocument,
)

pytestmark = pytest.mark.unit

FIRST: Final[str] = "# Intro\n\nFirst page text."
SECOND: Final[str] = "# Terms\n\nSecond page text."
CONTENT: Final[str] = f"{FIRST}\n\n<!-- PageBreak -->\n\n{SECOND}"
PAGES: Final[tuple[ExtractedPage, ...]] = (
    ExtractedPage(number=1, start=0, end=len(FIRST)),
    ExtractedPage(number=2, start=CONTENT.index(SECOND), end=len(CONTENT)),
)


class FakeExtractor:
    def __init__(self, *, extracted: ExtractedText) -> None:
        self.extracted = extracted
        self.calls: list[bytes] = []

    async def extract(self, *, data: bytes) -> ExtractedText:
        self.calls.append(data)
        return self.extracted


class FailingExtractor:
    async def extract(self, *, data: bytes) -> ExtractedText:
        assert data
        raise OCRDocumentError


class FakeEmbedder:
    def __init__(self, *, extra: int = 0) -> None:
        self.extra = extra
        self.calls: list[tuple[str, ...]] = []

    async def embed(self, *, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(texts)
        vectors = tuple((float(len(text)), 1.0) for text in texts)
        return vectors + ((0.0, 0.0),) * self.extra


class SlowEmbedder:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def embed(self, *, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        assert texts
        self.started.set()
        await asyncio.sleep(10)
        return ()


class MemoryIndex:
    def __init__(self) -> None:
        self.chunks: dict[str, IndexedChunk] = {}
        self.operations: list[str] = []

    async def upsert(self, *, chunks: tuple[IndexedChunk, ...]) -> None:
        self.operations.append("upsert")
        self.chunks.update((chunk.key, chunk) for chunk in chunks)

    async def delete(self, *, document_id: str) -> None:
        self.operations.append("delete")
        self.chunks = {
            key: chunk
            for key, chunk in self.chunks.items()
            if chunk.citation.document_id != document_id
        }

    async def search(
        self, *, query: SearchQuery, vector: tuple[float, ...]
    ) -> tuple[Passage, ...]:
        visible = sorted(
            (
                chunk
                for chunk in self.chunks.values()
                if query.scope.allows(access=chunk.access)
            ),
            key=lambda chunk: (chunk.citation.document_id, chunk.ordinal),
        )
        return tuple(
            Passage(text=chunk.text, citation=chunk.citation, score=vector[0])
            for chunk in visible[: query.top_k]
        )


def document(
    document_id: str = "doc-1", *, access: AccessScope | None = None
) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        title="Handbook",
        data=b"%PDF-1.7",
        access=AccessScope(public=True) if access is None else access,
        source="https://files.example/handbook.pdf",
    )


def ingestion(
    content: str = CONTENT, *, pages: tuple[ExtractedPage, ...] = PAGES
) -> tuple[IngestionService, MemoryIndex, FakeEmbedder]:
    index = MemoryIndex()
    embedder = FakeEmbedder()
    service = IngestionService(
        extractor=FakeExtractor(extracted=ExtractedText(content=content, pages=pages)),
        embedder=embedder,
        index=index,
    )
    return service, index, embedder


def test_ingestion_indexes_cited_chunks_per_page_and_section() -> None:
    service, index, embedder = ingestion()
    result = asyncio.run(service.ingest(document=document()))
    assert result == IngestionResult(document_id="doc-1", chunks=2)
    assert index.operations == ["delete", "upsert"]
    stored = sorted(index.chunks.values(), key=lambda chunk: chunk.ordinal)
    assert [chunk.text for chunk in stored] == [FIRST, SECOND]
    assert [chunk.citation for chunk in stored] == [
        Citation(
            document_id="doc-1",
            title="Handbook",
            source="https://files.example/handbook.pdf",
            page=1,
            section="Intro",
        ),
        Citation(
            document_id="doc-1",
            title="Handbook",
            source="https://files.example/handbook.pdf",
            page=2,
            section="Terms",
        ),
    ]
    assert embedder.calls == [(FIRST, SECOND)]
    assert stored[0].vector == (float(len(FIRST)), 1.0)


def test_reingestion_is_idempotent_and_replaces_stale_chunks() -> None:
    service, index, _ = ingestion()
    asyncio.run(service.ingest(document=document()))
    asyncio.run(service.ingest(document=document("doc-2")))
    snapshot = dict(index.chunks)
    asyncio.run(service.ingest(document=document()))
    assert index.chunks == snapshot

    replacement = IngestionService(
        extractor=FakeExtractor(extracted=ExtractedText(content="Only text.")),
        embedder=FakeEmbedder(),
        index=index,
    )
    assert asyncio.run(replacement.ingest(document=document())).chunks == 1
    remaining = [
        (chunk.text, chunk.citation.page)
        for chunk in index.chunks.values()
        if chunk.citation.document_id == "doc-1"
    ]
    assert remaining == [("Only text.", None)]
    assert len(index.chunks) == 3


def test_empty_extraction_removes_previous_chunks() -> None:
    service, index, embedder = ingestion()
    asyncio.run(service.ingest(document=document()))
    empty = IngestionService(
        extractor=FakeExtractor(extracted=ExtractedText(content="  ")),
        embedder=embedder,
        index=index,
    )
    assert asyncio.run(empty.ingest(document=document())).chunks == 0
    assert index.chunks == {}
    assert embedder.calls[-1] == ()


def test_vector_count_mismatch_leaves_index_untouched() -> None:
    index = MemoryIndex()
    service = IngestionService(
        extractor=FakeExtractor(extracted=ExtractedText(content=CONTENT, pages=PAGES)),
        embedder=FakeEmbedder(extra=1),
        index=index,
    )
    with pytest.raises(RetrievalProtocolError):
        asyncio.run(service.ingest(document=document()))
    assert index.operations == []


def test_typed_failures_are_logged_once_with_code_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = IngestionService(
        extractor=FailingExtractor(), embedder=FakeEmbedder(), index=MemoryIndex()
    )
    with caplog.at_level(logging.WARNING), pytest.raises(OCRDocumentError):
        asyncio.run(service.ingest(document=document()))
    logged = [
        (record.getMessage(), record.__dict__["retrieval_failure"])
        for record in caplog.records
    ]
    assert logged == [("retrieval.ingestion_failed", "ocr_document")]
    assert "Handbook" not in caplog.text


def test_deadline_becomes_sanitized_unavailable_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = RetrievalService(
        embedder=SlowEmbedder(), retriever=MemoryIndex(), timeout_seconds=0.01
    )
    query = SearchQuery(text="refund", scope=AccessScope(public=True))
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(RetrievalUnavailableError) as caught,
    ):
        asyncio.run(service.retrieve(query=query))
    assert isinstance(caught.value.__cause__, RetrievalError)
    assert caught.value.__context__ is None
    logged = [
        (record.getMessage(), record.__dict__["retrieval_failure"])
        for record in caplog.records
    ]
    assert logged == [("retrieval.search_failed", "retrieval_unavailable")]


def test_cancellation_propagates_without_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    embedder = SlowEmbedder()
    service = IngestionService(
        extractor=FakeExtractor(extracted=ExtractedText(content="text")),
        embedder=embedder,
        index=MemoryIndex(),
    )

    async def cancel() -> None:
        task = asyncio.create_task(service.ingest(document=document()))
        await embedder.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with caplog.at_level(logging.WARNING):
        asyncio.run(cancel())
    assert caplog.records == []


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), True, 3601])
def test_ingestion_deadline_is_bounded(seconds: float) -> None:
    with pytest.raises(RetrievalConfigurationError):
        IngestionService(
            extractor=FailingExtractor(),
            embedder=FakeEmbedder(),
            index=MemoryIndex(),
            chunking=ChunkingConfig(),
            timeout_seconds=seconds,
        )


@pytest.mark.parametrize("seconds", [0, 301])
def test_retrieval_deadline_is_bounded(seconds: float) -> None:
    with pytest.raises(RetrievalConfigurationError):
        RetrievalService(
            embedder=FakeEmbedder(), retriever=MemoryIndex(), timeout_seconds=seconds
        )


def test_retrieval_returns_only_passages_the_scope_may_read() -> None:
    service, index, embedder = ingestion("Shared answer.", pages=())
    hr = AccessScope(groups=frozenset({"hr"}))
    asyncio.run(service.ingest(document=document("public")))
    asyncio.run(service.ingest(document=document("private", access=hr)))
    retrieval = RetrievalService(embedder=embedder, retriever=index)

    def documents(scope: AccessScope) -> list[str]:
        query = SearchQuery(text="answer", scope=scope)
        passages = asyncio.run(retrieval.retrieve(query=query))
        assert all(passage.score == float(len("answer")) for passage in passages)
        return [passage.citation.document_id for passage in passages]

    assert documents(AccessScope(public=True)) == ["public"]
    assert documents(AccessScope(groups=frozenset({"eng"}))) == ["public"]
    assert documents(AccessScope(groups=frozenset({"hr", "eng"}))) == [
        "private",
        "public",
    ]


def test_retrieval_requires_exactly_one_query_vector() -> None:
    service = RetrievalService(embedder=FakeEmbedder(extra=1), retriever=MemoryIndex())
    query = SearchQuery(text="answer", scope=AccessScope(public=True))
    with pytest.raises(RetrievalProtocolError):
        asyncio.run(service.retrieve(query=query))
