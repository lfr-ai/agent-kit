"""Always-on context budget regressions for every selectable profile."""

from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_APPLY_TO = re.compile(r'^applyTo:\s*"(?P<scope>[^"]*)"', re.MULTILINE)
_ALWAYS_ON = {"**", "**/*"}
_MAX_ALWAYS_ON = 1
_MAX_SAME_SCOPE = 2
_MAX_INSTRUCTION_LINES = 20
# Upper bound with every bundle installed; overlapping globs count once each.
_MAX_INSTRUCTIONS_PER_PATH = 7
_MAX_INSTRUCTION_CHARS_PER_PATH = 12_000
_REPRESENTATIVE_PATHS = (
    "src/app/main.py",
    "tests/unit/test_service.py",
    "pyproject.toml",
    "web/src/App.tsx",
    "web/src/App.test.tsx",
    "package.json",
    "infra/main.tf",
    "infra/main.bicep",
    "template.yaml",
    "Dockerfile",
    "compose.yaml",
    ".github/workflows/ci.yml",
    "scripts/deploy.sh",
    "nginx/nginx.conf",
    "README.md",
    "docs/guide.md",
)


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


def _all_instructions() -> list[tuple[str, tuple[str, ...], int]]:
    """Return each instruction's name, ``applyTo`` globs, and character count."""
    instructions: list[tuple[str, tuple[str, ...], int]] = []
    for bundle in _section("bundles").values():
        root = _ROOT / bundle["path"] / ".apm/instructions"
        for path in sorted(root.glob("*.instructions.md")):
            text = path.read_text(encoding="utf-8")
            match = _APPLY_TO.search(text)
            assert match, f"{path.name} has no applyTo scope"
            globs = tuple(item.strip() for item in match["scope"].split(","))
            instructions.append((path.name, globs, len(text)))
    return instructions


@pytest.mark.parametrize("path", _REPRESENTATIVE_PATHS)
def test_one_file_loads_bounded_instruction_context(path: str) -> None:
    """Overlapping globs from different bundles must not stack on one file."""
    target = PurePosixPath(path)
    loaded = [
        (name, size)
        for name, globs, size in _all_instructions()
        if any(target.full_match(pattern) for pattern in globs)
    ]

    assert len(loaded) <= _MAX_INSTRUCTIONS_PER_PATH, loaded
    assert sum(size for _, size in loaded) <= _MAX_INSTRUCTION_CHARS_PER_PATH, loaded
