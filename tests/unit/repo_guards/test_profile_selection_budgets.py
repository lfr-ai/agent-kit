"""Supported profile and feature combinations stay within the discovery budget."""

import json
from pathlib import Path

import pytest

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

_ROOT = Path(__file__).resolve().parents[3]
_TOOL_SKILLS = {
    "terraform": "kit-terraform-validation",
    "bicep": "kit-azure-validation",
    "remote-access": "kit-remote-access",
}
# Combinations documented in README, CI and the APM smoke matrix. A user picks
# one IaC tool, so every single-tool and the two-tool pairing must fit.
_SUPPORTED = (
    ("fullstack", ()),
    ("fullstack", ("iac",)),
    ("fullstack", ("terraform",)),
    ("fullstack", ("bicep",)),
    ("fullstack", ("remote-access",)),
    ("fullstack", ("terraform", "bicep")),
    ("fullstack", ("ai",)),
    ("fullstack", ("workflows",)),
    ("ai", ("terraform", "bicep", "remote-access")),
    ("terraform", ()),
    ("bicep", ()),
)


def _selection(profile: str, features: tuple[str, ...]) -> dict[str, object]:
    snapshot = FileCatalogAdapter().load(_ROOT)
    plan = CatalogService().compose(snapshot, profile, features, ("copilot",))
    files = {item.relative_path: item.content for item in plan.files}
    selection = json.loads(files[".apm/selection.json"])
    assert isinstance(selection, dict)
    return selection


@pytest.mark.parametrize(("profile", "features"), _SUPPORTED, ids=str)
def test_supported_combination_composes_within_budget(
    profile: str, features: tuple[str, ...]
) -> None:
    """Composition rejects an over-budget selection, so composing proves the fit."""
    selection = _selection(profile, features)
    catalog = json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))

    assert isinstance(selection["description_chars"], int)
    assert (
        selection["description_chars"]
        <= catalog["budgets"]["profile_description_chars"]
    )


def test_cloud_tool_skills_load_only_with_their_feature() -> None:
    """The infrastructure core never pays discovery cost for an unused tool."""
    core = _selection("fullstack", ("iac",))["skills"]
    assert isinstance(core, list)
    assert not set(_TOOL_SKILLS.values()) & set(core)
    for feature, skill in _TOOL_SKILLS.items():
        selected = _selection("iac", (feature,))["skills"]
        assert isinstance(selected, list)
        assert skill in selected
        others = set(_TOOL_SKILLS.values()) - {skill}
        assert not others & set(selected)
