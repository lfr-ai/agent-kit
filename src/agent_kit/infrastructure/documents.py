"""Strict JSON, YAML, and Markdown frontmatter decoders for source documents."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, override

import yaml
import yaml.constructor

from agent_kit.core.guards import unique_json_object
from agent_kit.core.primitives import FRONTMATTER_DELIMITER

if TYPE_CHECKING:
    from yaml.error import Mark
    from yaml.nodes import MappingNode


class _UnhashableYAMLKeyError(yaml.constructor.ConstructorError):
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


class _DuplicateYAMLKeyError(yaml.constructor.ConstructorError):
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


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys at every mapping depth."""

    @override
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[object, object]:
        """Build a mapping only when each decoded key is unique.

        Args:
            node (MappingNode): YAML mapping whose keys and values are decoded.
            deep (bool): Whether nested values are fully constructed immediately.

        Returns:
            dict[object, object]: Decoded entries with hashable, unique keys.

        Raises:
            _UnhashableYAMLKeyError: A key cannot be hashed.
            _DuplicateYAMLKeyError: A key is repeated.
        """
        self.flatten_mapping(node)
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as error:
                raise _UnhashableYAMLKeyError(
                    context_mark=node.start_mark,
                    problem_mark=key_node.start_mark,
                ) from error
            if duplicate:
                raise _DuplicateYAMLKeyError(
                    context_mark=node.start_mark,
                    problem_mark=key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_json(text: str) -> object:
    """Parse JSON ``text``; a repeated property raises ``DuplicateJSONFieldError``."""
    return json.loads(text, object_pairs_hook=unique_json_object)


def decode_json(text: str) -> tuple[object | None, bool]:
    """Parse JSON ``text`` into ``(value, error)``; ``(None, True)`` when invalid.

    Repeated properties and excessive nesting are invalid; parser excerpts are
    hidden.
    """
    try:
        return load_json(text), False
    except (ValueError, RecursionError):
        return None, True


def decode_yaml(text: str) -> tuple[object | None, bool]:
    """Parse YAML ``text`` into ``(value, error)``; ``(None, True)`` when invalid.

    Repeated keys are invalid. Parser excerpts, which may contain secrets, are
    never returned.
    """
    loader = _UniqueKeySafeLoader(text)
    try:
        return loader.get_single_data(), False
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        return None, True
    finally:
        loader.dispose()


def decode_frontmatter(text: str) -> tuple[object | None, bool]:
    """Parse leading ``---`` frontmatter into ``(value, error)``.

    Text without frontmatter gives ``(None, False)`` and an unterminated block
    gives ``(None, True)``; a terminated block is parsed as YAML.
    """
    lines = text.splitlines()
    if lines[:1] != [FRONTMATTER_DELIMITER]:
        return None, False
    for index, line in enumerate(lines[1:], start=1):
        if line == FRONTMATTER_DELIMITER:
            return decode_yaml("\n".join(lines[1:index]))
    return None, True
