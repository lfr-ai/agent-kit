"""Consistency of the MCP inventory across policy, manifests, native files and docs."""

import json
from pathlib import Path
import re

import yaml

from agent_kit.application.services import catalog_service
from agent_kit.core.executables import mcp_issues

_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES = sorted((_ROOT / "packages").glob("*/apm.yml"))
_DEFAULTS = {"context7", "github", "microsoft-learn"}
_ROW = re.compile(r"^\| `?([a-z0-9-]+)`? \| ([^|]+) \|$")


def _declared() -> dict[str, list[dict[str, object]]]:
    found: dict[str, list[dict[str, object]]] = {}
    for manifest in _PACKAGES:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        entries = data.get("dependencies", {}).get("mcp", [])
        found[manifest.parent.name] = list(entries)
    return found


def _policy() -> dict[str, object]:
    return yaml.safe_load((_ROOT / "apm-policy.yml").read_text(encoding="utf-8"))


def _mcp_policy() -> dict[str, object]:
    value = _policy()["mcp"]
    assert isinstance(value, dict)
    return value


def _allowed() -> list[str]:
    value = _mcp_policy()["allow"]
    assert isinstance(value, list)
    assert all(isinstance(name, str) for name in value)
    return value


def _name(entry: dict[str, object]) -> str:
    value = entry["name"]
    assert isinstance(value, str)
    return value


def _native(path: str, key: str) -> dict[str, dict[str, object]]:
    data = json.loads((_ROOT / path).read_text(encoding="utf-8"))
    return data[key]


def test_allow_list_is_exactly_the_declared_servers() -> None:
    """A name without a declaration is dead permission; a declaration without one fails."""
    declared = {_name(entry) for entries in _declared().values() for entry in entries}
    allowed = _allowed()

    assert sorted(allowed) == allowed
    assert set(allowed) == declared


def test_generated_policy_matches_the_repository_policy() -> None:
    assert catalog_service._POLICY["mcp"] == _policy()["mcp"]
    assert list(catalog_service._MCP_ALLOWED) == _allowed()


def test_every_package_passes_the_closed_schema_with_the_shared_allow_list() -> None:
    allowed = _allowed()

    for package, entries in _declared().items():
        if entries:
            assert mcp_issues(entries, allowed=allowed) == [], package


def test_workspace_manifests_hold_only_the_reviewed_defaults() -> None:
    claude = _native(".mcp.json", "mcpServers")
    vscode = _native(".vscode/mcp.json", "servers")
    shared = {_name(entry): entry for entry in _declared()["shared"]}

    assert set(claude) == set(vscode) == _DEFAULTS == set(shared)
    for name, entry in shared.items():
        assert claude[name] == vscode[name]
        assert claude[name]["url"] == entry["url"]
        assert claude[name].get("headers", {}) == entry.get("headers", {})


def test_github_default_is_read_only_and_locked_down() -> None:
    headers = _native(".mcp.json", "mcpServers")["github"]["headers"]
    assert isinstance(headers, dict)

    assert headers["X-MCP-Readonly"] == "true"
    assert headers["X-MCP-Lockdown"] == "true"
    assert "X-MCP-Toolsets" in headers


def test_workspace_manifests_carry_no_credentials() -> None:
    text = (_ROOT / ".mcp.json").read_text(encoding="utf-8").lower()

    for marker in ("authorization", "token", "secret", "password", "api_key"):
        assert marker not in text


def test_policy_restricts_transport_and_transitive_trust() -> None:
    mcp = _mcp_policy()

    assert mcp["trust_transitive"] is False
    assert mcp["self_defined"] == "allow"
    assert mcp["transport"] == {"allow": ["http", "stdio"]}


def test_adoption_guide_covers_every_server_and_package() -> None:
    guide = (_ROOT / "docs/mcp-adoption.md").read_text(encoding="utf-8")
    rows = {
        match.group(1): match.group(2)
        for line in guide.splitlines()
        if (match := _ROW.match(line)) is not None
    }

    for name in _allowed():
        assert f"`{name}`" in guide, name
    for package, entries in _declared().items():
        expected = ", ".join(_name(entry) for entry in entries)
        assert rows.get(package, "none") == (expected or "none"), package
