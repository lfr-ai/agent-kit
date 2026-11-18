"""Azure AI Search hybrid index adapter with fail-closed security trimming."""

from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from enum import StrEnum, auto, unique
from http import HTTPStatus
from itertools import batched
from math import isfinite
from typing import Protocol

from azure.core.credentials_async import AsyncTokenCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import IndexingResult, VectorizedQuery

from platform_kit_runtime.core.retrieval.models import (
    AccessScope,
    AzureSearchConfig,
    Citation,
    IndexedChunk,
    Passage,
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalUnavailableError,
    SearchQuery,
    chunk_key,
)
from platform_kit_runtime.core.validation import is_nonblank
from platform_kit_runtime.infrastructure.retrieval.azure_failures import (
    classify_azure_failure,
)
from platform_kit_runtime.infrastructure.retrieval.failures import retrieval_failure

# Azure AI Search accepts at most 1,000 actions per indexing request.
_BATCH_SIZE = 1000
# The semantic ranker rescores up to 50 hybrid results; give it a full window.
_SEMANTIC_CANDIDATES = 50
_GROUP_DELIMITER = "|"
_HNSW = "hnsw"
_VECTOR_PROFILE = "content-vector"
_TRANSIENT_INDEXING_STATUSES = frozenset(
    {
        HTTPStatus.CONFLICT,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        HTTPStatus.SERVICE_UNAVAILABLE,
    }
)


@unique
class IndexField(StrEnum):
    """Field names of the chunk index created by ``search_index_definition``."""

    ID = auto()
    DOCUMENT_ID = auto()
    ORDINAL = auto()
    TITLE = auto()
    SOURCE = auto()
    PAGE = auto()
    SECTION = auto()
    CONTENT = auto()
    CONTENT_VECTOR = auto()
    ACCESS_GROUPS = auto()
    ACCESS_PUBLIC = auto()


class AzureSearchClient(Protocol):
    """Subset of the asynchronous ``SearchClient`` used by the adapter."""

    async def search(
        self,
        search_text: str | None = None,
        *,
        filter: str | None = None,  # noqa: A002 - mirrors the SDK keyword
        order_by: list[str] | None = None,
        query_type: str | None = None,
        semantic_configuration_name: str | None = None,
        top: int | None = None,
        vector_queries: list[VectorizedQuery] | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Start a query; the service is called while the result is iterated."""
        ...

    async def upload_documents(
        self, documents: list[dict[str, object]]
    ) -> list[IndexingResult]:
        """Insert or replace documents by key."""
        ...

    async def delete_documents(
        self, documents: list[dict[str, object]]
    ) -> list[IndexingResult]:
        """Delete documents by key; absent keys succeed."""
        ...


def _quoted(value: str) -> str:
    """Return an OData string literal."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def security_filter(scope: AccessScope) -> str:
    """Return the OData filter that trims results to ``scope``.

    Public scopes see only public chunks; group scopes also see chunks shared
    with a reader group. Raises ``RetrievalConfigurationError`` when a group
    contains the ``|`` delimiter.
    """
    public = f"{IndexField.ACCESS_PUBLIC} eq true"
    if scope.public:
        return public
    if any(_GROUP_DELIMITER in group for group in scope.groups):
        raise RetrievalConfigurationError
    groups = _quoted(_GROUP_DELIMITER.join(sorted(scope.groups)))
    delimiter = _quoted(_GROUP_DELIMITER)
    shared = f"{IndexField.ACCESS_GROUPS}/any(g: search.in(g, {groups}, {delimiter}))"
    return f"{public} or {shared}"


def _document_filter(document_id: str) -> str:
    return f"{IndexField.DOCUMENT_ID} eq {_quoted(document_id)}"


async def _guarded[ResultT](operation: Awaitable[ResultT]) -> ResultT:
    """Await an SDK operation and replace any failure with a content-free error."""
    try:
        return await operation
    except Exception as error:  # noqa: BLE001 - SDK failures must not leak service diagnostics
        kind = classify_azure_failure(error)
    raise retrieval_failure(kind) from RetrievalError()


def _check_indexing(results: Sequence[IndexingResult], *, expected: int) -> None:
    """Fail unless every action in a batch succeeded."""
    if len(results) != expected:
        raise RetrievalProtocolError
    failed = [result.status_code for result in results if result.succeeded is not True]
    if not failed:
        return
    if all(status in _TRANSIENT_INDEXING_STATUSES for status in failed):
        raise RetrievalUnavailableError
    raise RetrievalConfigurationError


def _document(chunk: IndexedChunk) -> dict[str, object]:
    citation = chunk.citation
    return {
        IndexField.ID: chunk.key,
        IndexField.DOCUMENT_ID: citation.document_id,
        IndexField.ORDINAL: chunk.ordinal,
        IndexField.TITLE: citation.title,
        IndexField.SOURCE: citation.source,
        IndexField.PAGE: citation.page,
        IndexField.SECTION: citation.section,
        IndexField.CONTENT: chunk.text,
        IndexField.CONTENT_VECTOR: list(chunk.vector),
        IndexField.ACCESS_GROUPS: sorted(chunk.access.groups),
        IndexField.ACCESS_PUBLIC: chunk.access.public,
    }


def _text(item: dict[str, object], name: IndexField) -> str:
    value = item.get(name)
    if not isinstance(value, str):
        raise RetrievalProtocolError
    return value


def _optional_text(item: dict[str, object], name: IndexField) -> str | None:
    value = item.get(name)
    if value is not None and not isinstance(value, str):
        raise RetrievalProtocolError
    return value


def _ordinal(value: object) -> int:
    if type(value) is not int or value < 0:
        raise RetrievalProtocolError
    return value


def _page(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise RetrievalProtocolError
    return value


def _score(item: dict[str, object]) -> float:
    reranked = item.get("@search.reranker_score")
    value = item.get("@search.score") if reranked is None else reranked
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RetrievalProtocolError
    if not isfinite(value):
        raise RetrievalProtocolError
    return float(value)


def _passage(item: object) -> Passage:
    if not isinstance(item, dict):
        raise RetrievalProtocolError
    document_id = _text(item, IndexField.DOCUMENT_ID)
    if not is_nonblank(document_id):
        raise RetrievalProtocolError
    citation = Citation(
        document_id=document_id,
        title=_text(item, IndexField.TITLE),
        source=_optional_text(item, IndexField.SOURCE),
        page=_page(item.get(IndexField.PAGE)),
        section=_optional_text(item, IndexField.SECTION),
    )
    return Passage(
        text=_text(item, IndexField.CONTENT), citation=citation, score=_score(item)
    )


class AzureSearchIndex:
    """Hybrid ``DocumentIndex`` and ``Retriever`` over one Azure AI Search index."""

    def __init__(self, *, client: AzureSearchClient, config: AzureSearchConfig) -> None:
        """Bind a caller-owned client to the index settings.

        Args:
            client (AzureSearchClient): Open asynchronous search client.
            config (AzureSearchConfig): Index and semantic ranker settings.
        """
        self._client = client
        self._config = config

    async def upsert(self, *, chunks: Sequence[IndexedChunk]) -> None:
        """Upload ``chunks`` in service-sized batches, replacing equal keys.

        Rejected documents raise ``RetrievalConfigurationError``; a busy or
        unreachable index raises ``RetrievalUnavailableError``.
        """
        for batch in batched(map(_document, chunks), _BATCH_SIZE, strict=False):
            documents = list(batch)
            results = await _guarded(self._client.upload_documents(documents))
            _check_indexing(results, expected=len(documents))

    async def _last_ordinal(self, document_id: str) -> int | None:
        results = await self._client.search(
            filter=_document_filter(document_id),
            order_by=[f"{IndexField.ORDINAL} desc"],
            top=1,
        )
        async for item in results:
            return _ordinal(item.get(IndexField.ORDINAL))
        return None

    async def delete(self, *, document_id: str) -> None:
        """Delete every chunk key of ``document_id`` up to its highest ordinal.

        Failures raise the same typed errors as ``upsert``.
        """
        last = await _guarded(self._last_ordinal(document_id))
        if last is None:
            return
        keys = (chunk_key(document_id=document_id, ordinal=n) for n in range(last + 1))
        for batch in batched(keys, _BATCH_SIZE, strict=False):
            documents: list[dict[str, object]] = [{IndexField.ID: key} for key in batch]
            results = await _guarded(self._client.delete_documents(documents))
            _check_indexing(results, expected=len(documents))

    async def _query(
        self, *, query: SearchQuery, vector: tuple[float, ...], trimming: str
    ) -> list[dict[str, object]]:
        semantic = self._config.semantic_configuration
        neighbors = query.top_k if semantic is None else _SEMANTIC_CANDIDATES
        vector_query = VectorizedQuery(
            vector=list(vector),
            k_nearest_neighbors=max(neighbors, query.top_k),
            fields=IndexField.CONTENT_VECTOR,
        )
        results = await self._client.search(
            query.text,
            filter=trimming,
            query_type=None if semantic is None else "semantic",
            semantic_configuration_name=semantic,
            top=query.top_k,
            vector_queries=[vector_query],
        )
        items: list[dict[str, object]] = []
        async for item in results:
            items.append(item)
            if len(items) == query.top_k:
                break
        return items

    async def search(
        self, *, query: SearchQuery, vector: tuple[float, ...]
    ) -> tuple[Passage, ...]:
        """Run a security-trimmed hybrid query, reranked when configured.

        Invalid scopes or rejected requests raise ``RetrievalConfigurationError``
        and malformed results raise ``RetrievalProtocolError``.

        Args:
            query (SearchQuery): Query text, reader scope and result count.
            vector (tuple[float, ...]): Embedding of the query text.

        Returns:
            tuple[Passage, ...]: Cited passages in service relevance order.
        """
        trimming = security_filter(query.scope)
        items = await _guarded(
            self._query(query=query, vector=vector, trimming=trimming)
        )
        return tuple(_passage(item) for item in items)


def search_index_definition(
    *, config: AzureSearchConfig, dimensions: int
) -> dict[str, object]:
    """Return the REST definition of an index that this adapter can use.

    Args:
        config (AzureSearchConfig): Index name and optional semantic configuration.
        dimensions (int): Embedding size; must match the embedding model output.

    Returns:
        dict[str, object]: Index JSON for the SDK, REST API or infrastructure code.

    Raises:
        RetrievalConfigurationError: ``dimensions`` is not a positive integer.
    """
    if type(dimensions) is not int or dimensions < 1:
        raise RetrievalConfigurationError
    fields: list[SearchField] = [
        SimpleField(name=IndexField.ID, type=SearchFieldDataType.STRING, key=True),
        SimpleField(
            name=IndexField.DOCUMENT_ID,
            type=SearchFieldDataType.STRING,
            filterable=True,
        ),
        SimpleField(
            name=IndexField.ORDINAL,
            type=SearchFieldDataType.INT32,
            filterable=True,
            sortable=True,
        ),
        SearchableField(name=IndexField.TITLE),
        SimpleField(name=IndexField.SOURCE, type=SearchFieldDataType.STRING),
        SimpleField(name=IndexField.PAGE, type=SearchFieldDataType.INT32),
        SearchableField(name=IndexField.SECTION),
        SearchableField(name=IndexField.CONTENT),
        SearchField(
            name=IndexField.CONTENT_VECTOR,
            type=SearchFieldDataType.Collection(SearchFieldDataType.SINGLE),
            searchable=True,
            retrievable=False,
            vector_search_dimensions=dimensions,
            vector_search_profile_name=_VECTOR_PROFILE,
        ),
        SimpleField(
            name=IndexField.ACCESS_GROUPS,
            type=SearchFieldDataType.Collection(SearchFieldDataType.STRING),
            filterable=True,
            hidden=True,
        ),
        SimpleField(
            name=IndexField.ACCESS_PUBLIC,
            type=SearchFieldDataType.BOOLEAN,
            filterable=True,
            hidden=True,
        ),
    ]
    semantic = config.semantic_configuration
    semantic_search = None
    if semantic is not None:
        prioritized = SemanticPrioritizedFields(
            title_field=SemanticField(field_name=IndexField.TITLE),
            content_fields=[SemanticField(field_name=IndexField.CONTENT)],
        )
        semantic_search = SemanticSearch(
            configurations=[
                SemanticConfiguration(name=semantic, prioritized_fields=prioritized)
            ]
        )
    index = SearchIndex(
        name=config.index_name,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name=_HNSW)],
            profiles=[
                VectorSearchProfile(
                    name=_VECTOR_PROFILE, algorithm_configuration_name=_HNSW
                )
            ],
        ),
        semantic_search=semantic_search,
    )
    return index.as_dict()


@asynccontextmanager
async def open_azure_search_index(
    *, config: AzureSearchConfig, credential: AsyncTokenCredential
) -> AsyncGenerator[AzureSearchIndex]:
    """Own an asynchronous search client authenticated with Microsoft Entra ID.

    Args:
        config (AzureSearchConfig): Endpoint, index and semantic settings.
        credential (AsyncTokenCredential): Caller-owned asynchronous token credential.

    Yields:
        AzureSearchIndex: Adapter bound to the open client.

    Raises:
        RetrievalConfigurationError: The credential is not an async token credential.
    """
    if not isinstance(credential, AsyncTokenCredential):
        raise RetrievalConfigurationError
    async with SearchClient(
        endpoint=config.endpoint, index_name=config.index_name, credential=credential
    ) as client:
        yield AzureSearchIndex(client=client, config=config)
