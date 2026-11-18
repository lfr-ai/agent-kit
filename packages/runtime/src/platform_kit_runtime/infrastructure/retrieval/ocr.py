"""Azure AI Document Intelligence text-extraction adapter (API 2024-11-30)."""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from io import BytesIO
from typing import IO, Protocol

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, DocumentPage
from azure.core.credentials_async import AsyncTokenCredential

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
from platform_kit_runtime.infrastructure.retrieval.azure_failures import (
    classify_azure_failure,
)
from platform_kit_runtime.infrastructure.retrieval.failures import FailureKind

# Offsets in Python strings are code points, so request matching span units.
_STRING_INDEX_TYPE = "unicodeCodePoint"
_MARKDOWN = "markdown"
_OCR_FAILURES = {
    FailureKind.AUTHENTICATION: OCRAuthenticationError,
    FailureKind.CONFIGURATION: OCRConfigurationError,
    FailureKind.CONTENT: OCRDocumentError,
    FailureKind.UNAVAILABLE: OCRUnavailableError,
    FailureKind.PROTOCOL: OCRProtocolError,
}


class DocumentAnalysisPoller(Protocol):
    """Long-running analysis operation returned by the SDK."""

    async def result(self) -> AnalyzeResult:
        """Poll until the analysis finishes and return its result."""
        ...


class DocumentAnalysisClient(Protocol):
    """Subset of the asynchronous ``DocumentIntelligenceClient`` used here."""

    async def begin_analyze_document(
        self,
        model_id: str,
        body: IO[bytes],
        *,
        string_index_type: str | None = None,
        output_content_format: str | None = None,
    ) -> DocumentAnalysisPoller:
        """Upload a document and start analysis."""
        ...


def _offset(value: object) -> int:
    if type(value) is not int or value < 0:
        raise OCRProtocolError
    return value


def _page(page: DocumentPage, *, length: int) -> ExtractedPage | None:
    spans = [(_offset(span.offset), _offset(span.length)) for span in page.spans or []]
    if not spans:
        return None
    start = min(offset for offset, _ in spans)
    end = max(offset + size for offset, size in spans)
    number = _offset(page.page_number)
    if number < 1 or end > length:
        raise OCRProtocolError
    return ExtractedPage(number=number, start=start, end=end)


def _extracted(result: AnalyzeResult) -> ExtractedText:
    content = result.content
    pages: Sequence[DocumentPage] = result.pages or []
    if not isinstance(content, str) or not isinstance(pages, list):
        raise OCRProtocolError
    mapped = [_page(page, length=len(content)) for page in pages]
    ordered = sorted(
        (page for page in mapped if page is not None), key=lambda page: page.start
    )
    return ExtractedText(content=content, pages=tuple(ordered))


class DocumentIntelligenceExtractor:
    """``TextExtractor`` using ``prebuilt-layout`` markdown or ``prebuilt-read`` text."""

    def __init__(self, *, client: DocumentAnalysisClient, config: OCRConfig) -> None:
        """Bind a caller-owned client to the extraction settings.

        Args:
            client (DocumentAnalysisClient): Open asynchronous analysis client.
            config (OCRConfig): Model, deadline and upload size settings.
        """
        self._client = client
        self._config = config

    async def _analyze(self, data: bytes) -> AnalyzeResult:
        markdown = _MARKDOWN if self._config.model is OCRModel.LAYOUT else None
        poller = await self._client.begin_analyze_document(
            self._config.model,
            BytesIO(data),
            string_index_type=_STRING_INDEX_TYPE,
            output_content_format=markdown,
        )
        return await poller.result()

    async def extract(self, *, data: bytes) -> ExtractedText:
        """Return Markdown or plain text with page boundaries for one document.

        Uploads ``data``, polls within the deadline and maps page offsets. Empty,
        oversized or rejected content raises ``OCRDocumentError``; other SDK
        failures raise the matching typed ``OCRError`` subclass.
        """
        if not isinstance(data, bytes) or not data:
            raise OCRDocumentError
        if len(data) > self._config.max_document_bytes:
            raise OCRDocumentError
        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                result = await self._analyze(data)
            extracted = _extracted(result)
        except Exception as error:  # noqa: BLE001 - SDK failures must not leak service diagnostics
            failure = _OCR_FAILURES[classify_azure_failure(error)]
        else:
            return extracted
        raise failure from OCRError()


@asynccontextmanager
async def open_document_intelligence(
    *, config: OCRConfig, credential: AsyncTokenCredential
) -> AsyncGenerator[DocumentIntelligenceExtractor]:
    """Own an asynchronous analysis client authenticated with Microsoft Entra ID.

    Args:
        config (OCRConfig): Endpoint, model, deadline and size settings.
        credential (AsyncTokenCredential): Caller-owned asynchronous token credential.

    Yields:
        DocumentIntelligenceExtractor: Adapter bound to the open client.

    Raises:
        OCRConfigurationError: The credential is not an async token credential.
    """
    if not isinstance(credential, AsyncTokenCredential):
        raise OCRConfigurationError
    async with DocumentIntelligenceClient(config.endpoint, credential) as client:
        yield DocumentIntelligenceExtractor(client=client, config=config)
