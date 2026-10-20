"""Portable prompt validation and delivery through project and session composition."""

import json
from pathlib import Path

import pytest

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_PROMPT = (
    "---\ndescription: Plan a backend change.\nagent: agent\n---\n\n"
    "Use [the backend skill](../skills/kit-backend/SKILL.md).\n"
)


def _add_prompt(root: Path, name: str, text: str = _PROMPT) -> Path:
    bundle = root / "packages/backend"
    manifest = json.loads((bundle / "apm.yml").read_text(encoding="utf-8"))
    if ".apm/prompts/" not in manifest["includes"]:
        manifest["includes"].append(".apm/prompts/")
        (bundle / "apm.yml").write_text(json.dumps(manifest), encoding="utf-8")
    path = bundle / ".apm/prompts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _codes(root: Path) -> set[str]:
    report = CatalogService().validate(FileCatalogAdapter().load(root))
    return {item.code for item in report.findings}


def test_valid_prompt_passes_and_ships_in_project_mode(source_root: Path) -> None:
    """A flat kit-prefixed prompt is validated and delivered with its profile."""
    _add_prompt(source_root, "kit-plan-backend.prompt.md")

    assert _codes(source_root) == set()
    plan = CatalogService().compose(
        FileCatalogAdapter().load(source_root), "backend", (), ()
    )
    paths = {item.relative_path for item in plan.files}
    assert ".apm/prompts/kit-plan-backend.prompt.md" in paths


def test_session_mode_omits_prompts(source_root: Path) -> None:
    """Narrow sessions never inherit project workflows that link omitted skills."""
    _add_prompt(source_root, "kit-plan-backend.prompt.md")

    plan = CatalogService().compose(
        FileCatalogAdapter().load(source_root),
        "backend",
        (),
        (),
        skills=("kit-shared",),
    )

    assert not any(
        item.relative_path.startswith(".apm/prompts/") for item in plan.files
    )


@pytest.mark.parametrize(
    ("name", "text", "code"),
    [
        ("plan.prompt.md", _PROMPT, "prompt.name"),
        ("kit-plan.md", _PROMPT, "prompt.name"),
        ("nested/kit-plan.prompt.md", _PROMPT, "prompt.name"),
        ("kit-plan.prompt.md", "No frontmatter.\n", "prompt.frontmatter"),
        (
            "kit-plan.prompt.md",
            "---\ndescription: Plan.\ntools: [edit]\n---\n\nBody.\n",
            "prompt.metadata",
        ),
        (
            "kit-plan.prompt.md",
            "---\nagent: agent\n---\n\nBody.\n",
            "prompt.description",
        ),
        (
            "kit-plan.prompt.md",
            f"---\ndescription: {'x' * 400}\n---\n\nBody.\n",
            "prompt.description",
        ),
        (
            "kit-plan.prompt.md",
            "---\ndescription: Plan.\n---\n\n[Missing](../skills/kit-nope/SKILL.md)\n",
            "links.missing",
        ),
    ],
)
def test_invalid_prompts_are_rejected(
    source_root: Path, name: str, text: str, code: str
) -> None:
    """Placement, naming, metadata, description budget, and links are enforced."""
    _add_prompt(source_root, name, text)

    assert code in _codes(source_root)


def test_prompt_names_are_unique_across_bundles(source_root: Path) -> None:
    """Two bundles cannot deliver the same slash command name."""
    _add_prompt(source_root, "kit-plan.prompt.md")
    shared = source_root / "packages/shared"
    manifest = json.loads((shared / "apm.yml").read_text(encoding="utf-8"))
    manifest["includes"].append(".apm/prompts/")
    (shared / "apm.yml").write_text(json.dumps(manifest), encoding="utf-8")
    (shared / ".apm/prompts").mkdir(parents=True)
    (shared / ".apm/prompts/kit-plan.prompt.md").write_text(
        "---\ndescription: Plan.\n---\n\nBody.\n", encoding="utf-8"
    )

    assert "prompt.duplicate" in _codes(source_root)
