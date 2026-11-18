"""Community files, intake labels, issue forms, and Dependabot contracts."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import yaml

from agent_kit.core.guards import is_json_object
from scripts.checks.governance.inputs import child_list, child_value, yaml_mapping

if TYPE_CHECKING:
    from pathlib import Path

_DOCS = (
    "GOVERNANCE.md",
    "SUPPORT.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
)
_DEPENDABOT_VERSION = 2
_DEPENDABOT_ECOSYSTEMS = frozenset(
    {"uv", "bun", "docker", "github-actions", "pre-commit", "devcontainers"}
)


def _labels(root: Path) -> set[str] | None:
    """Return unique label names from the inventory, or ``None`` when it is invalid."""
    try:
        raw: object = yaml.safe_load(
            (root / ".github/labels.yml").read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, list):
        return None
    names: set[str] = set()
    for item in raw:
        if (
            not is_json_object(item)
            or set(item) != {"name", "description", "color"}
            or not all(isinstance(value, str) for value in item.values())
            or re.fullmatch(r"[0-9a-f]{6}", str(item["color"])) is None
            or item["name"] in names
        ):
            return None
        names.add(str(item["name"]))
    return names


def _issue_config_findings(root: Path, repository: str | None) -> list[str]:
    """Require disabled blank issues and a private security route.

    Args:
        root (Path): Repository root that holds ``.github/ISSUE_TEMPLATE``.
        repository (str | None): Approved ``owner/name`` coordinate, if any.

    Returns:
        list[str]: Findings; empty when the issue config passes.
    """
    findings: list[str] = []
    config = yaml_mapping(root / ".github/ISSUE_TEMPLATE/config.yml")
    if config is None or config.get("blank_issues_enabled") is not False:
        findings.append("issue config: blank issues must be disabled")
    urls = [
        url
        for item in child_list(config, "contact_links")
        if is_json_object(item) and isinstance(url := item.get("url"), str)
    ]
    security_routes = [
        url
        for url in urls
        if url.endswith(("/security/advisories/new", "/blob/main/SECURITY.md"))
    ]
    if not security_routes:
        findings.append(
            "issue config: private security reporting or SECURITY.md instructions are required"
        )
    elif repository is not None and not all(
        url.startswith(f"https://github.com/{repository}/") for url in urls
    ):
        findings.append("issue config: contact links must use the approved repository")
    return findings


def _issue_form_findings(root: Path, labels: set[str]) -> list[str]:
    """Require issue forms to apply only declared labels.

    Args:
        root (Path): Repository root that holds ``.github/ISSUE_TEMPLATE``.
        labels (set[str]): Label names declared in ``labels.yml``.

    Returns:
        list[str]: Findings; empty when every form uses declared labels.
    """
    findings: list[str] = []
    for form in ("bug.yml", "capability-change.yml", "feature.yml"):
        data = yaml_mapping(root / ".github/ISSUE_TEMPLATE" / form)
        form_labels = child_list(data, "labels")
        if not form_labels:
            findings.append(f"{form}: issue form labels are required")
            continue
        findings.extend(
            f"{form}: label {label!r} is not in labels.yml"
            for label in form_labels
            if label not in labels
        )
    return findings


def _release_labels(changelog: object) -> set[str]:
    """Collect labels named by release-note categories and exclusions."""
    used = {
        str(label) for label in child_list(child_value(changelog, "exclude"), "labels")
    }
    for category in child_list(changelog, "categories"):
        used.update(str(label) for label in child_list(category, "labels"))
    return used


def intake(root: Path, repository: str | None) -> list[str]:
    """Require a private security route and valid labels without claiming host state.

    Args:
        root (Path): Repository root that holds the ``.github`` intake files.
        repository (str | None): Approved ``owner/name`` coordinate, if any.

    Returns:
        list[str]: Findings; empty when intake configuration passes.
    """
    labels = _labels(root)
    if labels is None:
        return ["labels.yml: must list unique name, description, and hex color"]
    findings = _issue_config_findings(root, repository)
    findings.extend(_issue_form_findings(root, labels))
    release = yaml_mapping(root / ".github/release.yml")
    used = _release_labels(child_value(release, "changelog"))
    findings.extend(
        f"release.yml: label {label!r} is not in labels.yml"
        for label in sorted(used - {"*"} - labels)
    )
    return findings


def dependabot(root: Path) -> list[str]:
    """Require Dependabot for every manifest kind, using only declared labels."""
    config = yaml_mapping(root / ".github/dependabot.yml")
    updates = child_value(config, "updates")
    if (
        config is None
        or config.get("version") != _DEPENDABOT_VERSION
        or not isinstance(updates, list)
    ):
        return [
            f"dependabot.yml: version {_DEPENDABOT_VERSION} with an updates list is required"
        ]
    entries = [item for item in updates if is_json_object(item)]
    ecosystems = {item.get("package-ecosystem") for item in entries}
    findings = [
        f"dependabot.yml: {ecosystem} updates are required"
        for ecosystem in sorted(_DEPENDABOT_ECOSYSTEMS - ecosystems)
    ]
    labels = _labels(root) or set()
    used = {str(label) for item in entries for label in child_list(item, "labels")}
    findings.extend(
        f"dependabot.yml: label {label!r} is not in labels.yml"
        for label in sorted(used - labels)
    )
    return findings


def community_file_findings(root: Path) -> list[str]:
    """Report each required community document missing under ``root``."""
    return [
        f"missing community file: {name}"
        for name in _DOCS
        if not (root / name).is_file()
    ]
