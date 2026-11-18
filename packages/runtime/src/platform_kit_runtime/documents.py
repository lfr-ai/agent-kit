"""Public opt-in OCR facade and composition root; import loads no SDKs."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Final

from platform_kit_runtime.core.retrieval.ocr import (
    ExtractedPage,
    ExtractedText,
    OCRAuthenticationError,
    OCRConfig,
    OCRConfigurationError,
    OCRDependencyError,
    OCRDocumentError,
    OCRError,
    OCRModel,
    OCRProtocolError,
    OCRUnavailableError,
    TextExtractor,
)

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential

__all__: Final[list[str]] = [
    "ExtractedPage",
    "ExtractedText",
    "OCRAuthenticationError",
    "OCRConfig",
    "OCRConfigurationError",
    "OCRDependencyError",
    "OCRDocumentError",
    "OCRError",
    "OCRModel",
    "OCRProtocolError",
    "OCRUnavailableError",
    "TextExtractor",
    "open_document_intelligence",
]


@asynccontextmanager
async def open_document_intelligence[CredentialT: AsyncTokenCredential](
    *, config: OCRConfig, credential: CredentialT
) -> AsyncGenerator[TextExtractor]:
    """Own an Azure AI Document Intelligence client; Entra ID tokens only.

    No request is sent until a document is extracted. Use a
    ``ManagedIdentityCredential`` in production; the caller keeps ownership of
    the credential.

    Args:
        config (OCRConfig): Endpoint, model, deadline and upload size settings.
        credential (CredentialT): Asynchronous Azure token credential; key
            credentials are rejected with ``OCRConfigurationError``.

    Yields:
        TextExtractor: Extractor returning markdown or text with page offsets.

    Raises:
        OCRDependencyError: The optional ``ocr`` extra is not installed.
    """
    try:
        from platform_kit_runtime.infrastructure.retrieval.ocr import (  # noqa: PLC0415 - SDK adapter is opt-in composition only
            open_document_intelligence as open_extractor,
        )
    except ImportError:
        failure = OCRDependencyError()
    else:
        async with open_extractor(config=config, credential=credential) as extractor:
            yield extractor
        return
    raise failure from OCRError()
