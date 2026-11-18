from dataclasses import replace
from typing import Final

import pytest

from platform_kit_runtime.core.retrieval.models import chunk_key
from platform_kit_runtime.retrieval import (
    AccessScope,
    AzureSearchConfig,
    ChunkingConfig,
    Citation,
    EmbeddingConfig,
    IndexedChunk,
    RetrievalConfigurationError,
    RetrievalError,
    SearchQuery,
    SourceDocument,
)

pytestmark = pytest.mark.unit

SENSITIVE: Final[str] = "private-embedding-key"
ENDPOINT: Final[str] = "https://search.example.net"


def groups(*names: str) -> AccessScope:
    return AccessScope(groups=frozenset(names))


@pytest.mark.parametrize(
    "fields",
    [
        {"groups": frozenset()},
        {"public": True},
        {"groups": frozenset({" "})},
        {"groups": frozenset({"bad\nname"})},
        {"groups": {"readers"}},
        {"groups": frozenset({7})},
        {"groups": frozenset(), "public": 1},
    ],
)
def test_access_scope_fails_closed(fields: dict[str, object]) -> None:
    with pytest.raises(RetrievalConfigurationError, match="configuration is invalid"):
        replace(groups("readers"), **fields)


def test_unscoped_access_is_impossible() -> None:
    with pytest.raises(RetrievalConfigurationError):
        AccessScope()


def test_access_scope_trims_by_group_and_explicit_public() -> None:
    public = AccessScope(public=True)
    reader = groups("finance", "legal")
    assert reader.allows(access=public)
    assert reader.allows(access=groups("legal"))
    assert not reader.allows(access=groups("hr"))
    assert public.allows(access=public)
    assert not public.allows(access=groups("legal"))
    assert "legal" not in repr(reader)


@pytest.mark.parametrize(
    "fields",
    [
        {"text": " "},
        {"text": 1},
        {"scope": None},
        {"top_k": 0},
        {"top_k": 51},
        {"top_k": True},
    ],
)
def test_search_query_requires_scope_and_bounds(fields: dict[str, object]) -> None:
    query = SearchQuery(text="refund policy", scope=groups("readers"))
    assert query.top_k == 5
    with pytest.raises(RetrievalConfigurationError):
        replace(query, **fields)
    assert "refund" not in repr(query)


@pytest.mark.parametrize(
    "fields",
    [
        {"document_id": ""},
        {"title": " "},
        {"data": b""},
        {"data": "text"},
        {"access": None},
        {"source": ""},
    ],
)
def test_source_document_validation(fields: dict[str, object]) -> None:
    document = SourceDocument(
        document_id="doc-1",
        title="Handbook",
        data=b"%PDF",
        access=AccessScope(public=True),
        source="https://files.example/handbook.pdf",
    )
    with pytest.raises(RetrievalConfigurationError):
        replace(document, **fields)
    assert "PDF" not in repr(document)


@pytest.mark.parametrize(
    "fields",
    [
        {"max_characters": 0},
        {"max_characters": 100_001},
        {"max_characters": 10.0},
        {"overlap_characters": -1},
        {"overlap_characters": 1200},
        {"overlap_characters": None},
    ],
)
def test_chunking_config_bounds(fields: dict[str, object]) -> None:
    with pytest.raises(RetrievalConfigurationError):
        replace(ChunkingConfig(), **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"model": ""},
        {"api_key": " "},
        {"api_base": "http://insecure.example"},
        {"api_version": ""},
        {"dimensions": 0},
        {"dimensions": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": 301},
        {"timeout_seconds": float("nan")},
        {"num_retries": 4},
        {"num_retries": False},
    ],
)
def test_embedding_config_validation_hides_secrets(fields: dict[str, object]) -> None:
    config = EmbeddingConfig(
        model="azure/embedding",
        api_key=SENSITIVE,
        api_base="https://models.example.net",
        api_version="2024-10-21",
        dimensions=3,
    )
    assert SENSITIVE not in repr(config)
    with pytest.raises(RetrievalConfigurationError) as caught:
        replace(config, **fields)
    assert SENSITIVE not in str(caught.value)


def entra_embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        model="openai/embedding-deployment",
        api_base="https://resource.openai.azure.com/openai/v1/",
        entra_authentication=True,
    )


def test_entra_embedding_config_is_keyless() -> None:
    config = entra_embedding_config()
    assert config.entra_authentication is True
    assert config.api_key is None
    assert config.api_version is None
    assert EmbeddingConfig(model="azure/embedding", api_key=SENSITIVE).api_key


@pytest.mark.parametrize(
    "fields",
    [
        {"api_key": SENSITIVE},
        {"api_key": ""},
        {"entra_authentication": "true"},
        {"entra_authentication": 1},
        {"entra_authentication": False},
        {"model": "azure/embedding-deployment"},
        {"model": "openai/"},
        {"model": "openai/ "},
        {"api_base": None},
        {"api_base": "https://resource.openai.azure.com"},
        {"api_base": "https://resource.openai.azure.com/openai/v1"},
        {"api_base": "http://localhost/openai/v1/"},
        {"api_version": "2024-10-21"},
    ],
)
def test_entra_embedding_config_requires_keyless_openai_v1(
    fields: dict[str, object],
) -> None:
    with pytest.raises(RetrievalConfigurationError) as caught:
        replace(entra_embedding_config(), **fields)
    assert SENSITIVE not in str(caught.value)


def test_omitted_embedding_key_never_enables_ambient_authentication() -> None:
    with pytest.raises(RetrievalConfigurationError):
        EmbeddingConfig(model="azure/embedding")
    with pytest.raises(RetrievalConfigurationError):
        EmbeddingConfig(model="azure/embedding", api_key=None)


@pytest.mark.parametrize(
    "fields",
    [
        {"endpoint": "http://search.example.net"},
        {"endpoint": "https://user:pass@search.example.net"},
        {"index_name": "Chunks"},
        {"index_name": "-chunks"},
        {"index_name": "c"},
        {"index_name": 5},
        {"semantic_configuration": " "},
    ],
)
def test_azure_search_config_validation(fields: dict[str, object]) -> None:
    config = AzureSearchConfig(endpoint=ENDPOINT, index_name="chunks")
    with pytest.raises(RetrievalConfigurationError):
        replace(config, **fields)


def test_chunk_keys_are_stable_and_distinct() -> None:
    key = chunk_key(document_id="doc-1", ordinal=0)
    assert key == chunk_key(document_id="doc-1", ordinal=0)
    assert key != chunk_key(document_id="doc-1", ordinal=1)
    assert key != chunk_key(document_id="doc-10", ordinal=0)
    assert len(key) == 64
    assert key.isalnum()
    chunk = IndexedChunk(
        citation=Citation(document_id="doc-1", title="Handbook"),
        ordinal=0,
        text="body",
        vector=(1.0,),
        access=AccessScope(public=True),
    )
    assert chunk.key == key


def test_errors_have_fixed_messages_and_codes() -> None:
    error = RetrievalConfigurationError()
    assert isinstance(error, RetrievalError)
    assert str(error) == "Retrieval configuration is invalid."
    assert error.code == "retrieval_configuration"
