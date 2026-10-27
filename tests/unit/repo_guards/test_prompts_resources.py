"""Repository guards for the portable prompt files delivered by each package."""

from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

ROOT = Path(__file__).parents[3]
PACKAGES = ROOT / "packages"
EXPECTED: dict[str, frozenset[str]] = {
    "shared": frozenset(
        {
            "kit-plan-change",
            "kit-verify-change",
            "kit-review-change",
            "kit-write-commit-message",
            "kit-align-tests",
            "kit-align-consistency",
            "kit-refactor-safely",
            "kit-onboard-codebase",
            "kit-reflect-and-learn",
            "kit-prepare-release",
            "kit-write-docs",
            "kit-hand-off",
            "kit-run-feedback-loop",
            "kit-improve",
        }
    ),
    "backend": frozenset(
        {
            "kit-align-python-conventions",
            "kit-add-endpoint",
            "kit-add-migration",
            "kit-model-domain",
            "kit-add-middleware",
            "kit-add-cache",
            "kit-design-rate-limit",
        }
    ),
    "frontend": frozenset(
        {
            "kit-add-feature",
            "kit-add-form",
            "kit-add-route",
            "kit-add-realtime",
            "kit-manage-server-state",
            "kit-audit-accessibility",
        }
    ),
    "ai": frozenset(
        {"kit-evaluate-retrieval", "kit-add-llm-call", "kit-run-llm-experiment"}
    ),
    "iac": frozenset(
        {
            "kit-harden-workflow",
            "kit-plan-deployment",
        }
    ),
    "terraform": frozenset({"kit-review-terraform-plan"}),
    "bicep": frozenset({"kit-review-bicep-whatif"}),
    "workflows": frozenset(
        {
            "kit-spec-explore",
            "kit-spec-propose",
            "kit-spec-apply",
            "kit-spec-verify",
            "kit-spec-archive",
            "kit-analyze-impact",
            "kit-simplify",
            "kit-audit-codebase",
            "kit-modernize",
            "kit-improve-codebase",
        }
    ),
    "coordination": frozenset({"kit-deliver-fullstack-feature"}),
}
PROMPTS = sorted(
    (package, name) for package, names in EXPECTED.items() for name in names
)
_LINK = re.compile(r"\]\(([^)#\s]+)")
_SKILL_LINK = re.compile(r"\]\(\.\./skills/(kit-[a-z0-9-]+)/SKILL\.md\)")
_SECTIONS = ("## Input", "## Procedure", "## Acceptance gates", "## Output")


def _prompt_path(package: str, name: str) -> Path:
    """Return the source path of one package prompt."""
    return PACKAGES / package / ".apm" / "prompts" / f"{name}.prompt.md"


def _split(text: str) -> tuple[dict[str, str], str]:
    """Split a prompt into parsed frontmatter and body."""
    _, header, body = text.split("---\n", 2)
    metadata = yaml.safe_load(header)
    assert isinstance(metadata, dict)
    return {str(key): str(value) for key, value in metadata.items()}, body


@pytest.mark.parametrize("package", sorted(EXPECTED))
def test_package_ships_exactly_its_prompts(package: str) -> None:
    """Each package includes its prompt folder and owns the expected prompts."""
    manifest = yaml.safe_load(
        (PACKAGES / package / "apm.yml").read_text(encoding="utf-8")
    )
    present = {
        path.name.removesuffix(".prompt.md")
        for path in (PACKAGES / package / ".apm" / "prompts").glob("*.prompt.md")
    }

    assert ".apm/prompts/" in manifest["includes"]
    assert present == EXPECTED[package]


@pytest.mark.parametrize(("package", "name"), PROMPTS)
def test_prompt_metadata_is_portable(package: str, name: str) -> None:
    """Prompts keep discovery-only metadata with a short one-line description."""
    raw = _prompt_path(package, name).read_bytes()
    metadata, _ = _split(raw.decode("utf-8"))

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert set(metadata) == {"description", "argument-hint", "agent"}
    assert 0 < len(metadata["description"]) <= 160
    assert metadata["agent"] in {"agent", "ask"}
    assert "$ARGUMENTS" not in raw.decode("utf-8")
    assert "${input:" not in raw.decode("utf-8")


@pytest.mark.parametrize(("package", "name"), PROMPTS)
def test_prompt_body_is_a_complete_procedure(package: str, name: str) -> None:
    """Prompts have the shared sections, a bounded length, and an owning skill."""
    path = _prompt_path(package, name)
    text = path.read_text(encoding="utf-8")
    _, body = _split(text)
    skills = set(_SKILL_LINK.findall(body))

    assert 25 <= len(text.splitlines()) <= 80
    assert all(section in body for section in _SECTIONS)
    assert "user-supplied argument" in body
    assert skills
    for skill in skills:
        assert (PACKAGES / package / ".apm" / "skills" / skill / "SKILL.md").is_file()


@pytest.mark.parametrize(("package", "name"), PROMPTS)
def test_prompt_links_stay_inside_the_package(package: str, name: str) -> None:
    """Every local link resolves inside the same package source folder."""
    path = _prompt_path(package, name)
    apm = (PACKAGES / package / ".apm").resolve()

    for target in _LINK.findall(path.read_text(encoding="utf-8")):
        if "://" in target:
            continue
        resolved = (path.parent / target).resolve()
        assert resolved.is_file(), target
        assert resolved.is_relative_to(apm), target


def test_improvement_prompt_ships_with_its_procedures_but_not_narrow_sessions() -> None:
    """The opt-in improvement facade retains its owners without widening sessions."""
    snapshot = FileCatalogAdapter().load(ROOT)
    service = CatalogService()
    project = service.compose(snapshot, "workflows", (), ())
    files = {item.relative_path: item.content for item in project.files}
    prompt = "kit-improve-codebase"

    assert (
        files[f".apm/prompts/{prompt}.prompt.md"]
        == _prompt_path("workflows", prompt).read_bytes()
    )
    for skill in (
        "kit-codebase-audit",
        "kit-modernize",
        "kit-simplify-review",
        "kit-refactor",
        "kit-consistency",
    ):
        assert f".apm/skills/{skill}/SKILL.md" in files
    instruction = "kit-readability.instructions.md"
    assert (
        files[f".apm/instructions/{instruction}"]
        == (PACKAGES / "shared" / ".apm" / "instructions" / instruction).read_bytes()
    )

    session = service.compose(
        snapshot, "workflows", (), (), skills=("kit-codebase-audit",)
    )
    assert not any(
        item.relative_path.startswith(".apm/prompts/") for item in session.files
    )
