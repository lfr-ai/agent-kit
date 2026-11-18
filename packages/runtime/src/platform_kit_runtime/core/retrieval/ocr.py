"""Provider-neutral OCR/text-extraction contracts; stdlib only."""

from bisect import bisect_right
from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Protocol

from platform_kit_runtime.core.validation import (
    is_bounded_seconds,
    is_int_in_range,
    is_service_endpoint,
)

_DEFAULT_TIMEOUT_SECONDS = 300.0
_MAX_TIMEOUT_SECONDS = 3600.0
# Document Intelligence v4.0 accepts at most 500 MB per request on paid tiers.
_MAX_DOCUMENT_BYTES = 500_000_000


class OCRError(Exception):
    """Base text-extraction failure with a fixed, content-free message."""

    message = "Document text extraction failed."
    code = "ocr_failure"

    def __init__(self) -> None:
        """Construct an error without accepting document content or tokens."""
        super().__init__(self.message)


class OCRConfigurationError(OCRError):
    """Invalid local settings, or the service rejected model or endpoint settings."""

    message = "OCR configuration is invalid."
    code = "ocr_configuration"


class OCRDocumentError(OCRError):
    """The document is empty, too large, unsupported or unreadable."""

    message = "The document cannot be extracted."
    code = "ocr_document"


class OCRAuthenticationError(OCRError):
    """The service rejected the credential or its role assignment."""

    message = "OCR authentication failed."
    code = "ocr_authentication"


class OCRUnavailableError(OCRError):
    """The deadline elapsed, or the service is unreachable, throttled or failing."""

    message = "OCR service is unavailable."
    code = "ocr_unavailable"


class OCRProtocolError(OCRError):
    """The SDK failed unexpectedly or returned a malformed analysis result."""

    message = "OCR service returned an invalid result."
    code = "ocr_protocol"


class OCRDependencyError(OCRError):
    """The optional OCR SDK is missing or incompatible."""

    message = "The optional OCR dependency is unavailable."
    code = "ocr_dependency"


@unique
class OCRModel(StrEnum):
    """Supported prebuilt extraction models."""

    LAYOUT = "prebuilt-layout"
    READ = "prebuilt-read"


@dataclass(frozen=True, kw_only=True, slots=True)
class OCRConfig:
    """Document Intelligence settings; authentication is Microsoft Entra only.

    Attributes:
        endpoint (str): HTTPS resource endpoint, such as
            ``https://<resource>.cognitiveservices.azure.com``.
        model (OCRModel): ``prebuilt-layout`` returns markdown with headings and
            tables; ``prebuilt-read`` returns plain text lines.
        timeout_seconds (float): Deadline for upload and polling, at most one hour.
        max_document_bytes (int): Local upload cap, at most the 500 MB service
            limit; set 4 MB for the free tier.
    """

    endpoint: str
    model: OCRModel = OCRModel.LAYOUT
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_document_bytes: int = _MAX_DOCUMENT_BYTES

    def __post_init__(self) -> None:
        """Validate settings before SDK import or network access.

        Raises:
            OCRConfigurationError: A supplied value is invalid.
        """
        bounded_size = is_int_in_range(
            self.max_document_bytes, low=1, high=_MAX_DOCUMENT_BYTES
        )
        bounded_timeout = is_bounded_seconds(
            self.timeout_seconds, maximum=_MAX_TIMEOUT_SECONDS
        )
        valid_model = isinstance(self.model, OCRModel)
        if not is_service_endpoint(self.endpoint) or not valid_model:
            raise OCRConfigurationError
        if not bounded_size or not bounded_timeout:
            raise OCRConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class ExtractedPage:
    """Where one page starts and ends in the extracted content.

    Attributes:
        number (int): One-based page number.
        start (int): Offset of the page's first character in the content.
        end (int): Exclusive offset after the page's last character.
    """

    number: int
    start: int
    end: int


@dataclass(frozen=True, kw_only=True, slots=True)
class ExtractedText:
    """Extracted document text with page boundaries.

    Attributes:
        content (str): Markdown or plain text, omitted from repr.
        pages (tuple[ExtractedPage, ...]): Pages ordered by start offset; empty
            when the source has no page structure.
    """

    content: str = field(repr=False)
    pages: tuple[ExtractedPage, ...] = ()

    def page_at(self, offset: int) -> int | None:
        """Return the last page starting at or before ``offset``, if any."""
        index = bisect_right([page.start for page in self.pages], offset) - 1
        return self.pages[index].number if index >= 0 else None


class TextExtractor(Protocol):
    """Async OCR/text-extraction port."""

    async def extract(self, *, data: bytes) -> ExtractedText:
        """Return the text and page offsets extracted from one document's bytes.

        Implementations raise ``OCRDocumentError``, ``OCRConfigurationError``,
        ``OCRAuthenticationError``, ``OCRUnavailableError`` or
        ``OCRProtocolError``; caller cancellation propagates unchanged.
        """
        ...
