"""Always-on context budget regressions for every selectable profile."""

from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_APPLY_TO = re.compile(r'^applyTo:\s*"(?P<scope>[^"]*)"', re.MULTILINE)
_FRONTMATTER = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n", re.DOTALL)
_SKILL_TRIGGER = "Use when"
_ROLE_TRIGGER = "Use "
_ALWAYS_ON = {"**", "**/*"}
_MAX_ALWAYS_ON = 1
_MAX_SAME_SCOPE = 2
_MAX_INSTRUCTION_LINES = 20
# Upper bound with every bundle installed; overlapping globs count once each.
_MAX_INSTRUCTIONS_PER_PATH = 7
_MAX_INSTRUCTION_CHARS_PER_PATH = 12_000
# Every root session loads AGENTS.md plus its host adapter; detail belongs in
# path-scoped rules and on-demand skills.
_ENTRY_FILES = ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md")
_MAX_ENTRY_CHARS = 5_000
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


def _always_on(scopes: Counter[str]) -> int:
    """Count instructions whose ``applyTo`` list contains an every-file glob."""
    return sum(
        count
        for scope, count in scopes.items()
        if _ALWAYS_ON & {glob.strip() for glob in scope.split(",")}
    )


@pytest.mark.parametrize("profile", sorted(_profiles()))
def test_profile_has_bounded_always_on_instruction_context(profile: str) -> None:
    """Broad instruction scopes stay few so every edit does not load duplicates."""
    scopes = _scopes(profile)

    assert _always_on(scopes) <= _MAX_ALWAYS_ON
    assert max(scopes.values(), default=0) <= _MAX_SAME_SCOPE


@pytest.mark.parametrize("scope", ["**", "**/*", "src/**,**", "src/**, **/*"])
def test_an_every_file_glob_in_a_list_is_always_on(scope: str) -> None:
    """Listing a narrow glob first cannot hide an every-file scope."""
    assert _always_on(Counter({scope: 1, "**/*.py": 1, "src/**": 1})) == 1


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


def _skill_descriptions() -> dict[str, str]:
    """Map every authored skill (root and bundles) to its frontmatter description."""
    roots = [_ROOT / ".apm/skills"] + [
        _ROOT / bundle["path"] / ".apm/skills"
        for bundle in _section("bundles").values()
    ]
    descriptions: dict[str, str] = {}
    for path in sorted({skill for root in roots for skill in root.glob("*/SKILL.md")}):
        match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
        assert match, f"{path} has no frontmatter"
        descriptions[path.relative_to(_ROOT).as_posix()] = yaml.safe_load(
            match["yaml"]
        )["description"]
    return descriptions


def test_every_skill_description_is_a_distinct_trigger() -> None:
    """Descriptions are the always-loaded routing surface: one trigger form, no twins."""
    descriptions = _skill_descriptions()

    assert descriptions, "No authored skills were discovered"
    off_pattern = sorted(
        name
        for name, text in descriptions.items()
        if not text.startswith(_SKILL_TRIGGER)
    )
    assert off_pattern == [], f"Start skill descriptions with {_SKILL_TRIGGER!r}"
    twins = [
        text for text, count in Counter(descriptions.values()).items() if count > 1
    ]
    assert twins == [], "Identical descriptions make skill routing ambiguous"


def test_root_entry_files_share_one_always_on_budget() -> None:
    """Host adapters and the shared policy cannot grow the always-loaded prefix."""
    sizes = {
        name: len((_ROOT / name).read_text(encoding="utf-8")) for name in _ENTRY_FILES
    }

    assert sum(sizes.values()) <= _MAX_ENTRY_CHARS, sizes


def test_every_native_role_description_is_a_trigger() -> None:
    """Role descriptions load into every picker, so they state when to use the role."""
    path = _ROOT / "packages/shared/.apm/skills/kit-agent-runtime/assets/agents.json"
    roles = json.loads(path.read_text(encoding="utf-8"))["roles"]

    assert roles, "No native roles were discovered"
    assert [
        role["id"]
        for role in roles
        if not role["description"].startswith(_ROLE_TRIGGER)
    ] == [], f"Start role descriptions with {_ROLE_TRIGGER!r}"
