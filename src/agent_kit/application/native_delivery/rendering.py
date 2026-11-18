"""Render validated native roles into runtime-owned agent adapters."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agent_kit.application.native_delivery.validation import (
    RoleKind,
    RoleTier,
    checked_runtimes,
    load_roles,
)
from agent_kit.core.primitives import FRONTMATTER_DELIMITER, NativeRuntime

if TYPE_CHECKING:
    from agent_kit.application.native_delivery.validation import NativeRole

_COPILOT_TOOLS = {
    RoleTier.VERIFIER: ("read", "search", "execute", "todo"),
    RoleTier.IMPLEMENTER: ("read", "search", "edit", "execute", "todo"),
    RoleTier.COORDINATOR: ("read", "search", "edit", "execute", "agent", "todo"),
}
_CLAUDE_TOOLS = {
    RoleTier.VERIFIER: ("Read", "Grep", "Glob", "Bash"),
    RoleTier.IMPLEMENTER: ("Read", "Grep", "Glob", "Edit", "Write", "Bash"),
    RoleTier.COORDINATOR: ("Read", "Grep", "Glob", "Edit", "Write", "Bash"),
}


def _yaml_string(value: str) -> str:
    """Quote a scalar using JSON syntax, which is also valid YAML."""
    return json.dumps(value, ensure_ascii=False)


def _copilot_metadata(role: NativeRole) -> str:
    """Render recognized Copilot agent frontmatter with bounded tool grants."""
    is_primary = role.kind is RoleKind.PRIMARY
    lines = [
        FRONTMATTER_DELIMITER,
        f"name: {role.identifier}",
        f"description: {_yaml_string(role.description)}",
        f"tools: {json.dumps(list(_COPILOT_TOOLS[role.tier]))}",
    ]
    if role.workers:
        lines.append(f"agents: {json.dumps(list(role.workers))}")
    lines.extend(
        (
            f"user-invocable: {json.dumps(is_primary)}",
            f"disable-model-invocation: {json.dumps(is_primary)}",
        )
    )
    if role.copilot_models is not None:
        lines.append(f"model: {json.dumps(list(role.copilot_models))}")
    lines.append(FRONTMATTER_DELIMITER)
    return "\n".join(lines) + "\n"


def _claude_metadata(role: NativeRole) -> str:
    """Render recognized Claude agent frontmatter with scoped tools only."""
    tools = list(_CLAUDE_TOOLS[role.tier])
    if role.tier is RoleTier.COORDINATOR:
        tools.insert(0, f"Agent({', '.join(role.workers)})")
    lines = [
        FRONTMATTER_DELIMITER,
        f"name: {role.identifier}",
        f"description: {_yaml_string(role.description)}",
        f"tools: {_yaml_string(', '.join(tools))}",
    ]
    if role.claude_model is not None:
        lines.append(f"model: {_yaml_string(role.claude_model)}")
    lines.append(FRONTMATTER_DELIMITER)
    return "\n".join(lines) + "\n"


def _render(metadata: str, body: str) -> bytes:
    """Join provider frontmatter to the unmodified shared role body as UTF-8."""
    return metadata.encode("utf-8") + body.encode("utf-8")


def _agent_path(runtime: NativeRuntime, role: NativeRole) -> str:
    """Place one role in the runtime's flat agent discovery directory."""
    return f"{runtime.agent_directory}/{role.identifier}{runtime.agent_suffix}"


def render_native_agents(
    files: dict[str, bytes], runtimes: tuple[str, ...]
) -> dict[str, bytes]:
    """Render selected runtime adapters from strict, selected source assets.

    Invalid targets raise ``NativeRuntimeError``; mistyped or malformed assets
    raise ``InputTypeError`` or ``ValueError``.

    Args:
        files (dict[str, bytes]): Selected source files keyed by path; only matching
            native role assets are decoded.
        runtimes (tuple[str, ...]): Non-empty, unique selection of supported runtimes.

    Returns:
        dict[str, bytes]: UTF-8 frontmatter and shared role body keyed by output path
        under ``.github/agents/`` or ``.claude/agents/``; empty when no roles are found.
    """
    targets = checked_runtimes(runtimes)
    roles = load_roles(files)
    rendered: dict[str, bytes] = {}
    for role in roles:
        # Standard agent-folder discovery is flat; frontmatter hides workers.
        if NativeRuntime.COPILOT in targets:
            path = _agent_path(NativeRuntime.COPILOT, role)
            rendered[path] = _render(_copilot_metadata(role), role.body)
        if NativeRuntime.CLAUDE in targets:
            path = _agent_path(NativeRuntime.CLAUDE, role)
            rendered[path] = _render(_claude_metadata(role), role.body)
    return rendered
