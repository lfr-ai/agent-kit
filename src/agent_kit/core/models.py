"""Immutable contracts shared across Agent Kit layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """A safe, source-relative validation diagnostic."""

    code: str
    message: str
    path: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ProfileSummary:
    """Effective capability counts and limits for one profile."""

    body_lines: int
    description_chars: int
    limits: tuple[tuple[str, int], ...]
    policy_lines: int
    profile: str
    skill_count: int


@dataclass(frozen=True, kw_only=True, slots=True)
class CheckReport:
    """Validation findings and effective profile summaries."""

    findings: tuple[Finding, ...]
    profiles: tuple[ProfileSummary, ...]
    version: str | None

    @property
    def valid(self) -> bool:
        """Whether the catalog has no validation findings."""
        return not self.findings


@dataclass(frozen=True, kw_only=True, slots=True)
class SourceDocument:
    """One source-tree file or symlink captured without following links."""

    content: bytes
    frontmatter: object | None
    frontmatter_error: bool
    is_directory: bool
    is_symlink: bool
    parse_error: bool
    relative_path: str
    text: str | None
    yaml_value: object | None


@dataclass(frozen=True, kw_only=True, slots=True)
class BundleSource:
    """Captured manifest and portable resources for one catalog bundle."""

    apm_exists: bool
    files: tuple[SourceDocument, ...]
    kind: str
    manifest: object | None
    manifest_document: SourceDocument
    manifest_error: bool
    manifest_is_symlink: bool
    name: str
    path: str
    root_is_symlink: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class CatalogSnapshot:
    """Read-only source data supplied by the catalog infrastructure port."""

    bundles: tuple[BundleSource, ...]
    catalog: object | None
    catalog_document: SourceDocument | None
    catalog_error: bool
    policy: object | None
    policy_document: SourceDocument | None
    policy_error: bool
    root: Path
    root_documents: tuple[SourceDocument, ...]
    root_paths: tuple[str, ...]
    root_symlinks: tuple[str, ...]
    root_is_symlink: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class Bundle:
    """Validated catalog bundle identity and contained source path."""

    kind: str
    name: str
    path: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Profile:
    """Validated profile inheritance and directly selected bundles."""

    bundles: tuple[str, ...]
    extends: tuple[str, ...]
    name: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Catalog:
    """Validated catalog metadata used for selection and materialization."""

    budgets: tuple[tuple[str, int], ...]
    bundles: tuple[Bundle, ...]
    profiles: tuple[Profile, ...]
    schema_version: int
    supported_runtimes: tuple[str, ...]
    version: str


@dataclass(frozen=True, kw_only=True, slots=True)
class PlannedFile:
    """One relative file planned for a new composed output."""

    content: bytes
    relative_path: str


@dataclass(frozen=True, kw_only=True, slots=True)
class CompositionPlan:
    """Pure, deterministic bytes for a selected profile composition."""

    bundles: tuple[str, ...]
    files: tuple[PlannedFile, ...]
    profile: str
    root: Path
    runtimes: tuple[str, ...]
    source_paths: tuple[tuple[str, str], ...]
    version: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ComposedSnapshot:
    """Read-only files captured from an already composed workspace."""

    files: tuple[SourceDocument, ...]
    provenance: object | None
    provenance_error: bool
    provenance_is_symlink: bool
    root: Path
    root_is_symlink: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class SessionContext:
    """Bounded context-entry health report for a session-start hook."""

    workspace: str
    missing: tuple[str, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class Selection:
    """A declared composition: one profile plus opt-in features and targets."""

    profile: str
    features: tuple[str, ...]
    runtimes: tuple[str, ...]
    skills: tuple[str, ...]
