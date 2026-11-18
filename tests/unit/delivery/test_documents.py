"""Strict document unit regressions adapted from Delivery Kit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from delivery_tools.documents import (
    MAX_DOCUMENT_BYTES,
    DocumentError,
    parse_json,
    parse_yaml,
    read_catalog_yaml,
    read_json,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text",
    ["x: a\nx: b\n", "a: &a [*a]\n", "[]", "1: value\n", "x: !!python/object:x {}"],
)
def test_yaml_rejects_ambiguous_or_unsafe_documents(text: str) -> None:
    with pytest.raises((DocumentError, yaml.YAMLError)):
        parse_yaml(text)


@pytest.mark.parametrize(
    "text",
    ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', "[]", "null"],
)
def test_json_rejects_ambiguous_documents(text: str) -> None:
    with pytest.raises(DocumentError):
        parse_json(text)


def test_github_on_and_typed_source_scalars() -> None:
    assert parse_yaml("on:\n  workflow_call:\n", workflow=True) == {
        "on": {"workflow_call": ""}
    }
    assert parse_yaml("flag: false\ncount: 3") == {"flag": False, "count": 3}


@pytest.mark.parametrize("parser", [parse_json, parse_yaml])
def test_bounded_input(parser: object) -> None:
    assert callable(parser)
    with pytest.raises(DocumentError, match="size limit"):
        parser(" " * (MAX_DOCUMENT_BYTES + 1))


def test_file_boundary_rejects_oversized_input(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(b" " * (MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(DocumentError, match="size limit"):
        read_json(source)


def test_catalog_loader_preserves_types_without_changing_other_loaders(
    tmp_path: Path,
) -> None:
    source = tmp_path / "workflow.yml"
    text = "on: {}\nflag: false\ncount: 3\ntext: 'false'\nlegacy: on\n"
    source.write_text(text, encoding="utf-8")
    assert read_catalog_yaml(source) == {
        "on": {},
        "flag": False,
        "count": 3,
        "text": "false",
        "legacy": "on",
    }
    assert parse_yaml("legacy: on\n") == {"legacy": True}
    assert yaml.safe_load("legacy: on\n") == {"legacy": True}
    assert parse_yaml(text, workflow=True)["flag"] == "false"


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("value: [", yaml.YAMLError),
        ("value: !!python/object:x {}", yaml.YAMLError),
        ("value: 2026-99-99", ValueError),
        ("value: !!bool maybe", KeyError),
        ("value: !!timestamp invalid", AttributeError),
        pytest.param(
            "value: !!float " + ":".join(["1"] * 200),
            OverflowError,
            id="overflowing-tagged-number",
        ),
    ],
)
def test_yaml_decoder_errors_are_chained(
    tmp_path: Path, text: str, cause: type[Exception]
) -> None:
    source = tmp_path / "workflow.yml"
    source.write_text(text, encoding="utf-8")
    with pytest.raises(DocumentError, match="YAML") as caught:
        read_catalog_yaml(source)
    assert isinstance(caught.value.__cause__, cause)
    with pytest.raises(DocumentError, match="YAML") as caught:
        parse_yaml(text)
    assert isinstance(caught.value.__cause__, cause)


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("name: first\nname: second", "duplicate"),
        ("1: value", "name"),
        ("value: &value [*value]", "aliases"),
        ("[]", "mapping"),
        pytest.param(
            " " * (MAX_DOCUMENT_BYTES + 1), "size limit", id="oversized-document"
        ),
    ],
)
def test_catalog_yaml_boundary_rejects_invalid_documents(
    tmp_path: Path, text: str, field: str
) -> None:
    source = tmp_path / "workflow.yml"
    source.write_text(text, encoding="utf-8")
    with pytest.raises(DocumentError, match=field):
        read_catalog_yaml(source)
