import asyncio
from collections.abc import Callable, Sequence
from dataclasses import replace
import traceback
from types import TracebackType
from typing import IO, Final, override

from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AccessToken, AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ServiceRequestError,
)
import pytest

from platform_kit_runtime.core.retrieval.ocr import (
    ExtractedPage,
    ExtractedText,
    OCRAuthenticationError,
    OCRConfig,
    OCRConfigurationError,
    OCRDocumentError,
    OCRError,
    OCRModel,
    OCRProtocolError,
    OCRUnavailableError,
)
from platform_kit_runtime.infrastructure.retrieval.ocr import (
    DocumentIntelligenceExtractor,
    open_document_intelligence,
)

pytestmark = pytest.mark.unit

SENSITIVE: Final[str] = "service-diagnostic-with-token-abc123"
CONFIG: Final[OCRConfig] = OCRConfig(endpoint="https://ocr.example.net")
FIRST: Final[str] = "# Title\n\nBody"
SECOND: Final[str] = "Page two"
CONTENT: Final[str] = f"{FIRST}\n<!-- PageBreak -->\n{SECOND}"
PAGES: Final[list[dict[str, object]]] = [
    {
        "pageNumber": 2,
        "spans": [{"offset": CONTENT.index(SECOND), "length": len(SECOND)}],
    },
    {"pageNumber": 1, "spans": [{"offset": 0, "length": len(FIRST)}]},
]


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


def analysis(
    content: object = CONTENT, pages: Sequence[object] = PAGES
) -> AnalyzeResult:
    return AnalyzeResult(
        {
            "apiVersion": "2024-11-30",
            "modelId": "prebuilt-layout",
            "stringIndexType": "unicodeCodePoint",
            "content": content,
            "pages": list(pages),
        }
    )


class FakePoller:
    def __init__(self, *, result: AnalyzeResult, failure: Exception | None) -> None:
        self._result = result
        self._failure = failure

    async def result(self) -> AnalyzeResult:
        if self._failure is not None:
            raise self._failure
        return self._result


class FakeAnalysisClient:
    def __init__(
        self,
        *,
        result: AnalyzeResult | None = None,
        start_failure: Exception | None = None,
        poll_failure: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.result = analysis() if result is None else result
        self.start_failure = start_failure
        self.poll_failure = poll_failure
        self.delay = delay
        self.calls: list[tuple[str, bytes, str | None, str | None]] = []

    async def begin_analyze_document(
        self,
        model_id: str,
        body: IO[bytes],
        *,
        string_index_type: str | None = None,
        output_content_format: str | None = None,
    ) -> FakePoller:
        self.calls.append(
            (model_id, body.read(), string_index_type, output_content_format)
        )
        await asyncio.sleep(self.delay)
        if self.start_failure is not None:
            raise self.start_failure
        return FakePoller(result=self.result, failure=self.poll_failure)


def http_error(status: int) -> HttpResponseError:
    error = HttpResponseError(message=SENSITIVE)
    error.status_code = status
    return error


def unchecked[ResultT](function: Callable[..., ResultT]) -> Callable[..., ResultT]:
    return function


def extract(
    client: FakeAnalysisClient, *, config: OCRConfig = CONFIG, data: bytes = b"%PDF-1.7"
) -> ExtractedText:
    extractor = DocumentIntelligenceExtractor(client=client, config=config)
    return asyncio.run(extractor.extract(data=data))


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint": "http://ocr.example.net"},
        {"endpoint": "https://user:pass@ocr.example.net"},
        {"model": "prebuilt-invoice"},
        {"max_document_bytes": 0},
        {"max_document_bytes": 500_000_001},
        {"max_document_bytes": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": 3601},
        {"timeout_seconds": float("inf")},
    ],
)
def test_config_rejects_invalid_settings(changes: dict[str, object]) -> None:
    with pytest.raises(OCRConfigurationError):
        replace(CONFIG, **changes)


def test_config_defaults_to_layout_within_service_limits() -> None:
    assert CONFIG.model is OCRModel.LAYOUT
    assert CONFIG.max_document_bytes == 500_000_000
    assert replace(CONFIG, max_document_bytes=4_000_000).max_document_bytes == 4_000_000


def test_page_lookup_uses_last_page_starting_before_offset() -> None:
    text = ExtractedText(
        content="ab\ncd",
        pages=(
            ExtractedPage(number=1, start=0, end=2),
            ExtractedPage(number=2, start=3, end=5),
        ),
    )
    assert [text.page_at(offset) for offset in range(5)] == [1, 1, 1, 2, 2]
    assert ExtractedText(content="x").page_at(0) is None
    assert "ab" not in repr(text)


def test_layout_requests_markdown_and_maps_sorted_pages() -> None:
    client = FakeAnalysisClient()
    extracted = extract(client)
    assert client.calls == [
        ("prebuilt-layout", b"%PDF-1.7", "unicodeCodePoint", "markdown")
    ]
    assert extracted == ExtractedText(
        content=CONTENT,
        pages=(
            ExtractedPage(number=1, start=0, end=len(FIRST)),
            ExtractedPage(number=2, start=CONTENT.index(SECOND), end=len(CONTENT)),
        ),
    )


def test_read_model_returns_plain_text_without_markdown_option() -> None:
    client = FakeAnalysisClient()
    extract(client, config=replace(CONFIG, model=OCRModel.READ))
    assert client.calls[0][0] == "prebuilt-read"
    assert client.calls[0][3] is None


def test_pages_cover_all_spans_and_spanless_pages_are_skipped() -> None:
    pages = [
        {
            "pageNumber": 1,
            "spans": [{"offset": 9, "length": 4}, {"offset": 0, "length": 3}],
        },
        {"pageNumber": 2, "spans": []},
        {"pageNumber": 3},
    ]
    extracted = extract(FakeAnalysisClient(result=analysis(pages=pages)))
    assert extracted.pages == (ExtractedPage(number=1, start=0, end=13),)


@pytest.mark.parametrize(
    ("data", "limit"),
    [(b"", 10), (b"12345", 4), (bytearray(b"12"), 10), ("text", 10)],
)
def test_invalid_input_is_rejected_before_upload(data: object, limit: int) -> None:
    client = FakeAnalysisClient()
    extractor = DocumentIntelligenceExtractor(
        client=client, config=replace(CONFIG, max_document_bytes=limit)
    )
    with pytest.raises(OCRDocumentError):
        asyncio.run(unchecked(extractor.extract)(data=data))
    assert client.calls == []


@pytest.mark.parametrize(
    "result",
    [
        analysis(content=None),
        analysis(pages=[{"pageNumber": 0, "spans": [{"offset": 0, "length": 1}]}]),
        analysis(pages=[{"spans": [{"offset": 0, "length": 1}]}]),
        analysis(pages=[{"pageNumber": 1, "spans": [{"offset": -1, "length": 1}]}]),
        analysis(pages=[{"pageNumber": 1, "spans": [{"offset": 0, "length": "x"}]}]),
        analysis(pages=[{"pageNumber": 1, "spans": [{"offset": 0, "length": 999}]}]),
    ],
)
def test_malformed_results_raise_protocol_errors(result: AnalyzeResult) -> None:
    with pytest.raises(OCRProtocolError):
        extract(FakeAnalysisClient(result=result))


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (http_error(400), OCRDocumentError),
        (http_error(413), OCRDocumentError),
        (http_error(415), OCRDocumentError),
        (http_error(401), OCRAuthenticationError),
        (ClientAuthenticationError(message=SENSITIVE), OCRAuthenticationError),
        (http_error(404), OCRConfigurationError),
        (http_error(429), OCRUnavailableError),
        (http_error(503), OCRUnavailableError),
        (ServiceRequestError(SENSITIVE), OCRUnavailableError),
        (RuntimeError(SENSITIVE), OCRProtocolError),
    ],
)
@pytest.mark.parametrize("stage", ["start", "poll"])
def test_sdk_failures_are_typed_and_sanitized(
    failure: Exception, expected: type[OCRError], stage: str
) -> None:
    client = (
        FakeAnalysisClient(start_failure=failure)
        if stage == "start"
        else FakeAnalysisClient(poll_failure=failure)
    )
    with pytest.raises(expected) as caught:
        extract(client)
    error = caught.value
    assert type(error) is expected
    assert str(error) == expected.message
    assert type(error.__cause__) is OCRError
    assert error.__context__ is None
    assert SENSITIVE not in "".join(traceback.format_exception(error))


def test_deadline_covers_upload_and_polling() -> None:
    config = replace(CONFIG, timeout_seconds=0.01)
    with pytest.raises(OCRUnavailableError):
        extract(FakeAnalysisClient(delay=10), config=config)


def test_open_requires_an_entra_token_credential() -> None:
    opener = unchecked(open_document_intelligence)

    async def open_with(credential: object) -> DocumentIntelligenceExtractor:
        async with opener(config=CONFIG, credential=credential) as extractor:
            return extractor

    with pytest.raises(OCRConfigurationError):
        asyncio.run(open_with(AzureKeyCredential("key")))
    extractor = asyncio.run(open_with(FakeCredential()))
    assert isinstance(extractor, DocumentIntelligenceExtractor)
