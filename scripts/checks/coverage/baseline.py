"""Pinned original capability baseline, asset index, and live source comparison."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final

from agent_kit.core.guards import is_json_object
from agent_kit.core.primitives import NativeRuntime
from scripts.checks.coverage.inputs import read_json, unsafe_asset

if TYPE_CHECKING:
    from pathlib import Path

COVERAGE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "baseline",
        "skills",
        "exclusions",
        "instructions",
        "agents",
        "mcp",
        "hooks",
        "assets",
        "guard_migration",
        "prompts",
        "prompt_files",
        "scripts",
    }
)
_BASELINE_COUNTS = {
    "skills": 74,
    "instructions": 31,
    "agents": 24,
    "prompts": 24,
    "mcp": 11,
    "hooks": 3,
    "assets": 5,
    "scripts": 22,
}
_BASELINE_KEYS_SHA256 = (
    # This public digest fingerprints the sorted baseline keys, not a credential.
    "0432d97293e5305af867e9751112b432"  # pragma: allowlist secret
    # This literal continues the fixed public baseline digest.
    "f14766d79b35b3854ce0449959af4719"  # pragma: allowlist secret
)


def baseline_sections(
    raw: dict[str, object],
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Split ``raw`` baseline sections by count into ``(sections, failures)``.

    Sections map each name with its pinned entry count to its entries; failures
    hold one message per missing or miscounted section.
    """
    sections: dict[str, dict[str, object]] = {}
    failures: list[str] = []
    for name, count in _BASELINE_COUNTS.items():
        section = raw.get(name)
        if is_json_object(section) and len(section) == count:
            sections[name] = section
        else:
            failures.append(
                f"coverage baseline {name} must contain {count} unique entries"
            )
    return sections, failures


def baseline_identity_failures(
    sections: dict[str, dict[str, object]], exclusions: dict[str, object]
) -> list[str]:
    """Pin baseline identities and require exclusions for unmigrated skills.

    Args:
        sections (dict[str, dict[str, object]]): Validated baseline sections.
        exclusions (dict[str, object]): Validated ``exclusions`` mapping.

    Returns:
        list[str]: At most one failure; empty when identities and exclusions match.
    """
    baseline = {name: sorted(section) for name, section in sections.items()}
    digest = hashlib.sha256(
        json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if digest != _BASELINE_KEYS_SHA256:
        return [
            "coverage baseline identities differ from the source-verified inventory"
        ]
    unmigrated = {name for name, value in sections["skills"].items() if value is None}
    if set(exclusions) != unmigrated:
        return [
            "coverage exclusions must match exactly the deliberately unmigrated skills"
        ]
    return []


def read_asset_index(root: Path) -> dict[str, object] | None:
    """Return asset categories mapped to reference lists; ``None`` if malformed."""
    asset_index = read_json(root / ".agents/agentic-setup/assets.json")
    if not is_json_object(asset_index) or set(asset_index) != {
        "schema_version",
        "assets",
    }:
        return None
    assets = asset_index["assets"]
    return assets if is_json_object(assets) else None


def asset_failures(
    root: Path, assets: dict[str, object], baseline: dict[str, object]
) -> list[str]:
    """Require matching categories and safe, present asset references.

    Args:
        root (Path): Repository root the references must stay inside.
        assets (dict[str, object]): Asset category to decoded reference list.
        baseline (dict[str, object]): Baseline asset categories to compare against.

    Returns:
        list[str]: One failure per category or reference that is invalid.
    """
    failures: list[str] = []
    if set(assets) != set(baseline):
        failures.append("asset index and baseline asset categories differ")
    for category, paths in assets.items():
        if not isinstance(paths, list) or not paths:
            failures.append(f"{category}: asset references must be nonempty")
            continue
        failures.extend(
            f"{category}: missing or unsafe asset reference"
            for relative in paths
            if unsafe_asset(root, relative)
        )
    return failures


def _live_inventory(source_root: Path) -> dict[str, set[str]]:
    """Collect capability identities from the original source checkout.

    Sections ``skills``, ``instructions``, ``agents``, ``prompts`` and ``scripts``
    map to the identities found there.
    """
    copilot = NativeRuntime.COPILOT
    skills_root = source_root / ".agents/skills"
    prompts_root = source_root / copilot.prompt_directory
    return {
        "skills": {
            path.parent.relative_to(skills_root).as_posix()
            for path in skills_root.rglob("SKILL.md")
        },
        "instructions": {
            path.name.removesuffix(".instructions.md")
            for path in (source_root / ".github/instructions").glob("*.instructions.md")
        },
        "agents": {
            path.name.removesuffix(copilot.agent_suffix)
            for path in (source_root / copilot.agent_directory).rglob(
                f"*{copilot.agent_suffix}"
            )
        },
        "prompts": {
            path.relative_to(prompts_root)
            .as_posix()
            .removesuffix(copilot.prompt_suffix)
            for path in prompts_root.rglob(f"*{copilot.prompt_suffix}")
        },
        "scripts": {
            path.relative_to(skills_root).as_posix()
            for path in skills_root.rglob("scripts/*.py")
        },
    }


def live_source_failures(
    source_root: Path | None, sections: dict[str, dict[str, object]]
) -> list[str]:
    """Compare an optional original checkout with the recorded inventory.

    Args:
        source_root (Path | None): Original checkout to compare, or ``None`` to skip.
        sections (dict[str, dict[str, object]]): Validated baseline sections.

    Returns:
        list[str]: Per-section difference summary plus its unrecorded and stale names.
    """
    if source_root is None:
        return []
    failures: list[str] = []
    for name, actual in _live_inventory(source_root).items():
        recorded = set(sections[name])
        if actual == recorded:
            continue
        failures.append(
            f"live source {name} differs from the recorded coverage inventory"
        )
        if missing := actual - recorded:
            failures.append(f"unrecorded {name}: {', '.join(sorted(missing))}")
        if stale := recorded - actual:
            failures.append(f"stale {name}: {', '.join(sorted(stale))}")
    return failures
