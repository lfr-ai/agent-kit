"""The bundled convention checker is exercised as installed source, not a copied guard."""

import runpy
from pathlib import Path

import pytest

_PATH = (
    Path(__file__).parents[3]
    / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)


@pytest.mark.parametrize(
    "text",
    [
        "from typing import Any\n",
        "from logging import getLogger\n",
        "def run(x: 'Thing') -> None: pass\n",
        "class Thing:\n def __init__(self): pass\n",
        "from dataclasses import dataclass\n@dataclass\nclass Thing: pass\n",
        f'def run() -> None:\n    """Run {chr(96)}name{chr(96)}."""\n',
        f'"""Module {chr(96) * 2}name{chr(96) * 2}."""\n',
    ],
)
def test_convention_asset_rejects_the_known_violation(text: str) -> None:
    """Original convention guarantees remain executable after extraction."""
    namespace = runpy.run_path(str(_PATH))
    assert namespace["violations"](text, "synthetic.py")


def test_convention_asset_accepts_single_quoted_docstring_code() -> None:
    """Single-quoted inline code and backticks outside docstrings stay valid."""
    namespace = runpy.run_path(str(_PATH))
    source = (
        f'_FENCE = "{chr(96) * 3}"\n\n\ndef run() -> None:\n    """Run \'name\'."""\n'
    )
    assert namespace["violations"](source, "synthetic.py") == []


def test_convention_asset_accepts_concrete_keyword_only_records() -> None:
    """Valid source is not rejected merely because it uses dataclasses."""
    namespace = runpy.run_path(str(_PATH))
    assert (
        namespace["violations"](
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True, kw_only=True, slots=True)\nclass Value: count: int\n",
            "synthetic.py",
        )
        == []
    )
