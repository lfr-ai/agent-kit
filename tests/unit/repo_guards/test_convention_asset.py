"""The bundled convention checker is exercised as installed source, not a copied guard."""

from pathlib import Path
import runpy

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
        'def run() -> None:\n    """Run \'name\'."""\n',
        'def run() -> None:\n    """Run \'an exact phrase\'."""\n',
        f'"""Module {chr(96) * 2}name."""\n',
        f'"""Module {chr(96) * 3}name{chr(96) * 3}."""\n',
    ],
)
def test_convention_asset_rejects_the_known_violation(text: str) -> None:
    """Original convention guarantees remain executable after extraction."""
    namespace = runpy.run_path(str(_PATH))
    assert namespace["violations"](text, "synthetic.py")


def test_convention_asset_accepts_double_backtick_docstring_code() -> None:
    """Double-backtick inline literals and backticks outside docs stay valid."""
    namespace = runpy.run_path(str(_PATH))
    source = (
        f'_FENCE = "{chr(96) * 3}"\n\n'
        f'def run() -> None:\n    """Run {chr(96) * 2}name{chr(96) * 2}."""\n'
    )
    assert namespace["violations"](source, "synthetic.py") == []


def test_convention_asset_can_select_docstring_rule(tmp_path: Path) -> None:
    """The docstring-only gate can scan assets without applying unrelated rules."""
    source = tmp_path / "asset.py"
    source.write_text(
        'from typing import Any\n\ndef run() -> None:\n    """Run ``name``."""\n',
        encoding="utf-8",
    )
    namespace = runpy.run_path(str(_PATH))

    assert namespace["main"](["--only", "docstring-backtick", str(source)]) == 0


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
