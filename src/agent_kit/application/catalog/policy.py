"""Own the released source policy contract and its validation.

The policy is a checked baseline that composition copies verbatim; it is not
runtime authorization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from agent_kit.application.catalog.errors import CompositionError, CompositionIssue
from agent_kit.application.catalog.schema import exact_mapping
from agent_kit.application.findings import add_finding
from agent_kit.core.guards import is_json_object

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import CatalogSnapshot, Finding

MCP_ALLOWED: Final[tuple[str, ...]] = (
    "azure",
    "chrome-devtools",
    "context7",
    "github",
    "langfuse-docs",
    "microsoft-learn",
    "playwright",
    "postman",
    "shadcn",
    "storybook",
    "temporal-docs",
    "terraform",
)
_SECURITY_POLICY = {
    "integrity": {"require_hashes": True},
    "audit": {"fail_on_drift": True},
}
POLICY: Final[JSONObject] = {
    "name": "Agent Kit source and dependency policy",
    "version": "1.0.0",
    "enforcement": "block",
    "fetch_failure": "block",
    "dependencies": {"allow": []},
    "mcp": {
        "allow": list(MCP_ALLOWED),
        "self_defined": "allow",
        "trust_transitive": False,
        "transport": {"allow": ["http", "stdio"]},
    },
    "manifest": {
        "required_fields": ["name", "version", "includes", "license"],
        "require_explicit_includes": True,
        "scripts": "deny",
    },
    "security": _SECURITY_POLICY,
}
_POLICY_SCALARS = ("name", "version", "enforcement", "fetch_failure")
_POLICY_SECTIONS = {
    "dependencies": {"allow"},
    "mcp": {"allow", "self_defined", "trust_transitive", "transport"},
    "manifest": {"required_fields", "require_explicit_includes", "scripts"},
    "security": {"integrity", "audit"},
}


def same_value(actual: object, expected: object) -> bool:
    """Compare nested policy values without Python bool/integer equivalence."""
    if type(actual) is not type(expected):
        return False
    if is_json_object(actual) and is_json_object(expected):
        return actual.keys() == expected.keys() and all(
            same_value(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            same_value(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return actual == expected


def _policy_value_finding(findings: list[Finding], key: str, path: str) -> None:
    """Report one policy value that differs from the released contract."""
    add_finding(findings, "policy.value", f"unsupported policy value for '{key}'", path)


def _policy_scalars_valid(top: JSONObject, path: str, findings: list[Finding]) -> bool:
    """Compare top-level scalar policy values with the released contract."""
    valid = True
    for key in _POLICY_SCALARS:
        if top.get(key) != POLICY[key]:
            _policy_value_finding(findings, key, path)
            valid = False
    return valid


def _security_policy_valid(
    security: JSONObject, path: str, findings: list[Finding]
) -> bool:
    """Require the exact nested integrity and audit ``security`` settings."""
    valid = True
    for child, expected in _SECURITY_POLICY.items():
        nested = exact_mapping(
            security.get(child), set(expected), f"{path}:security:{child}", findings
        )
        if nested is None:
            valid = False
        elif not same_value(nested, expected):
            _policy_value_finding(findings, child, path)
            valid = False
    return valid


def _policy_section_valid(
    top: JSONObject, key: str, path: str, findings: list[Finding]
) -> bool:
    """Require one nested policy section to match its released shape and values."""
    nested = exact_mapping(
        top.get(key), _POLICY_SECTIONS[key], f"{path}:{key}", findings
    )
    if nested is None:
        return False
    if key == "security":
        return _security_policy_valid(nested, path, findings)
    if same_value(nested, POLICY.get(key)):
        return True
    _policy_value_finding(findings, key, path)
    return False


def policy_mapping(value: object, path: str, findings: list[Finding]) -> bool:
    """Require the exact released strict policy contract."""
    top = exact_mapping(value, set(POLICY), path, findings)
    if top is None:
        return False
    results = [_policy_scalars_valid(top, path, findings)]
    results.extend(
        _policy_section_valid(top, key, path, findings) for key in _POLICY_SECTIONS
    )
    return all(results) and same_value(top, POLICY)


def check_policy(snapshot: CatalogSnapshot, findings: list[Finding]) -> None:
    """Require a readable policy document with the strict released contract."""
    if snapshot.policy_error or snapshot.policy_document is None:
        add_finding(
            findings,
            "policy.read",
            "apm-policy.yml is missing or invalid",
            "apm-policy.yml",
        )
    else:
        policy_mapping(snapshot.policy, "apm-policy.yml", findings)


def policy_line_count(snapshot: CatalogSnapshot) -> int:
    """Count readable policy lines, treating an unreadable policy as empty."""
    document = snapshot.policy_document
    if document is None or document.text is None:
        return 0
    return len(document.text.splitlines())


def policy_content(snapshot: CatalogSnapshot) -> bytes:
    """Return readable source policy bytes; raise ``CompositionError`` otherwise."""
    policy_document = snapshot.policy_document
    if policy_document is None or policy_document.text is None:
        raise CompositionError(CompositionIssue.POLICY_UNAVAILABLE)
    return policy_document.content
