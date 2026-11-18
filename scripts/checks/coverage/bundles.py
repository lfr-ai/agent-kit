"""Authored bundle identities and the replacement recorded for each original."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

from agent_kit.core.guards import is_json_object
from scripts.checks.coverage.inputs import read_json, unsafe_asset

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path

_FRONTMATTER_FENCES = 2  # split into empty prefix, metadata, and body
_SCRIPT_DISPOSITIONS = {
    "superseded-by-apm-owned-drift",
    "consumer-owned",
    "operator-owned",
    "excluded-copier",
}


@dataclass(frozen=True, kw_only=True, slots=True)
class _Bundles:
    """Capability identities discovered in every authored bundle."""

    skills: dict[str, Path]
    instructions: set[str]
    roles: set[str]
    prompts: set[str]


def _collect_skills(root: Path, bundle: Path, skills: dict[str, Path]) -> list[str]:
    """Record each bundle skill identity and report unreadable metadata.

    Args:
        root (Path): Repository root used to relativize failure paths.
        bundle (Path): Authored bundle directory to scan.
        skills (dict[str, Path]): Collector mapping skill name to its ``SKILL.md``.

    Returns:
        list[str]: One failure per skill whose metadata is unreadable or unnamed.
    """
    failures: list[str] = []
    for path in bundle.rglob("SKILL.md"):
        parts = path.read_text(encoding="utf-8").split("---", _FRONTMATTER_FENCES)
        if len(parts) != _FRONTMATTER_FENCES + 1:
            failures.append(f"{path.relative_to(root)}: invalid skill metadata")
            continue
        metadata = yaml.safe_load(parts[1])
        name = metadata.get("name") if is_json_object(metadata) else None
        if not isinstance(name, str):
            failures.append(f"{path.relative_to(root)}: missing skill identity")
            continue
        skills[name] = path
    return failures


def _collect_roles(root: Path, bundle: Path, roles: set[str]) -> list[str]:
    """Record native role identities and report invalid or duplicate roles.

    Args:
        root (Path): Repository root used to relativize failure paths.
        bundle (Path): Authored bundle directory to scan.
        roles (set[str]): Collector of role identifiers seen so far.

    Returns:
        list[str]: One failure per invalid role asset or duplicate role.
    """
    failures: list[str] = []
    for path in bundle.rglob("agents.json"):
        asset = read_json(path)
        entries = asset.get("roles") if is_json_object(asset) else None
        if not isinstance(entries, list):
            failures.append(f"{path.relative_to(root)}: invalid native role asset")
            continue
        for role in entries:
            identifier = role.get("id") if is_json_object(role) else None
            if not isinstance(identifier, str):
                continue
            if identifier in roles:
                failures.append(f"duplicate role {identifier}")
            roles.add(identifier)
    return failures


def _parse_template(path: Path) -> None:
    """Parse a source template with the parser for its rendered suffix."""
    name = path.name.removesuffix(".template")
    if name.endswith(".json"):
        read_json(path)
    elif name.endswith((".yaml", ".yml")):
        yaml.safe_load(path.read_text(encoding="utf-8"))
    elif name.endswith(".py"):
        ast.parse(path.read_text(encoding="utf-8"))


def _template_failures(root: Path, bundle: Path) -> list[str]:
    """Report source templates whose rendered syntax cannot be parsed.

    Args:
        root (Path): Repository root used to relativize failure paths.
        bundle (Path): Authored bundle directory to scan.

    Returns:
        list[str]: One failure per template with invalid syntax.
    """
    failures: list[str] = []
    for path in bundle.rglob("*.template"):
        try:
            _parse_template(path)
        except (ValueError, SyntaxError, yaml.YAMLError):
            failures.append(f"{path.relative_to(root)}: invalid source template syntax")
    return failures


def scan_bundles(root: Path) -> tuple[_Bundles, list[str]]:
    """Collect capability identities from the root and every package bundle.

    The result pairs the identities with the metadata, role and template failures
    found while scanning.
    """
    bundles = _Bundles(skills={}, instructions=set(), roles=set(), prompts=set())
    failures: list[str] = []
    for bundle in [root / ".apm", *sorted((root / "packages").glob("*/.apm"))]:
        failures.extend(_collect_skills(root, bundle, bundles.skills))
        bundles.instructions.update(
            path.name.removesuffix(".instructions.md")
            for path in bundle.rglob("*.instructions.md")
        )
        bundles.prompts.update(
            path.name.removesuffix(".prompt.md")
            for path in bundle.glob("prompts/*.prompt.md")
        )
        failures.extend(_collect_roles(root, bundle, bundles.roles))
        failures.extend(_template_failures(root, bundle))
    return bundles, failures


def _unresolved(
    section: dict[str, object], known: Collection[str], label: str
) -> list[str]:
    """Report entries whose recorded replacement is not a known identity.

    Args:
        section (dict[str, object]): Original identity mapped to its decoded replacement.
        known (Collection[str]): Replacement identities that exist in the bundles.
        label (str): Replacement kind named in each failure message.

    Returns:
        list[str]: One failure per entry whose replacement is not a known string.
    """
    return [
        f"missing {label} replacement {name}: {target}"
        for name, target in section.items()
        if not isinstance(target, str) or target not in known
    ]


def _skill_replacement_failures(
    skills: dict[str, object], exclusions: dict[str, object], available: set[str]
) -> list[str]:
    """Require a replacement or an exclusion rationale for every skill.

    Args:
        skills (dict[str, object]): Original skill mapped to its replacement, or ``None``.
        exclusions (dict[str, object]): Excluded skill mapped to its rationale.
        available (set[str]): Skill names that exist in the bundles.

    Returns:
        list[str]: One failure per skill with neither a replacement nor a rationale.
    """
    failures: list[str] = []
    for name, target in skills.items():
        if target is None:
            if not exclusions.get(name):
                failures.append(f"missing rationale for excluded {name}")
        elif not isinstance(target, str) or target not in available:
            failures.append(f"missing skill replacement {name}: {target}")
    return failures


def _prompt_file_failures(
    prompt_files: object, commands: dict[str, object], prompts: set[str]
) -> list[str]:
    """Require native prompt replacements for recorded original commands.

    Args:
        prompt_files (object): Decoded ``prompt_files`` value.
        commands (dict[str, object]): Recorded original commands.
        prompts (set[str]): Native prompt names that exist in the bundles.

    Returns:
        list[str]: One failure per mapping that is unknown or has no native prompt.
    """
    if not is_json_object(prompt_files):
        return ["prompt_files must map original commands to prompts"]
    failures: list[str] = []
    for name, target in prompt_files.items():
        if name not in commands:
            failures.append(f"prompt file mapping names no original command: {name}")
        elif not isinstance(target, str) or target not in prompts:
            failures.append(f"missing native prompt replacement {name}: {target}")
    return failures


def _script_failures(root: Path, scripts: dict[str, object]) -> list[str]:
    """Require a known disposition or a safe Python replacement per script.

    Args:
        root (Path): Repository root the replacement scripts must stay inside.
        scripts (dict[str, object]): Original script mapped to its decoded disposition.

    Returns:
        list[str]: One failure per script with an unknown or unsafe disposition.
    """
    return [
        f"missing or unsafe script disposition {name}: {target}"
        for name, target in scripts.items()
        if not (isinstance(target, str) and target in _SCRIPT_DISPOSITIONS)
        and (
            unsafe_asset(root, target)
            or not isinstance(target, str)
            or not target.endswith(".py")
        )
    ]


def replacement_failures(
    root: Path,
    sections: dict[str, dict[str, object]],
    *,
    exclusions: dict[str, object],
    prompt_files: object,
    bundles: _Bundles,
) -> list[str]:
    """Check every recorded replacement against the discovered bundles.

    Args:
        root (Path): Repository root passed through to script checks.
        sections (dict[str, dict[str, object]]): Validated baseline sections.
        exclusions (dict[str, object]): Excluded skill mapped to its rationale.
        prompt_files (object): Decoded ``prompt_files`` value.
        bundles (_Bundles): Identities discovered in every authored bundle.

    Returns:
        list[str]: One failure per missing replacement across all sections.
    """
    failures = _skill_replacement_failures(
        sections["skills"], exclusions, set(bundles.skills)
    )
    failures.extend(
        _unresolved(sections["instructions"], bundles.instructions, "instruction")
    )
    failures.extend(
        _unresolved(sections["prompts"], bundles.skills, "command procedure")
    )
    failures.extend(
        _prompt_file_failures(prompt_files, sections["prompts"], bundles.prompts)
    )
    failures.extend(_unresolved(sections["agents"], bundles.roles, "native role"))
    failures.extend(_script_failures(root, sections["scripts"]))
    return failures
