"""Reviewed MCP templates, active host manifests, and the integration inventory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit.core.guards import is_json_object, is_str_list
from scripts.checks.coverage.inputs import read_json

if TYPE_CHECKING:
    from pathlib import Path

_ACTIVE_MCP_SERVERS = {
    "context7": {
        "type": "http",
        "url": "https://mcp.context7.com/mcp/oauth",
    },
    "github": {
        "type": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {
            "X-MCP-Toolsets": "repos,issues,pull_requests,actions",
            "X-MCP-Readonly": "true",
            "X-MCP-Lockdown": "true",
        },
    },
    "microsoft-learn": {
        "type": "http",
        "url": "https://learn.microsoft.com/api/mcp",
    },
}
_REQUIRED_MCP_FLAGS = {
    "azure": ("--read-only",),
    "terraform": ("--toolsets=registry",),
    "playwright": ("--isolated", "--headless"),
    "chrome-devtools": (
        "--isolated",
        "--headless",
        "--no-usage-statistics",
        "--no-performance-crux",
    ),
}


def _valid_mcp_template_server(name: str, server: dict[str, object]) -> bool:
    """Validate one inactive example or reviewed server definition.

    Args:
        name (str): Server name in the template.
        server (dict[str, object]): Decoded server definition.

    Returns:
        bool: ``True`` when the definition matches the reviewed shape for ``name``.
    """
    if name in _ACTIVE_MCP_SERVERS:
        return server == _ACTIVE_MCP_SERVERS[name]
    if server.get("type") == "http":
        url = server.get("url")
        return (
            set(server) == {"type", "url"}
            and isinstance(url, str)
            and url.startswith("https://")
        )
    if server.get("type") != "stdio":
        return False
    command = server.get("command")
    args = server.get("args")
    return (
        set(server) == {"type", "command", "args"}
        and isinstance(command, str)
        and command in {"bunx", "docker"}
        and is_str_list(args)
        and bool(args)
        and (command != "bunx" or args[0] == "--bun")
        and "REVIEWED_" in " ".join(args)
        and not any("latest" in item for item in args)
        and set(_REQUIRED_MCP_FLAGS.get(name, ())) <= set(args)
    )


def _mcp_template_servers(
    filename: str, raw: object, *, wrapper: str, names: set[str]
) -> tuple[dict[str, object] | None, list[str]]:
    """Validate one native template; return its servers and failures.

    Args:
        filename (str): Template file name used to prefix each failure.
        raw (object): Decoded template document.
        wrapper (str): Top-level key that holds the server mapping.
        names (set[str]): Server names the template must define exactly.

    Returns:
        tuple[dict[str, object] | None, list[str]]: The server mapping, or ``None``
            when the wrapper or inventory is invalid, and the failure messages.
    """
    servers = raw.get(wrapper) if is_json_object(raw) else None
    if (
        not is_json_object(raw)
        or set(raw) != {wrapper}
        or not is_json_object(servers)
        or set(servers) != names
    ):
        return None, [f"{filename}: MCP template wrapper or inventory is invalid"]
    failures: list[str] = []
    for name, server in servers.items():
        if not is_json_object(server):
            failures.append(f"{filename}: invalid MCP template server {name}")
        elif not _valid_mcp_template_server(name, server):
            failures.append(f"{filename}: invalid MCP template transport for {name}")
    return servers, failures


def _mcp_templates(root: Path, names: set[str]) -> list[str]:
    """Compare complete inactive native inventories without claiming tool safety.

    Args:
        root (Path): Repository root that holds the editor assets.
        names (set[str]): Server names every native template must define.

    Returns:
        list[str]: Template failures; empty when the templates agree and are valid.
    """
    failures: list[str] = []
    home = root / "packages/shared/.apm/skills/kit-editor/assets"
    definitions: list[dict[str, object]] = []
    for filename, wrapper in (
        ("mcp-vscode.json.template", "servers"),
        ("mcp-claude.json.template", "mcpServers"),
    ):
        servers, template_failures = _mcp_template_servers(
            filename, read_json(home / filename), wrapper=wrapper, names=names
        )
        failures.extend(template_failures)
        if servers is not None:
            definitions.append(servers)
    if any(item != definitions[0] for item in definitions):
        failures.append("native MCP template server definitions disagree")
    optional = read_json(home / "mcp-optional.json.template")
    optional_servers = {
        name: _ACTIVE_MCP_SERVERS[name] for name in ("context7", "microsoft-learn")
    }
    if optional != {"mcpServers": optional_servers}:
        failures.append("optional MCP template definitions are invalid")
    return failures


def active_mcp_manifests(root: Path) -> list[str]:
    """Require matching host manifests with only the reviewed server set."""
    failures: list[str] = []
    for relative, wrapper in (
        (".mcp.json", "mcpServers"),
        (".vscode/mcp.json", "servers"),
    ):
        if read_json(root / relative) != {wrapper: _ACTIVE_MCP_SERVERS}:
            failures.append(
                f"{relative}: active MCP servers must match the reviewed read-only set"
            )
    return failures


def integration_failures(
    root: Path, sections: dict[str, dict[str, object]]
) -> list[str]:
    """Check integration, MCP template, and hook migration inventories.

    Args:
        root (Path): Repository root that holds the editor assets.
        sections (dict[str, dict[str, object]]): Validated baseline sections.

    Returns:
        list[str]: One failure per violated integration, template, or hook rule.
    """
    failures: list[str] = []
    integration = read_json(
        root / "packages/shared/.apm/skills/kit-editor/assets/integration-catalog.json"
    )
    integrations = (
        integration.get("integrations") if is_json_object(integration) else None
    )
    if (
        not is_json_object(integration)
        or integration.get("default_active") != []
        or not is_json_object(integrations)
        or set(integrations) != set(sections["mcp"])
    ):
        failures.append(
            "integration source inventory must match the baseline with no implicit active servers"
        )
    failures.extend(_mcp_templates(root, set(sections["mcp"])))
    if set(sections["hooks"]) != {
        "session-context",
        "tool-guardian",
        "license-guardian",
    }:
        failures.append("hook migration inventory is incomplete")
    return failures
