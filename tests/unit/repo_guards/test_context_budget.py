"""Always-on context budget regressions for every selectable profile."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_APPLY_TO = re.compile(r'^applyTo:\s*"(?P<scope>[^"]*)"', re.MULTILINE)
_ALWAYS_ON = {"**", "**/*"}
_MAX_ALWAYS_ON = 1
_MAX_SAME_SCOPE = 2
_MAX_INSTRUCTION_LINES = 20


def _section(name: str) -> dict[str, dict[str, str]]:
    """Read one catalog section whose entries are string mappings."""
    return json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))[name]


def _profiles() -> dict[str, dict[str, list[str]]]:
    return json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))["profiles"]


def _bundles(profile: str, profiles: dict[str, dict[str, list[str]]]) -> set[str]:
    """Resolve a profile's bundles through its inheritance chain."""
    selected = set(profiles[profile]["bundles"])
    for parent in profiles[profile]["extends"]:
        selected |= _bundles(parent, profiles)
    return selected


def _scopes(profile: str) -> Counter[str]:
    """Count instruction scopes that would be delivered for one profile."""
    bundles = _section("bundles")
    scopes: Counter[str] = Counter()
    for name in _bundles(profile, _profiles()):
        root = _ROOT / bundles[name]["path"] / ".apm/instructions"
        for path in sorted(root.glob("*.instructions.md")):
            text = path.read_text(encoding="utf-8")
            assert len(text.splitlines()) <= _MAX_INSTRUCTION_LINES, path.name
            match = _APPLY_TO.search(text)
            assert match, f"{path.name} has no applyTo scope"
            scopes[match["scope"]] += 1
    return scopes


@pytest.mark.parametrize("profile", sorted(_profiles()))
def test_profile_has_bounded_always_on_instruction_context(profile: str) -> None:
    """Broad instruction scopes stay few so every edit does not load duplicates."""
    scopes = _scopes(profile)

    assert sum(scopes[scope] for scope in _ALWAYS_ON) <= _MAX_ALWAYS_ON
    assert max(scopes.values(), default=0) <= _MAX_SAME_SCOPE
