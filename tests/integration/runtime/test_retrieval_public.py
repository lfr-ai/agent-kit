import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
import subprocess
import sys
from types import ModuleType, TracebackType
from typing import Final, override

from azure.core.credentials import AccessToken, AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.search.documents.indexes.models import SearchIndex
import pytest

from platform_kit_runtime.documents import (
    ExtractedPage,
    ExtractedText,
    OCRConfig,
    OCRConfigurationError,
    OCRDependencyError,
    OCRError,
    open_document_intelligence,
)
from platform_kit_runtime.retrieval import (
    AccessScope,
    AzureSearchConfig,
    EmbeddingConfig,
    IndexedChunk,
    IngestionService,
    LabelledQuery,
    Passage,
    RetrievalConfigurationError,
    RetrievalDependencyError,
    RetrievalError,
    RetrievalMetrics,
    RetrievalService,
    SearchQuery,
    SourceDocument,
    azure_search_index_definition,
    create_litellm_embedder,
    evaluate_retrieval,
    open_azure_search,
)

pytestmark = pytest.mark.integration

SEARCH: Final[AzureSearchConfig] = AzureSearchConfig(
    endpoint="https://search.example.net", index_name="chunks"
)
OCR: Final[OCRConfig] = OCRConfig(endpoint="https://ocr.example.net")
SEARCH_MODULE: Final[str] = "platform_kit_runtime.infrastructure.retrieval.azure_search"
OCR_MODULE: Final[str] = "platform_kit_runtime.infrastructure.retrieval.ocr"
POLICY: Final[str] = (
    "# Refunds\n\nRefunds take five days.\n\n# Travel\n\nBook trains early."
)
# Cold interpreter start-up with coverage can be slow on synced or scanned disks.
PROBE_TIMEOUT_SECONDS: Final[int] = 240


class FakeCredential(AsyncTokenCredential):
    @override
    async def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        raise AssertionError

    @override
    async def close(self) -> None:
        pass

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.close()


def test_facades_import_and_fail_safely_without_optional_dependencies() -> None:
    script = """
import asyncio
import importlib.abc
import sys
BLOCKED = {'azure', 'litellm', 'aiohttp', 'httpx', 'openai'}
class BlockSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in BLOCKED:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, BlockSDK())
from platform_kit_runtime.documents import OCRConfig, OCRDependencyError, open_document_intelligence
from platform_kit_runtime.retrieval import (
    AzureSearchConfig, ChunkingConfig, EmbeddingConfig, RetrievalDependencyError,
    azure_search_index_definition, chunk_markdown, create_litellm_embedder, open_azure_search,
)
assert not BLOCKED & {name.split('.')[0] for name in sys.modules}
assert chunk_markdown(text='# A\\n\\nbody', config=ChunkingConfig())
search = AzureSearchConfig(endpoint='https://search.example.net', index_name='chunks')
async def enter(opener, config, expected):
    try:
        async with opener(config=config, credential=None):
            raise AssertionError('opened without SDK')
    except expected:
        return
asyncio.run(enter(open_azure_search, search, RetrievalDependencyError))
asyncio.run(enter(
    open_document_intelligence, OCRConfig(endpoint='https://ocr.example.net'), OCRDependencyError
))
for call in (
    lambda: azure_search_index_definition(config=search, dimensions=3),
    lambda: create_litellm_embedder(config=EmbeddingConfig(model='m', api_key='k')),
):
    try:
        call()
    except RetrievalDependencyError:
        continue
    raise AssertionError('created without SDK')
"""
    result = subprocess.run(  # noqa: S603 - fixed offline interpreter probe
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stderr


def test_missing_adapters_raise_dependency_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, SEARCH_MODULE, None)
    monkeypatch.setitem(sys.modules, OCR_MODULE, None)

    async def open_search() -> None:
        async with open_azure_search(config=SEARCH, credential=FakeCredential()):
            pass

    async def open_ocr() -> None:
        async with open_document_intelligence(config=OCR, credential=FakeCredential()):
            pass

    with pytest.raises(RetrievalDependencyError) as search_error:
        asyncio.run(open_search())
    with pytest.raises(RetrievalDependencyError) as definition_error:
        azure_search_index_definition(config=SEARCH, dimensions=3)
    with pytest.raises(OCRDependencyError) as ocr_error:
        asyncio.run(open_ocr())
    for caught in (search_error, definition_error):
        assert type(caught.value.__cause__) is RetrievalError
        assert caught.value.__context__ is None
    assert type(ocr_error.value.__cause__) is OCRError
    assert ocr_error.value.__context__ is None


def test_facades_open_clients_with_entra_credentials_only() -> None:
    async def opened(
        opener: Callable[..., AbstractAsyncContextManager[object]],
        config: object,
        credential: object,
    ) -> bool:
        async with opener(config=config, credential=credential) as adapter:
            return adapter is not None

    search, ocr = open_azure_search, open_document_intelligence
    assert asyncio.run(opened(search, SEARCH, FakeCredential()))
    assert asyncio.run(opened(ocr, OCR, FakeCredential()))
    with pytest.raises(RetrievalConfigurationError):
        asyncio.run(opened(search, SEARCH, AzureKeyCredential("key")))
    with pytest.raises(OCRConfigurationError):
        asyncio.run(opened(ocr, OCR, AzureKeyCredential("key")))


def test_index_definition_is_valid_sdk_input() -> None:
    definition = azure_search_index_definition(config=SEARCH, dimensions=3)
    index = SearchIndex(definition)
    assert index.name == "chunks"
    assert [field.name for field in index.fields] == [
        "id",
        "document_id",
        "ordinal",
        "title",
        "source",
        "page",
        "section",
        "content",
        "content_vector",
        "access_groups",
        "access_public",
    ]


class PolicyExtractor:
    async def extract(self, *, data: bytes) -> ExtractedText:
        assert data == b"%PDF"
        travel = POLICY.index("# Travel")
        return ExtractedText(
            content=POLICY,
            pages=(
                ExtractedPage(number=1, start=0, end=travel),
                ExtractedPage(number=2, start=travel, end=len(POLICY)),
            ),
        )


class EmbeddingResponse:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data

    def model_dump(self) -> object:
        return {"data": self.data}


async def aembedding(**kwargs: object) -> object:
    texts = kwargs["input"]
    assert isinstance(texts, list)
    data: list[dict[str, object]] = [
        {"index": index, "embedding": [float("refund" in str(text).lower()), 1.0]}
        for index, text in enumerate(texts)
    ]
    return EmbeddingResponse(data)


class MemoryIndex:
    def __init__(self) -> None:
        self.chunks: dict[str, IndexedChunk] = {}

    async def upsert(self, *, chunks: tuple[IndexedChunk, ...]) -> None:
        self.chunks.update((chunk.key, chunk) for chunk in chunks)

    async def delete(self, *, document_id: str) -> None:
        self.chunks = {
            key: chunk
            for key, chunk in self.chunks.items()
            if chunk.citation.document_id != document_id
        }

    async def search(
        self, *, query: SearchQuery, vector: tuple[float, ...]
    ) -> tuple[Passage, ...]:
        visible = [
            chunk
            for chunk in self.chunks.values()
            if query.scope.allows(access=chunk.access)
        ]
        ranked = sorted(
            visible,
            key=lambda chunk: (
                -sum(a * b for a, b in zip(chunk.vector, vector, strict=True))
            ),
        )
        return tuple(
            Passage(text=chunk.text, citation=chunk.citation, score=1.0)
            for chunk in ranked[: query.top_k]
        )


def test_public_api_ingests_retrieves_with_citations_and_evaluates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = ModuleType("litellm")
    vars(sdk).update(EmbeddingResponse=EmbeddingResponse, aembedding=aembedding)
    monkeypatch.setitem(sys.modules, "litellm", sdk)
    embedder = create_litellm_embedder(
        config=EmbeddingConfig(model="azure/embeddings", api_key="test-key")
    )
    index = MemoryIndex()
    ingestion = IngestionService(
        extractor=PolicyExtractor(), embedder=embedder, index=index
    )
    finance = AccessScope(groups=frozenset({"finance"}))
    document = SourceDocument(
        document_id="policy", title="Policy", data=b"%PDF", access=finance
    )
    assert asyncio.run(ingestion.ingest(document=document)).chunks == 2
    assert asyncio.run(ingestion.ingest(document=document)).chunks == 2
    assert len(index.chunks) == 2

    retrieval = RetrievalService(embedder=embedder, retriever=index)
    query = SearchQuery(text="refund time", scope=finance, top_k=1)
    (passage,) = asyncio.run(retrieval.retrieve(query=query))
    assert passage.text == "# Refunds\n\nRefunds take five days."
    assert (passage.citation.page, passage.citation.section) == (1, "Refunds")

    outsider = SearchQuery(text="refund time", scope=AccessScope(public=True))
    assert asyncio.run(retrieval.retrieve(query=outsider)) == ()

    metrics = evaluate_retrieval(
        dataset=(LabelledQuery(query_id="q", relevant_ids=frozenset({"policy"})),),
        results={"q": [passage.citation.document_id]},
        k=1,
    )
    assert metrics == RetrievalMetrics(k=1, queries=1, recall_at_k=1.0, mrr=1.0)
