"""Unit checks that imported Renovate regexes match synthetic consumer pins."""

from __future__ import annotations

import re

import pytest

from delivery_tools.catalog import ROOT, nodes
from delivery_tools.documents import read_json

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('uv-version: "0.12.24"', "uv"),
        ('bunVersion: "1.3.11"', "oven-sh/bun"),
        ('bicepVersion: "0.48.1"', "Azure/bicep"),
        ('terraform-version: "1.16.5"', "hashicorp/terraform"),
        ('tflintVersion: "0.65.0"', "terraform-linters/tflint"),
    ],
)
def test_tool_pin_manager_matches_versions(source: str, expected: str) -> None:
    managers = nodes(read_json(ROOT / "renovate/tool-pins.json"))
    manager = next(node for node in managers if node.get("depNameTemplate") == expected)
    raw = manager["matchStrings"]
    assert isinstance(raw, list)
    patterns = [pattern for pattern in raw if isinstance(pattern, str)]
    assert patterns
    assert any(
        re.search(pattern.replace("(?<", "(?P<"), source) for pattern in patterns
    )


def test_avm_manager_preserves_module_and_version() -> None:
    source = "module synthetic 'br/public:avm/res/storage/storage-account:0.14.3' = {}"
    managers = list(nodes(read_json(ROOT / "renovate/bicep.json")))
    manager = next(node for node in managers if node.get("customType") == "regex")
    patterns = manager["matchStrings"]
    assert isinstance(patterns, list)
    pattern = patterns[0]
    assert isinstance(pattern, str)
    match = re.search(pattern.replace("(?<", "(?P<"), source)
    assert match
    assert match.groupdict() == {
        "depName": "avm/res/storage/storage-account",
        "currentValue": "0.14.3",
    }
