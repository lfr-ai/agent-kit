"""Check capability completeness, resource syntax, and editor task ownership."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

from agent_kit.core.guards import is_int, is_json_object
from scripts.checks.coverage.baseline import (
    COVERAGE_FIELDS,
    asset_failures,
    baseline_identity_failures,
    baseline_sections,
    live_source_failures,
    read_asset_index,
)
from scripts.checks.coverage.bundles import replacement_failures, scan_bundles
from scripts.checks.coverage.editor import editor_task_failures
from scripts.checks.coverage.inputs import read_json
from scripts.checks.coverage.mcp import active_mcp_manifests, integration_failures
from scripts.checks.coverage.policy import policy_failures
from scripts.checks.resources import check as check_resources

_ROOT = Path(__file__).resolve().parents[3]


def check(root: Path, *, source_root: Path | None = None) -> list[str]:
    """Verify every promised replacement exists and inactive sources remain valid.

    Args:
        root (Path): Repository root to verify.
        source_root (Path | None): Optional original checkout to compare inventories with.

    Returns:
        list[str]: Human-readable failures; empty when coverage is complete.
    """
    raw = read_json(root / ".agents/agentic-setup/coverage.json")
    if (
        not is_json_object(raw)
        or set(raw) != COVERAGE_FIELDS
        or not is_int(raw.get("schema_version"))
        or raw.get("schema_version") != 1
    ):
        return ["coverage schema is invalid"]
    sections, failures = baseline_sections(raw)
    if failures:
        return failures
    exclusions = raw["exclusions"]
    if not is_json_object(exclusions):
        return [
            "coverage exclusions must match exactly the deliberately unmigrated skills"
        ]
    identity_failures = baseline_identity_failures(sections, exclusions)
    if identity_failures:
        return identity_failures
    assets = read_asset_index(root)
    if assets is None:
        return ["asset index is invalid"]
    failures = asset_failures(root, assets, sections["assets"])
    bundles, bundle_failures = scan_bundles(root)
    failures.extend(bundle_failures)
    failures.extend(
        replacement_failures(
            root,
            sections,
            exclusions=exclusions,
            prompt_files=raw["prompt_files"],
            bundles=bundles,
        )
    )
    failures.extend(integration_failures(root, sections))
    failures.extend(live_source_failures(source_root, sections))
    failures.extend(editor_task_failures(root))
    failures.extend(active_mcp_manifests(root))
    failures.extend(policy_failures(root))
    failures.extend(check_resources(root))
    return failures


def main() -> int:
    """Print coverage failures without modifying runtime projections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        failures = check(_ROOT, source_root=args.source_root)
    except (OSError, ValueError, yaml.YAMLError) as error:
        sys.stderr.write(f"Capability coverage inputs cannot be parsed: {error}\n")
        return 1
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write(
        "Original capability inventory, replacements, templates, and editor contracts passed.\n"
    )
    return 0
