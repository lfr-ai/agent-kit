# Retrieval

Opt-in ingestion and cited, security-trimmed retrieval over Azure AI Search.
Text extraction is in [OCR](ocr.md); embeddings reuse LiteLLM as in
[async text inference](ai.md). There are no HTTP routes, answer generation,
agents, indexers, skillsets or deployment resources.

## Dependency and import boundary

- `retrieval` extra: `azure-search-documents` and `azure-identity`.
- `ai` extra: LiteLLM, for `create_litellm_embedder`.
- `ocr` extra: Document Intelligence, for ingestion from binary documents.

The Azure clients are asynchronous and need the `aiohttp` transport, which the
`retrieval` and `ocr` extras install.

Importing `platform_kit_runtime.retrieval` loads no SDK. The records, ports,
chunker, metrics and services are standard-library only. `open_azure_search`
and `azure_search_index_definition` raise `RetrievalDependencyError` without
the `retrieval` extra; `create_litellm_embedder` raises it without the `ai`
extra.

## Ingest and retrieve

```python
import os

from azure.identity.aio import ManagedIdentityCredential, get_bearer_token_provider

from platform_kit_runtime.documents import OCRConfig, open_document_intelligence
from platform_kit_runtime.retrieval import (
    AccessScope,
    AzureSearchConfig,
    EmbeddingConfig,
    IngestionService,
    Passage,
    RetrievalService,
    SearchQuery,
    SourceDocument,
    create_litellm_embedder,
    open_azure_search,
)

READERS = AccessScope(groups=frozenset({os.environ["READER_GROUP_ID"]}))
# Keyless Microsoft Entra: an openai/<deployment> selector on a /openai/v1/ base.
EMBEDDINGS = EmbeddingConfig(
    entra_authentication=True,
    model="openai/<embedding-deployment>",
    api_base="https://<resource>.openai.azure.com/openai/v1/",
)


async def ingest_and_search(data: bytes, question: str) -> tuple[Passage, ...]:
    search = AzureSearchConfig(
        endpoint=os.environ["SEARCH_ENDPOINT"],
        index_name="chunks",
        semantic_configuration="default",
    )
    ocr = OCRConfig(endpoint=os.environ["DOCUMENT_INTELLIGENCE_ENDPOINT"])
    async with (
        ManagedIdentityCredential() as credential,
        open_azure_search(config=search, credential=credential) as index,
        open_document_intelligence(config=ocr, credential=credential) as extractor,
    ):
        embedder = create_litellm_embedder(
            config=EMBEDDINGS,
            token_provider=get_bearer_token_provider(
                credential, "https://ai.azure.com/.default"
            ),
        )
        ingestion = IngestionService(
            extractor=extractor, embedder=embedder, index=index
        )
        await ingestion.ingest(
            document=SourceDocument(
                document_id="policy-42",
                title="Travel policy",
                source="https://intranet.example/policies/travel.pdf",
                data=data,
                access=READERS,
            )
        )
        retrieval = RetrievalService(embedder=embedder, retriever=index)
        return await retrieval.retrieve(
            query=SearchQuery(text=question, scope=READERS, top_k=5)
        )
```

Each `Passage` has `text`, a service `score` and a `Citation` with
`document_id`, `title`, `source`, `page` and `section` (the markdown heading
path, for example `Travel > Meals`). Page numbers come from OCR page spans.

Construct embedders and services once and reuse them. Both services accept any
implementation of their Protocol ports (`TextExtractor`, `Embedder`,
`DocumentIndex`, `Retriever`), so other stores or extractors need no changes
to the use cases.

## Embedding authentication

Microsoft Entra is the recommended mode and keeps embeddings working when the
Azure OpenAI or Foundry resource sets `disableLocalAuth=true`. With
`entra_authentication=True`, `EmbeddingConfig` requires
`model="openai/<deployment>"` and an HTTPS `api_base` whose path is exactly
`/openai/v1/` (`https://<resource>.openai.azure.com/openai/v1/` or
`https://<resource>.services.ai.azure.com/openai/v1/`), and rejects `api_key`
and `api_version`. `create_litellm_embedder` requires a callable
`token_provider` exactly when the flag is set; otherwise it raises
`RetrievalConfigurationError` before loading the SDK.

The adapter awaits the provider once per batch of up to 64 texts, within that
call's deadline, and LiteLLM sends the token as `Authorization: Bearer`, never
as an `api-key` header; SDK retries reuse it. Token acquisition failures and
blank or non-printable tokens raise `RetrievalAuthenticationError`, token
timeouts raise `RetrievalUnavailableError`, and cancellation propagates.
Neither tokens nor provider messages appear in errors or logs.

Key authentication remains available where the provider allows it: pass an
explicit `api_key`, for example with `model="azure/<deployment>"`,
`api_base="https://<resource>.openai.azure.com"` and `api_version`, and no
token provider. An omitted or blank key raises `RetrievalConfigurationError`;
the runtime never falls back to ambient credentials.

## Access scopes fail closed

`AccessScope` requires exactly one of a nonempty set of group IDs or the
explicit `public=True` flag; `AccessScope()` raises
`RetrievalConfigurationError`. A document's scope is stored with each chunk.
Every query carries the reader's scope and the adapter always sends a filter:

- groups: `access_groups/any(g: search.in(g, '<id>|<id>', '|'))` or public
  content;
- public: `access_public eq true` only.

Group IDs are opaque strings such as Microsoft Entra group object IDs and must
not contain `|`. Resolve them from the authenticated caller, never from request
input. This is query-time trimming in the application, not Azure AI Search
document-level access control.

## Index schema

`azure_search_index_definition(config=..., dimensions=...)` returns the REST JSON
definition expected by the adapter. It includes a key field, a filterable
`document_id`, searchable `title`, `section` and `content`, hidden filterable
`access_groups` and `access_public` fields, citation fields and an HNSW
`content_vector` field. When
`semantic_configuration` is set, it adds a semantic configuration that ranks
`content` with `title` as the title field. Create it once from deployment code:

```python
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex

definition = azure_search_index_definition(config=search, dimensions=1536)
async with SearchIndexClient(search.endpoint, credential) as client:
    await client.create_or_update_index(SearchIndex(definition))
```

`dimensions` must equal the embedding size, including any
`EmbeddingConfig.dimensions` override.

## Behavior

- Queries are hybrid: full-text plus one vector query, fused by the service.
  With `semantic_configuration` the semantic ranker re-ranks up to 50 hybrid
  candidates; the service must have the semantic ranker enabled.
- Ingestion extracts, chunks and embeds before changing the index. It then
  deletes the document's chunks and uploads the new ones, so re-ingesting the
  same `document_id` replaces content. Chunk keys are SHA-256 digests of the
  document ID and chunk ordinal.
- `chunk_markdown` keeps heading sections and fenced code together where they
  fit and splits larger blocks at line, sentence, then word boundaries. Size
  splits repeat up to `overlap_characters` (default 150) of context; the
  default budget is 1,200 characters. The output is deterministic.
- Uploads and deletes are sent in batches of 1,000; embeddings in batches of 64.
- Azure AI Search is near-real-time: a delete issued moments after an upload
  can miss chunks that are not yet searchable. Avoid concurrent ingestion of
  the same document ID.

## Deadlines and failures

`IngestionService` has a total deadline of 900 seconds by default (at most one
hour); `RetrievalService` has 30 seconds (at most 300). Expiry cancels the work
and raises `RetrievalUnavailableError`. Caller cancellation propagates as
`asyncio.CancelledError` and is not logged.

Failures are `RetrievalError` subclasses with fixed messages and a `code`:
configuration, authentication, unavailable, protocol and dependency. Messages
never contain document text, queries, group IDs, endpoints or tokens, and the
SDK exception is not chained. Each service logs a handled failure once with
the `retrieval_failure` code; OCR failures pass through as `OCRError`.

## Evaluation

```python
from platform_kit_runtime.retrieval import LabelledQuery, evaluate_retrieval

metrics = evaluate_retrieval(
    dataset=[LabelledQuery(query_id="q1", relevant_ids=frozenset({"policy-42"}))],
    results={"q1": ["policy-7", "policy-42"]},
    k=5,
)
assert metrics.recall_at_k == 1.0
assert metrics.mrr == 0.5
```

`recall_at_k`, `reciprocal_rank` and `evaluate_retrieval` are pure functions.
Use document or chunk IDs consistently, for example
`passage.citation.document_id`.

## Authentication and roles

Azure AI Search accepts only Microsoft Entra token credentials; key credentials
raise `RetrievalConfigurationError`. Enable role-based access on the search
service. Embeddings use Microsoft Entra through a token provider over the same
credential, as above, or an API key where the provider allows it.
Use `ManagedIdentityCredential` in production. For local development use
`DefaultAzureCredential` with `AZURE_TOKEN_CREDENTIALS=dev`. The caller owns and
closes the credential.

| Task | Role (search service or index scope) |
| --- | --- |
| Query | Search Index Data Reader |
| Ingest and delete | Search Index Data Contributor |
| Create or update the index | Search Service Contributor |
| Embeddings | Cognitive Services OpenAI User on the Azure OpenAI or Foundry resource; or a provider API key in `EmbeddingConfig` |
| OCR during ingestion | Cognitive Services User, see [OCR](ocr.md) |
