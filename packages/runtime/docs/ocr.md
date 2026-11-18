# OCR

Opt-in text extraction with Azure AI Document Intelligence (API `2024-11-30`,
v4.0). The output feeds the [retrieval](retrieval.md) chunker, but
`TextExtractor` is a plain port and works on its own. There are no custom
models, classifiers, batch analysis, field extraction or HTTP routes.

## Dependency and import boundary

The `ocr` extra installs `azure-ai-documentintelligence`, `azure-identity` and
`aiohttp`, the transport the asynchronous client needs. Importing
`platform_kit_runtime.documents` loads no SDK; `open_document_intelligence`
raises `OCRDependencyError` when the extra is missing.

## Extract text

```python
import os

from azure.identity.aio import ManagedIdentityCredential

from platform_kit_runtime.documents import (
    ExtractedText,
    OCRConfig,
    OCRModel,
    open_document_intelligence,
)


async def extract(data: bytes) -> ExtractedText:
    config = OCRConfig(
        endpoint=os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"],
        model=OCRModel.LAYOUT,
        timeout_seconds=120.0,
    )
    async with (
        ManagedIdentityCredential() as credential,
        open_document_intelligence(config=config, credential=credential) as extractor,
    ):
        return await extractor.extract(data=data)
```

`ExtractedText.content` is the full document text. `pages` holds each page's
number and character range, and `page_at(offset)` returns the page that
contains an offset, or `None`. Offsets are Unicode code points, so they index
Python strings directly.

## Models

| `OCRModel` | Service model | Output |
| --- | --- | --- |
| `LAYOUT` (default) | `prebuilt-layout` | Markdown with headings, tables and figures |
| `READ` | `prebuilt-read` | Plain text lines |

Use `LAYOUT` for retrieval because headings become citation sections. Use
`READ` for scans where layout does not matter. Supported inputs include PDF,
JPEG, PNG, BMP, TIFF, HEIF and Office files; see the service documentation for
model-specific formats.

## Limits and deadlines

| Setting | Default | Notes |
| --- | --- | --- |
| `max_document_bytes` | 500 MB | Checked before upload. Set 4 MB on the free (F0) tier. |
| `timeout_seconds` | 300 | Covers upload and polling. At most one hour. |

The service analyzes up to 2,000 pages per document on paid tiers and only the
first two pages on the free tier. Empty or oversized input raises
`OCRDocumentError` without a network call. When the deadline expires, the
adapter stops waiting and raises `OCRUnavailableError`. The service operation
can still finish remotely. Caller cancellation propagates as
`asyncio.CancelledError`.

## Failures

All failures are `OCRError` subclasses with fixed messages and a `code`:

- `OCRConfigurationError`: invalid settings, a key credential, or a rejected
  model or endpoint.
- `OCRDocumentError`: empty, oversized, corrupt or unsupported input.
- `OCRAuthenticationError`: the token or role assignment was rejected.
- `OCRUnavailableError`: deadline, throttling, network or service failure.
- `OCRProtocolError`: a malformed result or unexpected SDK failure.
- `OCRDependencyError`: the `ocr` extra is missing or incompatible.

Errors never include document content, endpoints or tokens. The SDK exception
is not chained.

## Authentication and roles

Only Microsoft Entra token credentials are accepted. The resource must use a
custom subdomain endpoint such as
`https://<resource>.cognitiveservices.azure.com`. Assign **Cognitive Services
User** on the Document Intelligence (or Foundry) resource to the managed
identity. Use `ManagedIdentityCredential` in production. Locally, use
`DefaultAzureCredential` with `AZURE_TOKEN_CREDENTIALS=dev`. The caller owns
and closes the credential.
