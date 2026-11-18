"""Finite starter selections preserve opt-in bundles and discovery budgets."""

from __future__ import annotations

from itertools import product
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_kit.application.catalog import CatalogService
from agent_kit.infrastructure.catalog import FileCatalogAdapter

if TYPE_CHECKING:
    from agent_kit.core.models import CatalogSnapshot

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = _ROOT / "packages/starter/template"
_API_ONLY = "{% if service == 'api' %}"
_SETTINGS_SOURCES = {
    "{% if service == 'api' %}.env.example{% endif %}.jinja",
    *(
        f"{{% if service == 'api' %}}.env.{stage}.example{{% endif %}}.jinja"
        for stage in ("dev", "test", "staging", "prod")
    ),
    "{% if service == 'api' %}src{% endif %}/app/settings.py.jinja",
    "{% if service == 'api' %}tests{% endif %}/test_settings.py.jinja",
}
_BASE_PROFILES = {
    "toolkit": {"extends": [], "bundles": ["toolkit", "shared"]},
    "shared": {"extends": [], "bundles": ["shared"]},
    "backend": {"extends": ["shared"], "bundles": ["backend"]},
    "frontend": {"extends": ["shared"], "bundles": ["frontend"]},
    "fullstack": {"extends": ["backend", "frontend"], "bundles": ["coordination"]},
    "iac": {"extends": ["shared"], "bundles": ["iac"]},
    "workflows": {"extends": ["shared"], "bundles": ["workflows"]},
    "ai": {"extends": ["backend"], "bundles": ["ai"]},
    "terraform": {"extends": ["iac"], "bundles": ["terraform"]},
    "bicep": {"extends": ["iac"], "bundles": ["bicep"]},
    "remote-access": {"extends": ["iac"], "bundles": ["remote-access"]},
    "temporal": {"extends": ["backend"], "bundles": ["temporal"]},
    "identity": {"extends": ["shared"], "bundles": ["identity"]},
}
_STARTERS = {
    "starter-library": ("shared", "workflows"),
    **{
        "-".join((f"starter-{kind}", *filter(None, (ai, identity, iac)))): (
            kind,
            "workflows",
            *filter(None, (ai, identity, iac)),
        )
        for kind in ("backend", "frontend", "fullstack")
        for ai, identity, iac in product(
            ("",) if kind == "frontend" else ("", "ai"),
            ("", "identity"),
            ("", "bicep", "terraform"),
        )
    },
}
_STACK_BUNDLES = {
    "shared": {"shared"},
    "backend": {"shared", "backend"},
    "frontend": {"shared", "frontend"},
    "fullstack": {"shared", "backend", "frontend", "coordination"},
}
_OPTIONAL_BUNDLES = {
    "ai",
    "identity",
    "bicep",
    "terraform",
    "temporal",
    "remote-access",
}


@pytest.fixture(scope="module")
def snapshot() -> CatalogSnapshot:
    return FileCatalogAdapter().load(_ROOT)


def test_exact_finite_starter_mapping_preserves_base_profiles(
    snapshot: CatalogSnapshot,
) -> None:
    """Only the 31 approved combinations extend the existing base catalog."""
    catalog = snapshot.catalog
    assert isinstance(catalog, dict)
    expected = {
        **_BASE_PROFILES,
        **{
            name: {"extends": list(parents), "bundles": []}
            for name, parents in _STARTERS.items()
        },
    }

    assert len(_STARTERS) == 31
    assert catalog["profiles"] == expected


@pytest.mark.parametrize(("name", "parents"), _STARTERS.items(), ids=_STARTERS)
def test_starter_composes_only_selected_bundles_and_mcp(
    snapshot: CatalogSnapshot, name: str, parents: tuple[str, ...]
) -> None:
    """Pure composition exposes no toolkit, implicit identity, or cloud tools."""
    plan = CatalogService().compose(snapshot, name, (), ())
    features = set(parents[2:])
    expected = _STACK_BUNDLES[parents[0]] | {"workflows"} | features
    if features & {"bicep", "terraform"}:
        expected.add("iac")

    assert set(plan.bundles) == expected
    assert set(plan.bundles) & _OPTIONAL_BUNDLES == features
    source_paths = dict(plan.source_paths)
    assert all(source_paths[bundle].startswith("packages/") for bundle in plan.bundles)
    files = {item.relative_path: item.content for item in plan.files}
    selection = json.loads(files[".apm/selection.json"])
    assert selection["description_chars"] <= 6500
    manifest = json.loads(files["apm.yml"])
    mcp_names = {item["name"] for item in manifest["dependencies"].get("mcp", [])}
    expected_optional_mcp = {
        server
        for feature, server in (
            ("bicep", "azure"),
            ("terraform", "terraform"),
            ("ai", "langfuse-docs"),
        )
        if feature in features
    }
    assert (
        mcp_names
        & {
            "azure",
            "terraform",
            "langfuse-docs",
            "temporal-docs",
        }
        == expected_optional_mcp
    )


def test_every_catalog_profile_fits_unchanged_discovery_budgets(
    snapshot: CatalogSnapshot,
) -> None:
    """Count all inherited skill descriptions through the production service."""
    catalog = snapshot.catalog
    assert isinstance(catalog, dict)
    assert catalog["budgets"] == {
        "policy_lines": 120,
        "skill_body_lines": 300,
        "description_chars": 350,
        "profile_description_chars": 6500,
    }
    report = CatalogService().validate(snapshot)
    assert report.valid, report.findings
    summaries = {item.profile: item for item in report.profiles}
    assert summaries.keys() == _BASE_PROFILES.keys() | _STARTERS.keys()
    for summary in summaries.values():
        assert 0 < summary.description_chars <= 6500, summary
        assert dict(summary.limits)["profile_description_chars"] == 6500


def test_settings_layer_sources_render_only_for_the_api_service() -> None:
    """The typed settings layer is opt-in scaffold, never part of the foundation."""
    sources = {
        path.relative_to(_TEMPLATE).as_posix()
        for path in _TEMPLATE.rglob("*")
        if path.is_file() and ("settings" in path.name or ".env" in path.name)
    }

    assert sources == _SETTINGS_SOURCES
    assert all(source.startswith(_API_ONLY) for source in sources)
