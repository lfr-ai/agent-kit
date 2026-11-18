"""Public opt-in retrieval facade and composition root; import loads no SDKs."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Final

from platform_kit_runtime.application.retrieval import (
    IngestionService,
    RetrievalService,
)
from platform_kit_runtime.core.ai import AsyncTokenProvider
from platform_kit_runtime.core.retrieval.chunking import chunk_markdown
from platform_kit_runtime.core.retrieval.evaluation import (
    LabelledQuery,
    RetrievalMetrics,
    evaluate_retrieval,
    recall_at_k,
    reciprocal_rank,
)
from platform_kit_runtime.core.retrieval.models import (
    AccessScope,
    AzureSearchConfig,
    ChunkingConfig,
    Citation,
    EmbeddingConfig,
    IndexedChunk,
    IngestionResult,
    Passage,
    RetrievalAuthenticationError,
    RetrievalConfigurationError,
    RetrievalDependencyError,
    RetrievalError,
    RetrievalProtocolError,
    RetrievalUnavailableError,
    SearchQuery,
    SourceDocument,
    TextChunk,
)
from platform_kit_runtime.core.retrieval.ports import (
    DocumentIndex,
    Embedder,
    HybridIndex,
    Retriever,
)

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential

__all__: Final[list[str]] = [
    "AccessScope",
    "AzureSearchConfig",
    "ChunkingConfig",
    "Citation",
    "DocumentIndex",
    "Embedder",
    "EmbeddingConfig",
    "HybridIndex",
    "IndexedChunk",
    "IngestionResult",
    "IngestionService",
    "LabelledQuery",
    "Passage",
    "RetrievalAuthenticationError",
    "RetrievalConfigurationError",
    "RetrievalDependencyError",
    "RetrievalError",
    "RetrievalMetrics",
    "RetrievalProtocolError",
    "RetrievalService",
    "RetrievalUnavailableError",
    "Retriever",
    "SearchQuery",
    "SourceDocument",
    "TextChunk",
    "azure_search_index_definition",
    "chunk_markdown",
    "create_litellm_embedder",
    "evaluate_retrieval",
    "open_azure_search",
    "recall_at_k",
    "reciprocal_rank",
]


def create_litellm_embedder(
    *, config: EmbeddingConfig, token_provider: AsyncTokenProvider | None = None
) -> Embedder:
    """Return a batched embedder with strict vector validation over LiteLLM.

    No SDK settings or callbacks are set globally. SDK loading can raise
    ``RetrievalDependencyError`` when the optional AI SDK is unavailable or
    incompatible. For keyless Microsoft Entra authentication, pass a provider
    such as ``azure.identity.aio``
    ``get_bearer_token_provider(credential, "https://ai.azure.com/.default")``.

    Args:
        config (EmbeddingConfig): Explicit provider and authentication settings.
        token_provider (AsyncTokenProvider | None): Required only with
            ``config.entra_authentication``. Called once per SDK call within
            that call's deadline; the caller owns credential renewal and
            cleanup.

    Returns:
        Embedder: Embedding port with typed, content-free errors.

    Raises:
        RetrievalConfigurationError: The authentication mode and token provider
            disagree, or the token provider is not callable. Raised before the
            SDK is loaded.
    """
    if config.entra_authentication != (token_provider is not None):
        raise RetrievalConfigurationError
    if token_provider is not None and not callable(token_provider):
        raise RetrievalConfigurationError
    from platform_kit_runtime.infrastructure.retrieval.embeddings import (  # noqa: PLC0415 - SDK adapter is opt-in composition only
        LiteLLMEmbedder,
        load_litellm_embeddings,
    )

    return LiteLLMEmbedder(
        config=config, sdk=load_litellm_embeddings(), token_provider=token_provider
    )


@asynccontextmanager
async def open_azure_search[CredentialT: AsyncTokenCredential](
    *, config: AzureSearchConfig, credential: CredentialT
) -> AsyncGenerator[HybridIndex]:
    """Own an Azure AI Search client for one index; Entra ID tokens only.

    No request is sent until the index is used. Use a ``ManagedIdentityCredential``
    in production; the caller keeps ownership of the credential.

    Args:
        config (AzureSearchConfig): Endpoint, index and semantic ranker settings.
        credential (CredentialT): Asynchronous Azure token credential; key
            credentials are rejected with ``RetrievalConfigurationError``.

    Yields:
        HybridIndex: Security-trimmed hybrid index for ingestion and search.

    Raises:
        RetrievalDependencyError: The optional ``retrieval`` extra is not installed.
    """
    try:
        from platform_kit_runtime.infrastructure.retrieval.azure_search import (  # noqa: PLC0415 - SDK adapter is opt-in composition only
            open_azure_search_index,
        )
    except ImportError:
        failure = RetrievalDependencyError()
    else:
        async with open_azure_search_index(
            config=config, credential=credential
        ) as index:
            yield index
        return
    raise failure from RetrievalError()


def azure_search_index_definition(
    *, config: AzureSearchConfig, dimensions: int
) -> dict[str, object]:
    """Return the REST JSON definition of a compatible Azure AI Search index.

    The definition has a key field, filterable document and access fields, an
    HNSW vector field and, when configured, a semantic configuration. Create it
    with ``SearchIndexClient.create_or_update_index(SearchIndex(definition))``,
    the REST API or infrastructure code.

    Args:
        config (AzureSearchConfig): Index name and optional semantic configuration.
        dimensions (int): Embedding size produced by the embedding model.

    Returns:
        dict[str, object]: Index definition using REST property names.

    Raises:
        RetrievalDependencyError: The optional ``retrieval`` extra is not installed.
    """
    try:
        from platform_kit_runtime.infrastructure.retrieval.azure_search import (  # noqa: PLC0415 - SDK adapter is opt-in composition only
            search_index_definition,
        )
    except ImportError:
        failure = RetrievalDependencyError()
    else:
        return search_index_definition(config=config, dimensions=dimensions)
    raise failure from RetrievalError()
