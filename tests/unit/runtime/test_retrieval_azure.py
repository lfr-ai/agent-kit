import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from itertools import cycle
import math
import traceback
from types import TracebackType
from typing import Final, override

from azure.core.credentials import AccessToken, AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.search.documents.indexes.models import SearchIndex
from azure.search.documents.models import IndexingResult, VectorizedQuery
import pytest

from platform_kit_runtime.core.retrieval.models import (
    AccessScope,
    AzureSearchConfig,
    Citation,
    IndexedChunk,
    Passage,
    RetrievalAuthenticationError,
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalUnavailableError,
    SearchQuery,
    chunk_key,
)
from platform_kit_runtime.infrastructure.retrieval.azure_search import (
    AzureSearchIndex,
    IndexField,
    open_azure_search_index,
    search_index_definition,
    security_filter,
)

pytestmark = pytest.mark.unit

type Item = dict[str, object]

SENSITIVE: Final[str] = "service-diagnostic-with-token-abc123"
ENDPOINT: Final[str] = "https://search.example.net"
CONFIG: Final[AzureSearchConfig] = AzureSearchConfig(
    endpoint=ENDPOINT, index_name="chunks"
)
SEMANTIC: Final[AzureSearchConfig] = AzureSearchConfig(
    endpoint=ENDPOINT, index_name="chunks", semantic_configuration="default"
)
GROUPS: Final[AccessScope] = AccessScope(groups=frozenset({"hr", "eng"}))
PUBLIC: Final[AccessScope] = AccessScope(public=True)
ROW: Final[Item] = {
    "id": "key",
    "document_id": "doc-1",
    "title": "Handbook",
    "source": None,
    "page": 3,
    "section": "Intro",
    "content": "Refunds take five days.",
    "@search.score": 0.25,
    "@search.reranker_score": None,
}


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


class FakeSearchClient:
    def __init__(
        self,
        *,
        items: Sequence[Item] = (),
        statuses: Sequence[int] = (201,),
        dropped: int = 0,
        call_failure: Exception | None = None,
        iteration_failure: Exception | None = None,
    ) -> None:
        self.items = items
        self.statuses = statuses
        self.dropped = dropped
        self.call_failure = call_failure
        self.iteration_failure = iteration_failure
        self.searches: list[tuple[str | None, dict[str, object]]] = []
        self.uploads: list[list[Item]] = []
        self.deletes: list[list[Item]] = []

    async def search(
        self, search_text: str | None = None, **options: object
    ) -> AsyncIterator[Item]:
        self.searches.append((search_text, options))
        if self.call_failure is not None:
            raise self.call_failure
        return self._results()

    async def _results(self) -> AsyncIterator[Item]:
        for item in self.items:
            yield item
        if self.iteration_failure is not None:
            raise self.iteration_failure

    def _indexing(self, documents: list[Item]) -> list[IndexingResult]:
        if self.call_failure is not None:
            raise self.call_failure
        results = [
            IndexingResult(
                {"key": document["id"], "status": status < 300, "statusCode": status}
            )
            for document, status in zip(documents, cycle(self.statuses), strict=False)
        ]
        return results[self.dropped :]

    async def upload_documents(self, documents: list[Item]) -> list[IndexingResult]:
        self.uploads.append(documents)
        return self._indexing(documents)

    async def delete_documents(self, documents: list[Item]) -> list[IndexingResult]:
        self.deletes.append(documents)
        return self._indexing(documents)


def http_error(status: int | None) -> HttpResponseError:
    error = HttpResponseError(message=SENSITIVE)
    error.status_code = status
    return error


def unchecked[ResultT](function: Callable[..., ResultT]) -> Callable[..., ResultT]:
    return function


def chunk(ordinal: int = 0) -> IndexedChunk:
    return IndexedChunk(
        citation=Citation(
            document_id="doc-1",
            title="Handbook",
            source="https://files.example/handbook.pdf",
            page=2,
            section="Intro",
        ),
        ordinal=ordinal,
        text="Refunds take five days.",
        vector=(0.5, 1.0),
        access=GROUPS,
    )


def query(scope: AccessScope = GROUPS, *, top_k: int = 2) -> SearchQuery:
    return SearchQuery(text="refund", scope=scope, top_k=top_k)


def search(
    client: FakeSearchClient,
    *,
    config: AzureSearchConfig = CONFIG,
    request: SearchQuery | None = None,
) -> tuple[Passage, ...]:
    index = AzureSearchIndex(client=client, config=config)
    return asyncio.run(index.search(query=request or query(), vector=(0.5, 1.0)))


def assert_sanitized(error: BaseException, expected: type[RetrievalError]) -> None:
    assert type(error) is expected
    assert str(error) == expected.message
    assert type(error.__cause__) is RetrievalError
    assert error.__cause__.__cause__ is None
    assert error.__context__ is None
    assert SENSITIVE not in "".join(traceback.format_exception(error))


def test_upsert_writes_index_documents_in_service_batches() -> None:
    client = FakeSearchClient()
    chunks = tuple(chunk(ordinal) for ordinal in range(1001))
    asyncio.run(AzureSearchIndex(client=client, config=CONFIG).upsert(chunks=chunks))
    assert [len(batch) for batch in client.uploads] == [1000, 1]
    assert client.uploads[0][0] == {
        "id": chunk_key(document_id="doc-1", ordinal=0),
        "document_id": "doc-1",
        "ordinal": 0,
        "title": "Handbook",
        "source": "https://files.example/handbook.pdf",
        "page": 2,
        "section": "Intro",
        "content": "Refunds take five days.",
        "content_vector": [0.5, 1.0],
        "access_groups": ["eng", "hr"],
        "access_public": False,
    }


def test_empty_upsert_makes_no_call() -> None:
    client = FakeSearchClient()
    asyncio.run(AzureSearchIndex(client=client, config=CONFIG).upsert(chunks=()))
    assert client.uploads == []


@pytest.mark.parametrize(
    ("statuses", "dropped", "expected"),
    [
        ((201, 503), 0, RetrievalUnavailableError),
        ((409, 422), 0, RetrievalUnavailableError),
        ((201, 400), 0, RetrievalConfigurationError),
        ((503, 404), 0, RetrievalConfigurationError),
        ((201,), 1, RetrievalProtocolError),
    ],
)
def test_partial_indexing_failures_are_typed(
    statuses: tuple[int, ...], dropped: int, expected: type[RetrievalError]
) -> None:
    client = FakeSearchClient(statuses=statuses, dropped=dropped)
    index = AzureSearchIndex(client=client, config=CONFIG)
    with pytest.raises(expected):
        asyncio.run(index.upsert(chunks=(chunk(0), chunk(1))))


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ClientAuthenticationError(message=SENSITIVE), RetrievalAuthenticationError),
        (ServiceRequestError(SENSITIVE), RetrievalUnavailableError),
        (ServiceResponseError(SENSITIVE), RetrievalUnavailableError),
        (TimeoutError(SENSITIVE), RetrievalUnavailableError),
        (http_error(401), RetrievalAuthenticationError),
        (http_error(403), RetrievalAuthenticationError),
        (http_error(408), RetrievalUnavailableError),
        (http_error(429), RetrievalUnavailableError),
        (http_error(503), RetrievalUnavailableError),
        (http_error(400), RetrievalConfigurationError),
        (http_error(404), RetrievalConfigurationError),
        (http_error(302), RetrievalProtocolError),
        (http_error(None), RetrievalProtocolError),
        (RuntimeError(SENSITIVE), RetrievalProtocolError),
    ],
)
def test_sdk_failures_are_classified_without_service_text(
    failure: Exception, expected: type[RetrievalError]
) -> None:
    index = AzureSearchIndex(
        client=FakeSearchClient(call_failure=failure), config=CONFIG
    )
    with pytest.raises(expected) as caught:
        asyncio.run(index.upsert(chunks=(chunk(),)))
    assert_sanitized(caught.value, expected)


def test_delete_removes_every_ordinal_up_to_the_stored_maximum() -> None:
    client = FakeSearchClient(items=[{"ordinal": 2}])
    asyncio.run(
        AzureSearchIndex(client=client, config=CONFIG).delete(document_id="it's")
    )
    assert client.searches == [
        (
            None,
            {
                "filter": "document_id eq 'it''s'",
                "order_by": ["ordinal desc"],
                "top": 1,
            },
        )
    ]
    assert client.deletes == [
        [{"id": chunk_key(document_id="it's", ordinal=n)} for n in range(3)]
    ]


def test_delete_batches_large_documents_and_skips_missing_ones() -> None:
    client = FakeSearchClient(items=[{"ordinal": 1000}])
    index = AzureSearchIndex(client=client, config=CONFIG)
    asyncio.run(index.delete(document_id="doc-1"))
    assert [len(batch) for batch in client.deletes] == [1000, 1]

    empty = FakeSearchClient()
    asyncio.run(
        AzureSearchIndex(client=empty, config=CONFIG).delete(document_id="doc-1")
    )
    assert empty.deletes == []


@pytest.mark.parametrize("item", [{"ordinal": -1}, {"ordinal": True}, {}])
def test_delete_rejects_malformed_ordinals(item: Item) -> None:
    client = FakeSearchClient(items=[item])
    index = AzureSearchIndex(client=client, config=CONFIG)
    with pytest.raises(RetrievalProtocolError):
        asyncio.run(index.delete(document_id="doc-1"))
    assert client.deletes == []


def test_delete_reports_failed_actions() -> None:
    client = FakeSearchClient(items=[{"ordinal": 0}], statuses=(503,))
    index = AzureSearchIndex(client=client, config=CONFIG)
    with pytest.raises(RetrievalUnavailableError):
        asyncio.run(index.delete(document_id="doc-1"))


def test_security_filter_fails_closed_to_public_or_shared_groups() -> None:
    assert security_filter(PUBLIC) == "access_public eq true"
    assert security_filter(GROUPS) == (
        "access_public eq true or access_groups/any(g: search.in(g, 'eng|hr', '|'))"
    )
    quoted = AccessScope(groups=frozenset({"o'neil"}))
    assert "'o''neil'" in security_filter(quoted)


def test_delimiter_in_group_is_rejected_before_any_request() -> None:
    client = FakeSearchClient(items=[ROW])
    unsafe = AccessScope(groups=frozenset({"hr|admins"}))
    with pytest.raises(RetrievalConfigurationError):
        search(client, request=query(unsafe))
    assert client.searches == []


def test_hybrid_search_is_trimmed_and_returns_cited_passages() -> None:
    client = FakeSearchClient(items=[ROW, ROW, ROW])
    passages = search(client)
    assert (
        passages
        == (
            Passage(
                text="Refunds take five days.",
                citation=Citation(
                    document_id="doc-1", title="Handbook", page=3, section="Intro"
                ),
                score=0.25,
            ),
        )
        * 2
    )
    text, options = client.searches[0]
    vectors = options.pop("vector_queries")
    assert text == "refund"
    assert options == {
        "filter": security_filter(GROUPS),
        "query_type": None,
        "semantic_configuration_name": None,
        "top": 2,
    }
    assert isinstance(vectors, list)
    assert len(vectors) == 1
    vector = vectors[0]
    assert isinstance(vector, VectorizedQuery)
    assert (vector.vector, vector.k_nearest_neighbors, vector.fields) == (
        [0.5, 1.0],
        2,
        "content_vector",
    )


def test_semantic_ranking_uses_full_candidate_window_and_reranker_score() -> None:
    client = FakeSearchClient(items=[{**ROW, "@search.reranker_score": 3}])
    passages = search(client, config=SEMANTIC, request=query(PUBLIC))
    assert [passage.score for passage in passages] == [3.0]
    _, options = client.searches[0]
    assert options["filter"] == "access_public eq true"
    assert options["query_type"] == "semantic"
    assert options["semantic_configuration_name"] == "default"
    vectors = options["vector_queries"]
    assert isinstance(vectors, list)
    assert vectors[0].k_nearest_neighbors == 50


@pytest.mark.parametrize(
    "changes",
    [
        {"content": None},
        {"title": 1},
        {"document_id": " "},
        {"source": 5},
        {"page": 0},
        {"page": True},
        {"@search.score": "high"},
        {"@search.score": math.nan},
        {"@search.score": True},
        {"@search.score": None},
    ],
)
def test_malformed_results_raise_protocol_errors(changes: Item) -> None:
    with pytest.raises(RetrievalProtocolError):
        search(FakeSearchClient(items=[{**ROW, **changes}]))


def test_non_mapping_results_raise_protocol_errors() -> None:
    with pytest.raises(RetrievalProtocolError):
        search(unchecked(FakeSearchClient)(items=["not a document"]))


def test_unknown_page_is_cited_without_page() -> None:
    (passage,) = search(FakeSearchClient(items=[{**ROW, "page": None}]))
    assert passage.citation.page is None


def test_failures_while_iterating_results_are_sanitized() -> None:
    client = FakeSearchClient(items=[ROW], iteration_failure=http_error(503))
    with pytest.raises(RetrievalUnavailableError) as caught:
        search(client)
    assert_sanitized(caught.value, RetrievalUnavailableError)


def fields_by_name(definition: dict[str, object]) -> dict[str, dict[str, object]]:
    fields = definition["fields"]
    assert isinstance(fields, list)
    return {field["name"]: field for field in fields}


def test_index_definition_matches_the_adapter_contract() -> None:
    definition = search_index_definition(config=CONFIG, dimensions=1536)
    fields = fields_by_name(definition)
    assert definition["name"] == "chunks"
    assert "semantic" not in definition
    assert list(fields) == list(IndexField)
    assert fields["id"]["key"] is True
    assert fields["ordinal"]["sortable"] is True
    assert fields["content_vector"]["dimensions"] == 1536
    assert fields["content_vector"]["retrievable"] is False
    for name in ("document_id", "access_groups", "access_public"):
        assert fields[name]["filterable"] is True
    for name in ("access_groups", "access_public"):
        assert fields[name]["retrievable"] is False
    assert SearchIndex(definition).name == "chunks"


def test_index_definition_adds_semantic_configuration_when_configured() -> None:
    definition = search_index_definition(config=SEMANTIC, dimensions=3)
    assert definition["semantic"] == {
        "configurations": [
            {
                "name": "default",
                "prioritizedFields": {
                    "titleField": {"fieldName": "title"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                },
            }
        ]
    }


@pytest.mark.parametrize("dimensions", [0, -1, True, 1.5])
def test_index_definition_rejects_invalid_dimensions(dimensions: object) -> None:
    with pytest.raises(RetrievalConfigurationError):
        unchecked(search_index_definition)(config=CONFIG, dimensions=dimensions)


def test_open_requires_an_entra_token_credential() -> None:
    opener = unchecked(open_azure_search_index)

    async def open_with(credential: object) -> AzureSearchIndex:
        async with opener(config=CONFIG, credential=credential) as index:
            return index

    with pytest.raises(RetrievalConfigurationError):
        asyncio.run(open_with(AzureKeyCredential("key")))
    assert isinstance(asyncio.run(open_with(FakeCredential())), AzureSearchIndex)
