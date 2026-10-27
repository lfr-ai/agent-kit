"""Read-only YAML, JSON, and resource catalog adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, TypeGuard, override

import yaml
import yaml.constructor

from agent_kit.core.errors import DuplicateJsonFieldError
from agent_kit.core.models import (
    BundleSource,
    CatalogSnapshot,
    ComposedSnapshot,
    SourceDocument,
)
from agent_kit.core.ports.catalog import CatalogPort

if TYPE_CHECKING:
    from collections.abc import Iterator

    from yaml.error import Mark
    from yaml.nodes import MappingNode


_EXCLUDED_ROOT_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "build",
        "dist",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".import_linter_cache",
        ".hypothesis",
        ".tox",
        ".ty",
        "htmlcov",
        "apm_modules",
        "node_modules",
    }
)
_BYTECODE_DIRECTORIES = frozenset({"__pycache__"})
_BYTECODE_SUFFIXES = frozenset({".pyc", ".pyo"})


class _UnhashableYamlKeyError(yaml.constructor.ConstructorError):
    """A YAML mapping key is not hashable."""

    def __init__(self, *, context_mark: Mark | None, problem_mark: Mark | None) -> None:
        """Describe the invalid key at its parser location.

        Args:
            context_mark (Mark | None): Mapping start location, when available.
            problem_mark (Mark | None): Key start location, when available.
        """
        super().__init__(
            "while constructing a mapping",
            context_mark,
            "unhashable mapping key",
            problem_mark,
        )


class _DuplicateYamlKeyError(yaml.constructor.ConstructorError):
    """A YAML mapping repeats a key."""

    def __init__(self, *, context_mark: Mark | None, problem_mark: Mark | None) -> None:
        """Describe the repeated key at its parser location.

        Args:
            context_mark (Mark | None): Mapping start location, when available.
            problem_mark (Mark | None): Key start location, when available.
        """
        super().__init__(
            "while constructing a mapping",
            context_mark,
            "duplicate mapping key",
            problem_mark,
        )


def _string_mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow decoded mappings to string keys and object values."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_link(path: Path) -> bool:
    """Recognize filesystem symlinks and Windows junctions."""
    return path.is_symlink() or path.is_junction()


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys at every mapping depth."""

    @override
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[object, object]:
        """Build a mapping only when each decoded key is unique.

        Raises:
            _UnhashableYamlKeyError: A key cannot be hashed.
            _DuplicateYamlKeyError: A key is repeated.
        """
        self.flatten_mapping(node)
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise _UnhashableYamlKeyError(
                    context_mark=node.start_mark,
                    problem_mark=key_node.start_mark,
                ) from error
            if duplicate:
                raise _DuplicateYamlKeyError(
                    context_mark=node.start_mark,
                    problem_mark=key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _unique_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object and reject repeated property names.

    Raises:
        DuplicateJsonFieldError: A property name is repeated.
    """
    mapping: dict[str, object] = {}
    for key, value in pairs:
        if key in mapping:
            raise DuplicateJsonFieldError(key)
        mapping[key] = value
    return mapping


def _decode_json(text: str) -> tuple[object | None, bool]:
    """Parse JSON while rejecting overwritten properties and hiding excerpts."""
    try:
        return json.loads(text, object_pairs_hook=_unique_json_pairs), False
    except (ValueError, RecursionError):
        return None, True


def _decode_mapping(text: str) -> tuple[object | None, bool]:
    """Parse YAML without returning parser excerpts that may contain secrets."""
    loader = _UniqueKeySafeLoader(text)
    try:
        return loader.get_single_data(), False
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        return None, True
    finally:
        loader.dispose()


def _unread_document(
    relative_path: str,
    *,
    is_directory: bool = False,
    is_symlink: bool = False,
    parse_error: bool = False,
) -> SourceDocument:
    """Describe a path whose bytes are deliberately or necessarily not read."""
    return SourceDocument(
        content=b"",
        frontmatter=None,
        frontmatter_error=False,
        is_directory=is_directory,
        is_symlink=is_symlink,
        parse_error=parse_error,
        relative_path=relative_path,
        text=None,
        yaml_value=None,
    )


def _decode_utf8(content: bytes) -> str | None:
    """Decode UTF-8 text, returning ``None`` for binary content."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _decode_frontmatter(text: str) -> tuple[object | None, bool]:
    """Parse leading ``---`` frontmatter, flagging an unterminated block."""
    lines = text.splitlines()
    if lines[:1] != ["---"]:
        return None, False
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            return _decode_mapping("\n".join(lines[1:index]))
    return None, True


def _decoded_document(path: Path, relative_path: str, content: bytes) -> SourceDocument:
    """Decode captured bytes as text, YAML, and Markdown frontmatter."""
    text = _decode_utf8(content)
    yaml_value: object | None = None
    parse_error = False
    if text is not None and path.suffix.lower() in {".yml", ".yaml"}:
        yaml_value, parse_error = _decode_mapping(text)
    frontmatter, frontmatter_error = (
        _decode_frontmatter(text) if text is not None else (None, False)
    )
    return SourceDocument(
        content=content,
        frontmatter=frontmatter,
        frontmatter_error=frontmatter_error,
        is_directory=False,
        is_symlink=False,
        parse_error=parse_error,
        relative_path=relative_path,
        text=text,
        yaml_value=yaml_value,
    )


def _decode_document(path: Path, relative_path: str) -> SourceDocument:
    """Capture one file while refusing to read a symlink target."""
    try:
        is_symlink = _is_link(path)
        is_directory = path.is_dir() and not is_symlink
        if is_symlink or is_directory:
            return _unread_document(
                relative_path, is_directory=is_directory, is_symlink=is_symlink
            )
        content = path.read_bytes()
    except OSError:
        return _unread_document(relative_path, parse_error=True)
    return _decoded_document(path, relative_path, content)


def _walk_documents(
    base: Path,
    *,
    exclude: Path | None = None,
    excluded_directories: frozenset[str] = frozenset(),
    excluded_suffixes: frozenset[str] = frozenset(),
) -> Iterator[SourceDocument]:
    """Decode files in sorted order, capturing linked directories unfollowed."""
    for current, directories, filenames in os.walk(
        base, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        retained: list[str] = []
        for directory in sorted(directories):
            path = current_path / directory
            if _is_link(path):
                yield _decode_document(path, path.relative_to(base).as_posix())
            else:
                retained.append(directory)
        directories[:] = sorted(set(retained) - excluded_directories)
        for filename in sorted(filenames):
            path = current_path / filename
            if _include_file(
                path, exclude=exclude, excluded_suffixes=excluded_suffixes
            ):
                yield _decode_document(path, path.relative_to(base).as_posix())


def _include_file(
    path: Path, *, exclude: Path | None, excluded_suffixes: frozenset[str]
) -> bool:
    """Skip source bytecode without hiding linked files from validation."""
    return path != exclude and (path.suffix not in excluded_suffixes or _is_link(path))


def _read_provenance(path: Path) -> tuple[object | None, bool]:
    """Read and decode provenance JSON, flagging any read or decode failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, True
    return _decode_json(text)


def _bundle_declaration(definition: object) -> tuple[str, str] | None:
    """Return a declared bundle's safe relative path and kind, if usable."""
    if not _string_mapping(definition):
        return None
    relative = _safe_relative_bundle_path(definition.get("path"))
    if relative is None:
        return None
    kind = definition.get("kind")
    return relative, kind if isinstance(kind, str) else ""


def _retained_directories(
    current: Path, directories: list[str], root: Path, symlinks: list[str]
) -> list[str]:
    """Record linked directories and return the non-generated ones to descend."""
    retained: list[str] = []
    for name in sorted(directories):
        path = current / name
        if _is_link(path):
            symlinks.append(path.relative_to(root).as_posix())
        elif name not in _EXCLUDED_ROOT_DIRECTORIES:
            retained.append(name)
    return retained


def _has_symlink_component(root: Path, relative: str) -> bool:
    """Find symlinks in a declared source path without resolving through them."""
    current = root
    parts = PurePosixPath(relative).parts
    for part in parts:
        if part == ".":
            continue
        current = current / part
        if _is_link(current):
            return True
    return False


def _safe_relative_bundle_path(value: object) -> str | None:
    """Return a safe slash-separated catalog path, or None for unsafe input."""
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return None
    if any(part in {"..", ""} for part in posix.parts):
        return None
    return posix.as_posix()


class FileCatalogAdapter(CatalogPort):
    """Capture source and composed trees using only local filesystem reads."""

    _ROOT_DOCUMENTS = frozenset(
        {
            "AGENTS.md",
            "CHANGELOG.md",
            "CLAUDE.md",
            "CODE_OF_CONDUCT.md",
            "CONTRIBUTING.md",
            "GOVERNANCE.md",
            "PROJECT.md",
            "README.md",
            "SECURITY.md",
            "SUPPORT.md",
            "projects.md",
        }
    )

    def __init__(self) -> None:
        """Create the stateless filesystem adapter."""

    def load(self, root: Path) -> CatalogSnapshot:
        """Capture the catalog tree and each safely declared bundle."""
        root_is_symlink = _is_link(root)
        resolved_root = root.resolve(strict=False)
        if root_is_symlink:
            return CatalogSnapshot(
                bundles=(),
                catalog=None,
                catalog_document=None,
                catalog_error=True,
                policy=None,
                policy_document=None,
                policy_error=True,
                root=resolved_root,
                root_documents=(),
                root_paths=(),
                root_symlinks=(),
                root_is_symlink=True,
            )
        catalog_path = resolved_root / "catalog.json"
        catalog_document = _decode_document(catalog_path, "catalog.json")
        catalog, catalog_error = (
            _decode_json(catalog_document.text)
            if catalog_document.text is not None and not catalog_document.is_symlink
            else (None, True)
        )

        policy_path = resolved_root / "apm-policy.yml"
        policy_document = _decode_document(policy_path, "apm-policy.yml")
        policy = policy_document.yaml_value
        policy_error = policy_document.parse_error or policy_document.text is None

        bundles = self._load_bundles(resolved_root, catalog)
        root_documents = self._load_root_documents(resolved_root)
        root_paths, root_symlinks = self._list_root_paths(resolved_root)
        return CatalogSnapshot(
            bundles=bundles,
            catalog=catalog,
            catalog_document=catalog_document,
            catalog_error=catalog_error,
            policy=policy,
            policy_document=policy_document,
            policy_error=policy_error,
            root=resolved_root,
            root_documents=root_documents,
            root_paths=root_paths,
            root_symlinks=root_symlinks,
            root_is_symlink=root_is_symlink,
        )

    def load_composed(self, root: Path) -> ComposedSnapshot:
        """Capture composed files and provenance without following symlinks."""
        root_is_symlink = _is_link(root)
        resolved_root = root.resolve(strict=False)
        provenance_path = resolved_root / "provenance.json"
        provenance_is_symlink = _is_link(provenance_path)
        provenance, provenance_error = (
            (None, True)
            if root_is_symlink or provenance_is_symlink
            else _read_provenance(provenance_path)
        )
        files = (
            tuple(_walk_documents(resolved_root, exclude=provenance_path))
            if resolved_root.is_dir() and not root_is_symlink
            else ()
        )
        return ComposedSnapshot(
            files=files,
            provenance=provenance,
            provenance_error=provenance_error,
            provenance_is_symlink=provenance_is_symlink,
            root=resolved_root,
            root_is_symlink=root_is_symlink,
        )

    def _load_bundles(
        self, root: Path, catalog: object | None
    ) -> tuple[BundleSource, ...]:
        """Capture every bundle the decoded catalog declares at a safe path."""
        raw_bundles = catalog.get("bundles") if _string_mapping(catalog) else None
        if not _string_mapping(raw_bundles):
            return ()
        bundles: list[BundleSource] = []
        for name, definition in raw_bundles.items():
            declaration = _bundle_declaration(definition)
            if declaration is not None:
                relative, kind = declaration
                bundles.append(self._load_bundle(root, name, relative, kind))
        return tuple(bundles)

    def _load_bundle(
        self, root: Path, name: str, relative: str, kind: str
    ) -> BundleSource:
        """Capture a bundle's manifest and .apm files without following links."""
        bundle_root = (
            root if relative == "." else root.joinpath(*PurePosixPath(relative).parts)
        )
        root_is_symlink = _has_symlink_component(root, relative)
        apm_root = bundle_root / ".apm"
        apm_is_symlink = _is_link(apm_root)
        apm_exists = apm_root.is_dir() and not apm_is_symlink and not root_is_symlink

        manifest_relative = f"{relative}/apm.yml"
        manifest_document = (
            _unread_document(manifest_relative, is_symlink=True, parse_error=True)
            if root_is_symlink
            else _decode_document(bundle_root / "apm.yml", manifest_relative)
        )
        manifest_error = (
            manifest_document.parse_error
            or manifest_document.text is None
            or manifest_document.is_symlink
        )
        files = (
            tuple(
                _walk_documents(
                    apm_root,
                    excluded_directories=_BYTECODE_DIRECTORIES,
                    excluded_suffixes=_BYTECODE_SUFFIXES,
                )
            )
            if apm_exists
            else ()
        )

        return BundleSource(
            apm_exists=apm_exists,
            files=files,
            kind=kind,
            manifest=manifest_document.yaml_value,
            manifest_document=manifest_document,
            manifest_error=manifest_error,
            manifest_is_symlink=manifest_document.is_symlink,
            name=name,
            path=relative,
            root_is_symlink=root_is_symlink or apm_is_symlink,
        )

    def _load_root_documents(self, root: Path) -> tuple[SourceDocument, ...]:
        """Read root markdown guidance and the machine-readable index."""
        documents: list[SourceDocument] = []
        candidates: list[Path] = []
        try:
            candidates.extend(
                path
                for path in root.iterdir()
                if path.is_file()
                and path.suffix.lower() == ".md"
                and path.name in self._ROOT_DOCUMENTS
            )
        except OSError:
            return ()
        candidates.extend((root / "AGENTS.md", root / "llms.txt", root / "LICENSE"))
        unique = {path.name: path for path in candidates}
        documents.extend(
            _decode_document(path, path.name)
            for path in sorted(unique.values())
            if path.exists() or path.is_symlink()
        )
        return tuple(documents)

    def _list_root_paths(self, root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """List source paths and symlinks without traversing linked directories."""
        if not root.is_dir():
            return (), ()
        paths: list[str] = []
        symlinks: list[str] = []
        for current, directories, filenames in os.walk(
            root, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            directories[:] = _retained_directories(
                current_path, directories, root, symlinks
            )
            for filename in sorted(filenames):
                path = current_path / filename
                relative = path.relative_to(root).as_posix()
                (symlinks if _is_link(path) else paths).append(relative)
        return tuple(paths), tuple(symlinks)
