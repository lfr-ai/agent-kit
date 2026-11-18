"""Consumer APM policy template: Agent Kit sources and reviewed MCP servers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from agent_kit.core.guards import is_json_object, is_str_list

if TYPE_CHECKING:
    from pathlib import Path

_PROFILE_DEPENDENCY_SOURCES = {
    "lfr-ai/agent-kit/profiles/*",
    "lfr-ai/agent-kit/packages/*",
}


def policy_failures(root: Path) -> list[str]:
    """Require a narrow Agent Kit source allowlist and reviewed MCP policy."""
    template = root / ".apm/skills/kit-apm-adopt/assets/apm-policy.yml.template"
    policy = yaml.safe_load(template.read_text(encoding="utf-8"))
    dependencies = policy.get("dependencies") if is_json_object(policy) else None
    sources = dependencies.get("allow") if is_json_object(dependencies) else None
    if not is_str_list(sources) or set(sources) != _PROFILE_DEPENDENCY_SOURCES:
        return [
            "consumer APM policy template must allow Agent Kit profiles and source packages"
        ]
    mcp_policy = policy.get("mcp") if is_json_object(policy) else None
    if (
        not is_json_object(policy)
        or not is_json_object(mcp_policy)
        or not mcp_policy.get("allow")
        or mcp_policy.get("self_defined") != "allow"
        or mcp_policy.get("trust_transitive") is not False
        or "executables" in policy
    ):
        return ["consumer APM policy template must keep MCP named and reviewed"]
    return []
