"""Strict document boundaries adapted from Delivery Kit (see LICENSE)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final, TypeGuard, override

import yaml
from yaml.tokens import AliasToken

if TYPE_CHECKING:
    from collections.abc import Hashable
    from pathlib import Path

    from yaml.nodes import MappingNode

MAX_DOCUMENT_BYTES: Final[int] = 1_000_000
_TOO_LARGE = "Document exceeds the validation size limit"
_DUPLICATE_KEY = "Document contains a duplicate or non-string mapping key/name"
_ALIAS = "YAML aliases are not supported in validation inputs"
_NOT_MAPPING = "Expected a string-keyed document mapping"
_DUPLICATE_JSON_KEY = "JSON document contains a duplicate mapping key"
_NON_FINITE = "JSON document contains a non-finite value"
_INVALID_YAML = "Invalid YAML document"
_BOOL_TAG = "tag:yaml.org,2002:bool"
# SafeConstructor can leak built-in errors for malformed explicit scalar tags.
_YAML_ERRORS = (
    yaml.YAMLError,
    ValueError,
    KeyError,
    AttributeError,
    OverflowError,
    RecursionError,
)


class DocumentError(ValueError):
    """Document is ambiguous, unsupported or too large for validation."""


def is_mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow a decoded value to a dictionary with string keys."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def mapping(value: object) -> dict[str, object]:
    """Return the original string-keyed mapping or raise ``DocumentError``."""
    if not is_mapping(value):
        raise DocumentError(_NOT_MAPPING)
    return value


def _construct_mapping(
    loader: yaml.BaseLoader | yaml.SafeLoader, node: MappingNode, *, deep: bool
) -> dict[Hashable, object]:
    """Reject ambiguous keys and attach field context to safe-constructor errors."""
    result: dict[Hashable, object] = {}
    for key_node, value_node in node.value:
        key: object = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise DocumentError(_DUPLICATE_KEY)
        try:
            result[key] = loader.construct_object(value_node, deep=deep)
        except DocumentError:
            raise
        except _YAML_ERRORS as exc:
            message = f"{key}: invalid YAML value"
            raise DocumentError(message) from exc
    return result


class _SourceLoader(yaml.SafeLoader):
    @override
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[Hashable, object]:
        return _construct_mapping(self, node, deep=deep)


class _WorkflowLoader(yaml.BaseLoader):
    @override
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[Hashable, object]:
        return _construct_mapping(self, node, deep=deep)


class _CatalogLoader(_SourceLoader):
    """Safe typed workflow scalars with an isolated boolean resolver."""


# Copy resolver lists, not the SafeLoader's shared registry. YAML 1.1's
# yes/no/on/off tokens are strings in GitHub metadata, not booleans.
_CatalogLoader.yaml_implicit_resolvers = {
    initial: [(tag, pattern) for tag, pattern in resolvers if tag != _BOOL_TAG]
    for initial, resolvers in _SourceLoader.yaml_implicit_resolvers.items()
}
_CatalogLoader.add_implicit_resolver(
    _BOOL_TAG, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)


def _reject_aliases(text: str) -> None:
    """Reject aliases before decoding to prevent cyclic or expanded documents."""
    if any(isinstance(token, AliasToken) for token in yaml.scan(text)):
        raise DocumentError(_ALIAS)


def _parse_yaml(
    text: str, *, loader: type[_SourceLoader | _WorkflowLoader]
) -> dict[str, object]:
    """Bound YAML decoding and normalize vendor errors without echoing source values."""
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise DocumentError(_TOO_LARGE)
    try:
        _reject_aliases(text)
        value: object = yaml.load(text, Loader=loader)  # noqa: S506 - safe loaders only
    except DocumentError:
        raise
    except _YAML_ERRORS as exc:
        raise DocumentError(_INVALID_YAML) from exc
    return mapping(value)


def parse_yaml(text: str, *, workflow: bool = False) -> dict[str, object]:
    """Parse unique YAML mappings; ``workflow=True`` retains legacy scalar text.

    Typed GitHub catalog extraction uses ``read_catalog_yaml`` instead. Oversized,
    invalid, aliased, unsafe, too deeply nested or ambiguous YAML propagates
    ``DocumentError``.
    """
    loader = _WorkflowLoader if workflow else _SourceLoader
    return _parse_yaml(text, loader=loader)


def read_text(path: Path) -> str:
    """Read bounded UTF-8 input, raising ``DocumentError`` above the size limit.

    A file that cannot be inspected or read propagates ``OSError``; invalid
    UTF-8 propagates ``UnicodeError``.
    """
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise DocumentError(_TOO_LARGE)
    return path.read_text(encoding="utf-8")


def read_yaml(path: Path, *, workflow: bool = False) -> dict[str, object]:
    """Read bounded YAML without overwriting duplicate keys.

    ``workflow=True`` preserves legacy text scalars for source-policy inspection.
    Read failures follow ``read_text`` and parse failures ``parse_yaml``.
    """
    return parse_yaml(read_text(path), workflow=workflow)


def read_catalog_yaml(path: Path) -> dict[str, object]:
    """Read typed GitHub metadata without treating ``on`` as a boolean key.

    Implicit booleans use true/false tokens; ordinary quoted scalars stay text
    unless explicitly tagged. The resolver is isolated from other YAML readers.
    Failures propagate as in ``read_yaml``.
    """
    return _parse_yaml(read_text(path), loader=_CatalogLoader)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys before pairs collapse into a mapping."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError(_DUPLICATE_JSON_KEY)
        result[key] = value
    return result


def _invalid_constant(_value: str) -> object:
    raise DocumentError(_NON_FINITE)


def parse_json(text: str) -> dict[str, object]:
    """Parse a bounded JSON mapping with unique keys and finite values.

    Oversized, duplicated, non-finite or non-mapping text raises
    ``DocumentError``; invalid JSON propagates ``json.JSONDecodeError``.
    """
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise DocumentError(_TOO_LARGE)
    value: object = json.loads(
        text, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
    )
    return mapping(value)


def read_json(path: Path) -> dict[str, object]:
    """Read a bounded strict JSON mapping via ``read_text`` and ``parse_json``."""
    return parse_json(read_text(path))
