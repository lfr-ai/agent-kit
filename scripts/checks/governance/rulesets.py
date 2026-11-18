"""Importable rulesets for the default branch and release tags."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from agent_kit.core.guards import is_int, is_json_object
from agent_kit.infrastructure.documents import load_json
from scripts.checks.governance.inputs import child_value

if TYPE_CHECKING:
    from pathlib import Path


class _RulesetContract(TypedDict):
    """Fixed target, scope, and protection rules of one importable ruleset."""

    target: str
    include: list[str]
    required: frozenset[str]


_RULESET_RULES = {
    "main.json": _RulesetContract(
        target="branch",
        include=["~DEFAULT_BRANCH"],
        required=frozenset(
            {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
        ),
    ),
    "release-tags.json": _RulesetContract(
        target="tag",
        include=["refs/tags/v*"],
        required=frozenset({"deletion", "non_fast_forward", "update"}),
    ),
}
_REQUIRED_CHECK = "Required toolkit checks"
_REQUIRED_APPROVALS = 1
# Pull-request-only bypass covers the entire main ruleset, including status checks,
# not just approval. It does not authorize direct pushes; agents use a write role.
_ADMIN_ROLE_ID = 5
_BYPASS_ACTORS = {
    "main.json": [
        {
            "actor_id": _ADMIN_ROLE_ID,
            "actor_type": "RepositoryRole",
            "bypass_mode": "pull_request",
        }
    ],
    "release-tags.json": [],
}
_PULL_REQUEST_GUARDS = (
    "dismiss_stale_reviews_on_push",
    "require_code_owner_review",
    "require_last_push_approval",
    "required_review_thread_resolution",
)


def _ruleset(root: Path, name: str) -> list[str]:
    """Validate an importable repository ruleset without claiming it is applied.

    Args:
        root (Path): Repository root that holds ``.github/rulesets``.
        name (str): Ruleset file name, a key of the reviewed contracts.

    Returns:
        list[str]: Scope, inventory, and parameter findings; empty when it passes.
    """
    expected = _RULESET_RULES[name]
    try:
        raw = load_json((root / ".github/rulesets" / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"rulesets/{name}: missing, invalid, or duplicate-key JSON"]
    if not is_json_object(raw):
        return [f"rulesets/{name}: ruleset must be a mapping"]
    findings = _ruleset_scope_findings(name, raw, expected)
    rules = raw.get("rules")
    entries = rules if isinstance(rules, list) else []
    typed: dict[str, object] = {
        kind: rule
        for rule in entries
        if is_json_object(rule) and isinstance(kind := rule.get("type"), str)
    }
    if len(typed) != len(entries) or set(typed) != expected["required"]:
        findings.append(
            f"rulesets/{name}: rule inventory must contain each reviewed type exactly once"
        )
    if name == "main.json":
        findings.extend(_main_ruleset_parameters(typed))
    return findings


def _ruleset_scope_findings(
    name: str, raw: dict[str, object], expected: _RulesetContract
) -> list[str]:
    """Require the fixed target, scope, enforcement, and reviewed bypass actors.

    Args:
        name (str): Ruleset file name used to prefix each finding.
        raw (dict[str, object]): Decoded ruleset document.
        expected (_RulesetContract): Reviewed target, include refs, and required rule types.

    Returns:
        list[str]: Scope and bypass findings; empty when both match the contract.
    """
    findings: list[str] = []
    ref_name = child_value(raw.get("conditions"), "ref_name")
    if (
        raw.get("target") != expected["target"]
        or raw.get("enforcement") != "active"
        or not is_json_object(ref_name)
        or ref_name.get("include") != expected["include"]
        or ref_name.get("exclude") != []
    ):
        findings.append(f"rulesets/{name}: target, scope, and enforcement are fixed")
    if raw.get("bypass_actors") != _BYPASS_ACTORS[name]:
        findings.append(f"rulesets/{name}: bypass actors require explicit review")
    return findings


def _review_parameter_findings(parameters: object) -> list[str]:
    """Require the reviewed positive approval count and all review guards."""
    if not is_json_object(parameters):
        return ["rulesets/main.json: review parameters are required"]
    findings: list[str] = []
    if not all(parameters.get(guard) is True for guard in _PULL_REQUEST_GUARDS):
        findings.append("rulesets/main.json: review guards must all be enabled")
    count = parameters.get("required_approving_review_count")
    if not is_int(count) or count != _REQUIRED_APPROVALS:
        findings.append(
            "rulesets/main.json: review count must remain the reviewed positive integer"
        )
    return findings


def _main_ruleset_parameters(rules: dict[str, object]) -> list[str]:
    """Check review and status-check parameters of the default-branch ruleset."""
    findings = _review_parameter_findings(
        child_value(rules.get("pull_request"), "parameters")
    )
    status_parameters = child_value(rules.get("required_status_checks"), "parameters")
    checks = child_value(status_parameters, "required_status_checks")
    if checks != [{"context": _REQUIRED_CHECK}]:
        findings.append(
            "rulesets/main.json: the stable required matrix summary is the only check"
        )
    if (
        not is_json_object(status_parameters)
        or status_parameters.get("strict_required_status_checks_policy") is not True
    ):
        findings.append("rulesets/main.json: required status checks must be strict")
    return findings


def ruleset_findings(root: Path) -> list[str]:
    """Validate every reviewed ruleset under ``root`` without claiming it is applied."""
    return [finding for name in _RULESET_RULES for finding in _ruleset(root, name)]
