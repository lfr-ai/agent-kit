"""Shared temporary source-tree fixtures and directory-based suite markers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SUITES = ("unit", "property", "integration")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark each test with the suite named by its top-level tests/ directory."""
    root = Path(__file__).parent
    for item in items:
        suite = item.path.relative_to(root).parts[0]
        if suite in _SUITES and item.get_closest_marker(suite) is None:
            item.add_marker(suite)


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    """Create a complete, isolated Agent Kit source tree."""
    root = tmp_path / "kit"
    root.mkdir()
    catalog = {
        "schema_version": 1,
        "version": "0.1.0",
        "supported_runtimes": ["copilot", "claude"],
        "budgets": {
            "policy_lines": 120,
            "skill_body_lines": 300,
            "description_chars": 350,
            "profile_description_chars": 6500,
        },
        "bundles": {
            "toolkit": {"path": ".", "kind": "project"},
            "shared": {"path": "packages/shared", "kind": "portable"},
            "backend": {"path": "packages/backend", "kind": "portable"},
            "frontend": {"path": "packages/frontend", "kind": "portable"},
            "iac": {"path": "packages/iac", "kind": "portable"},
        },
        "profiles": {
            "toolkit": {"extends": [], "bundles": ["toolkit", "shared"]},
            "shared": {"extends": [], "bundles": ["shared"]},
            "backend": {"extends": ["shared"], "bundles": ["backend"]},
            "frontend": {"extends": ["shared"], "bundles": ["frontend"]},
            "fullstack": {"extends": ["backend", "frontend"], "bundles": []},
            "iac": {"extends": ["shared"], "bundles": ["iac"]},
        },
    }
    (root / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    (root / "apm-policy.yml").write_text(
        """name: Agent Kit source and dependency policy
version: "1.0.0"
enforcement: block
fetch_failure: block
dependencies:
  allow: []
mcp:
  allow: []
  self_defined: deny
  trust_transitive: false
manifest:
  required_fields:
    - name
    - version
    - includes
    - license
  require_explicit_includes: true
  scripts: deny
executables:
  deny_all: true
security:
  integrity:
    require_hashes: true
  audit:
    fail_on_drift: true
""",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text("# Source policy\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT License\nSynthetic fixture\n", encoding="utf-8")
    (root / "llms.txt").write_text(
        "# Index\n\n[Policy](apm-policy.yml)\n", encoding="utf-8"
    )

    bundles = {
        "toolkit": (".", "project"),
        "shared": ("packages/shared", "portable"),
        "backend": ("packages/backend", "portable"),
        "frontend": ("packages/frontend", "portable"),
        "iac": ("packages/iac", "portable"),
    }
    for name, (relative, _kind) in bundles.items():
        bundle_root = root / relative
        apm_root = bundle_root / ".apm"
        instruction_dir = apm_root / "instructions"
        skill_dir = apm_root / "skills" / f"kit-{name}"
        instruction_dir.mkdir(parents=True)
        skill_dir.mkdir(parents=True)
        manifest = {
            "name": f"agent-kit-{name}",
            "version": "0.1.0",
            "description": f"{name} source bundle",
            "targets": ["copilot", "claude"],
            "includes": [".apm/instructions/", ".apm/skills/"],
            "dependencies": {},
            "executables": {},
            "license": "MIT",
        }
        (bundle_root / "apm.yml").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (instruction_dir / f"kit-{name}.instructions.md").write_text(
            "---\n"
            f"description: Instructions for {name}.\n"
            'applyTo: "**/*.py"\n'
            "---\n\n"
            f"Use the {name} guidance.\n",
            encoding="utf-8",
        )
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: kit-{name}\n"
            f"description: Review {name} changes carefully.\n"
            "---\n\n"
            f"# {name.title()} review\n\n"
            "Check the relevant contract.\n",
            encoding="utf-8",
        )
    return root
