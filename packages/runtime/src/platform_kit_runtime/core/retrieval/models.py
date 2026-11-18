"""Immutable retrieval records, fail-closed access scopes and settings; stdlib only."""

from dataclasses import dataclass, field
import hashlib
import re
from typing import Self

from platform_kit_runtime.core.limits import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MAX_REQUEST_TIMEOUT_SECONDS,
    MAX_SDK_RETRIES,
)
from platform_kit_runtime.core.validation import (
    is_bounded_seconds,
    is_int_in_range,
    is_nonblank,
    is_openai_v1_deployment,
    is_service_endpoint,
)

_DEFAULT_MAX_CHARACTERS = 1200
_DEFAULT_OVERLAP_CHARACTERS = 150
_MAX_CHUNK_CHARACTERS = 100_000
_DEFAULT_TOP_K = 5
_MAX_TOP_K = 50
_KEY_SEPARATOR = "\x1f"
_INDEX_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,126}[a-z0-9]")


class RetrievalError(Exception):
    """Base retrieval failure with a fixed, content-free message."""

    message = "Retrieval failed."
    code = "retrieval_failure"

    def __init__(self) -> None:
        """Construct an error without accepting document, query or token values."""
        super().__init__(self.message)


class RetrievalConfigurationError(RetrievalError):
    """Invalid local settings/input, or the provider rejected the configuration."""

    message = "Retrieval configuration is invalid."
    code = "retrieval_configuration"


class RetrievalAuthenticationError(RetrievalError):
    """The provider rejected the credential or its role assignment."""

    message = "Retrieval authentication failed."
    code = "retrieval_authentication"


class RetrievalUnavailableError(RetrievalError):
    """The deadline elapsed, or the provider is unreachable, throttled or failing."""

    message = "Retrieval provider is unavailable."
    code = "retrieval_unavailable"


class RetrievalProtocolError(RetrievalError):
    """The SDK failed unexpectedly or returned a malformed response."""

    message = "Retrieval provider returned an invalid response."
    code = "retrieval_protocol"


class RetrievalDependencyError(RetrievalError):
    """The optional retrieval SDK is missing or incompatible."""

    message = "The optional retrieval dependency is unavailable."
    code = "retrieval_dependency"


def chunk_key(*, document_id: str, ordinal: int) -> str:
    """Return a stable, index-safe key for one chunk of one document.

    Args:
        document_id (str): Caller-owned document identifier.
        ordinal (int): Zero-based chunk position within the document.

    Returns:
        str: Lowercase SHA-256 hex digest, safe for any key alphabet.
    """
    material = f"{document_id}{_KEY_SEPARATOR}{ordinal}".encode()
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, kw_only=True, slots=True)
class AccessScope:
    """Readers allowed to see content; an empty, unscoped value cannot exist.

    Attributes:
        groups (frozenset[str]): Nonblank group identifiers; empty only when public.
        public (bool): Explicit opt-in for content readable by every caller.
    """

    groups: frozenset[str] = field(default=frozenset(), repr=False)
    public: bool = False

    def __post_init__(self) -> None:
        """Fail closed on empty, mixed or malformed scopes.

        Raises:
            RetrievalConfigurationError: The scope is neither groups nor public.
        """
        valid_groups = isinstance(self.groups, frozenset) and all(
            is_nonblank(group) for group in self.groups
        )
        # Exactly one of explicit groups or the explicit public flag is required.
        explicit = type(self.public) is bool and self.public != bool(self.groups)
        if not valid_groups or not explicit:
            raise RetrievalConfigurationError

    def allows(self, *, access: Self) -> bool:
        """Return whether this reader may see content stored with ``access``."""
        return access.public or not self.groups.isdisjoint(access.groups)


@dataclass(frozen=True, kw_only=True, slots=True)
class ChunkingConfig:
    """Character budget for markdown-aware chunks.

    Attributes:
        max_characters (int): Upper bound per chunk, from one to 100,000.
        overlap_characters (int): Context repeated after a size split; below
            ``max_characters`` and never carried across a heading.
    """

    max_characters: int = _DEFAULT_MAX_CHARACTERS
    overlap_characters: int = _DEFAULT_OVERLAP_CHARACTERS

    def __post_init__(self) -> None:
        """Reject non-integer, out-of-range or overlapping budgets.

        Raises:
            RetrievalConfigurationError: A budget is invalid.
        """
        integers = (
            type(self.max_characters) is int and type(self.overlap_characters) is int
        )
        if not integers or not (
            0 < self.max_characters <= _MAX_CHUNK_CHARACTERS
            and 0 <= self.overlap_characters < self.max_characters
        ):
            raise RetrievalConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class TextChunk:
    """One chunk of extracted text with its source offsets.

    Attributes:
        text (str): Nonblank chunk text, omitted from repr.
        start (int): Offset of the first character in the source text.
        end (int): Exclusive offset after the last character in the source text.
        section (str | None): Heading path such as ``Guide > Setup``, if any.
    """

    text: str = field(repr=False)
    start: int
    end: int
    section: str | None = field(default=None, repr=False)


@dataclass(frozen=True, kw_only=True, slots=True)
class Citation:
    """Provenance needed to cite a passage.

    Attributes:
        document_id (str): Caller-owned document identifier.
        title (str): Human-readable document title, omitted from repr.
        source (str | None): Optional link or path to the original, omitted from repr.
        page (int | None): One-based page where the passage starts, when known.
        section (str | None): Heading path of the passage, omitted from repr.
    """

    document_id: str
    title: str = field(repr=False)
    source: str | None = field(default=None, repr=False)
    page: int | None = None
    section: str | None = field(default=None, repr=False)


@dataclass(frozen=True, kw_only=True, slots=True)
class Passage:
    """A retrieved passage with its citation and provider relevance score.

    Attributes:
        text (str): Passage text, omitted from repr.
        citation (Citation): Where the passage came from.
        score (float): Provider score; semantic reranker score when available.
    """

    text: str = field(repr=False)
    citation: Citation
    score: float


@dataclass(frozen=True, kw_only=True, slots=True)
class SearchQuery:
    """A search request that always carries the reader's access scope.

    Attributes:
        text (str): Nonblank query text, omitted from repr.
        scope (AccessScope): Required reader scope; results are trimmed to it.
        top_k (int): Number of passages to return, from one to 50.
    """

    text: str = field(repr=False)
    scope: AccessScope
    top_k: int = _DEFAULT_TOP_K

    def __post_init__(self) -> None:
        """Reject blank text, a missing scope or an unbounded result count.

        Raises:
            RetrievalConfigurationError: A field is invalid.
        """
        bounded = is_int_in_range(self.top_k, low=1, high=_MAX_TOP_K)
        if not is_nonblank(self.text) or not isinstance(self.scope, AccessScope):
            raise RetrievalConfigurationError
        if not bounded:
            raise RetrievalConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class SourceDocument:
    """A document to ingest, replacing any earlier version with the same ID.

    Attributes:
        document_id (str): Nonblank caller-owned identifier; the idempotency key.
        title (str): Nonblank title used in citations, omitted from repr.
        data (bytes): Nonempty original file bytes, omitted from repr.
        access (AccessScope): Readers allowed to retrieve the document.
        source (str | None): Optional link or path used in citations.
    """

    document_id: str
    title: str = field(repr=False)
    data: bytes = field(repr=False)
    access: AccessScope
    source: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate identifiers and types without copying content into errors.

        Raises:
            RetrievalConfigurationError: A field is blank or has the wrong type.
        """
        named = is_nonblank(self.document_id) and is_nonblank(self.title)
        typed = isinstance(self.data, bytes) and isinstance(self.access, AccessScope)
        if not named or not typed or not self.data:
            raise RetrievalConfigurationError
        if self.source is not None and not is_nonblank(self.source):
            raise RetrievalConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class IndexedChunk:
    """An embedded chunk ready for an index write.

    Attributes:
        citation (Citation): Provenance stored with the chunk.
        ordinal (int): Zero-based position of the chunk in its document.
        text (str): Chunk text, omitted from repr.
        vector (tuple[float, ...]): Embedding of ``text``, omitted from repr.
        access (AccessScope): Readers allowed to retrieve the chunk.
    """

    citation: Citation
    ordinal: int
    text: str = field(repr=False)
    vector: tuple[float, ...] = field(repr=False)
    access: AccessScope

    @property
    def key(self) -> str:
        """Stable index key derived from the document ID and ordinal."""
        return chunk_key(document_id=self.citation.document_id, ordinal=self.ordinal)


@dataclass(frozen=True, kw_only=True, slots=True)
class IngestionResult:
    """Outcome of one idempotent ingestion.

    Attributes:
        document_id (str): The replaced document.
        chunks (int): Number of chunks now indexed for the document.
    """

    document_id: str
    chunks: int


@dataclass(frozen=True, kw_only=True, slots=True)
class EmbeddingConfig:
    """Explicit LiteLLM embedding settings; no environment discovery by the runtime.

    Attributes:
        model (str): LiteLLM model selector: ``openai/<deployment>`` with
            Microsoft Entra, or for example ``azure/<deployment>`` with a key.
        api_key (str | None): Caller-resolved API key, never included in repr or
            errors. Required without ``entra_authentication``; must be absent
            with it.
        api_base (str | None): Optional HTTPS endpoint; required with Microsoft
            Entra, where its path must be exactly ``/openai/v1/``.
        api_version (str | None): Optional provider API version for key
            authentication, notably Azure; must be absent with Microsoft Entra.
        dimensions (int | None): Optional positive output size for models that
            support shortening; must match the index vector field.
        timeout_seconds (float): Positive finite deadline per SDK call, at most
            300 seconds, including token acquisition and SDK retries.
        num_retries (int): SDK retry cap from zero to three; defaults to zero.
        entra_authentication (bool): Require a caller-owned async token provider
            at composition, an ``openai/<deployment>`` model and an HTTPS
            ``/openai/v1/`` base. No API version or key is accepted. Defaults to
            ``False``.
    """

    model: str = field(repr=False)
    api_key: str | None = field(default=None, repr=False)
    api_base: str | None = field(default=None, repr=False)
    api_version: str | None = field(default=None, repr=False)
    dimensions: int | None = None
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    num_retries: int = 0
    entra_authentication: bool = False

    def __post_init__(self) -> None:
        """Validate settings before optional SDK import or network access.

        Raises:
            RetrievalConfigurationError: A supplied value is invalid, or the
                authentication settings do not match the selected mode.
        """
        if not is_nonblank(self.model):
            raise RetrievalConfigurationError
        if self.api_base is not None and not is_service_endpoint(self.api_base):
            raise RetrievalConfigurationError
        if self.api_version is not None and not is_nonblank(self.api_version):
            raise RetrievalConfigurationError
        valid_dimensions = self.dimensions is None or (
            type(self.dimensions) is int and self.dimensions > 0
        )
        bounded_retries = is_int_in_range(self.num_retries, low=0, high=MAX_SDK_RETRIES)
        bounded_timeout = is_bounded_seconds(
            self.timeout_seconds, maximum=MAX_REQUEST_TIMEOUT_SECONDS
        )
        if not valid_dimensions or not bounded_retries or not bounded_timeout:
            raise RetrievalConfigurationError
        self._validate_authentication()

    def _validate_authentication(self) -> None:
        if not isinstance(self.entra_authentication, bool):
            raise RetrievalConfigurationError
        if not self.entra_authentication:
            if not is_nonblank(self.api_key):
                raise RetrievalConfigurationError
            return
        keyless = self.api_key is None and self.api_version is None
        v1_deployment = is_openai_v1_deployment(
            model=self.model, api_base=self.api_base
        )
        if not keyless or not v1_deployment:
            raise RetrievalConfigurationError


@dataclass(frozen=True, kw_only=True, slots=True)
class AzureSearchConfig:
    """Azure AI Search index settings; authentication is Microsoft Entra only.

    Attributes:
        endpoint (str): HTTPS service endpoint, such as
            ``https://<service>.search.windows.net``.
        index_name (str): Existing index name: 2-128 lowercase letters, digits
            or dashes, starting and ending with a letter or digit.
        semantic_configuration (str | None): Semantic configuration name; when
            set, queries use the semantic ranker over hybrid results.
    """

    endpoint: str
    index_name: str
    semantic_configuration: str | None = None

    def __post_init__(self) -> None:
        """Validate settings before SDK import or network access.

        Raises:
            RetrievalConfigurationError: A supplied value is invalid.
        """
        valid_name = isinstance(self.index_name, str) and bool(
            _INDEX_NAME.fullmatch(self.index_name)
        )
        if not is_service_endpoint(self.endpoint) or not valid_name:
            raise RetrievalConfigurationError
        if self.semantic_configuration is not None and not is_nonblank(
            self.semantic_configuration
        ):
            raise RetrievalConfigurationError
