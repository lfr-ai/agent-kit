"""Strict decoders reject ambiguous JSON, YAML, and Markdown frontmatter."""

from __future__ import annotations

import pytest

from agent_kit.core.errors import DuplicateJSONFieldError
from agent_kit.infrastructure.documents import (
    decode_frontmatter,
    decode_json,
    decode_yaml,
    load_json,
)

_DEEP_NESTING = 100_000


def test_load_json_rejects_a_repeated_property() -> None:
    with pytest.raises(DuplicateJSONFieldError, match="'a'"):
        load_json('{"nested": {"a": 1, "a": 2}}')


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": [1, 2]}', ({"a": [1, 2]}, False)),
        ('{"a": 1, "a": 2}', (None, True)),
        ("{", (None, True)),
        pytest.param("[" * _DEEP_NESTING, (None, True), id="deep-nesting"),
    ],
)
def test_decode_json_reports_invalid_text_without_raising(
    text: str, expected: tuple[object | None, bool]
) -> None:
    assert decode_json(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: {b: 1}", ({"a": {"b": 1}}, False)),
        ("a:\n  b: 1\n  b: 2\n", (None, True)),
        ("? [1, 2]\n: value\n", (None, True)),
        ("a: [", (None, True)),
        ("a: !!python/object:os.system x", (None, True)),
    ],
)
def test_decode_yaml_rejects_ambiguous_or_unsafe_mappings(
    text: str, expected: tuple[object | None, bool]
) -> None:
    assert decode_yaml(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# Title\n", (None, False)),
        ("---\nname: x\n---\nbody\n", ({"name": "x"}, False)),
        ("---\nname: x\n", (None, True)),
        ("---\nname: x\nname: y\n---\n", (None, True)),
    ],
)
def test_decode_frontmatter_requires_a_terminated_unique_block(
    text: str, expected: tuple[object | None, bool]
) -> None:
    assert decode_frontmatter(text) == expected
