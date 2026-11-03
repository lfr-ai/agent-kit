"""Closed-schema checks for delivered hook and MCP declarations."""

from collections.abc import Mapping
import json
from pathlib import Path
from urllib.parse import urlunsplit

import pytest
import yaml

from agent_kit.core.executables import hook_issues, mcp_issues, script_issue

_ROOT = Path(__file__).resolve().parents[3]
_ALLOWED = ("docs", "local", "remote", "tool")
_DIGEST = "a" * 64
_USERINFO_URL = urlunsplit(("https", "user:fixture@example.com", "/mcp", "", ""))
_BUNX = {
    "name": "tool",
    "registry": False,
    "transport": "stdio",
    "command": "bunx",
    "args": ["--bun", "@scope/server@1.2.3", "--flag"],
}
_DOCKER = {
    "name": "local",
    "registry": False,
    "transport": "stdio",
    "command": "docker",
    "args": ["run", "-i", "--rm", f"example/server:1.0@sha256:{_DIGEST}", "--ro"],
}
_HTTP = {
    "name": "docs",
    "registry": False,
    "transport": "http",
    "url": "https://example.com/mcp",
    "headers": {"X-MCP-Readonly": "true"},
}
_HOOK_ENTRY = {
    "type": "command",
    "bash": "python3 ./scripts/guard.py",
    "powershell": "python ./scripts/guard.py",
    "timeoutSec": 10,
}


def _with(base: Mapping[str, object], **changes: object) -> dict[str, object]:
    return {**base, **changes}


def _hook_text(entry_changes: Mapping[str, object] | None = None) -> str:
    entry = {**_HOOK_ENTRY, **(entry_changes or {})}
    return json.dumps({"version": 1, "hooks": {"preToolUse": [entry]}})


@pytest.mark.parametrize("entry", [_BUNX, _DOCKER, _HTTP])
def test_valid_declarations_have_no_issues(entry: Mapping[str, object]) -> None:
    assert mcp_issues([entry], allowed=_ALLOWED) == []


def test_loopback_http_is_allowed() -> None:
    entry = _with(_HTTP, url="http://localhost:6006/mcp", headers={})

    assert mcp_issues([entry], allowed=_ALLOWED) == []


@pytest.mark.parametrize(
    "entry",
    [
        _with(_BUNX, args=["--bun", "@scope/server@latest"]),
        _with(_BUNX, args=["--bun", "@scope/server"]),
        _with(_BUNX, args=["@scope/server@1.2.3"]),
        _with(_BUNX, args=["--bun", "@scope/server@1.2.3", "$(id)"]),
        _with(_BUNX, args=[]),
        _with(_BUNX, command="npx"),
        _with(_BUNX, command="sh"),
        _with(_BUNX, url="https://example.com"),
        _with(_DOCKER, args=["run", "-i", "--rm", "example/server:1.0"]),
        _with(_DOCKER, args=["run", "-i", "--rm", "example/server:latest"]),
        _with(
            _DOCKER,
            args=["run", "--privileged", "-i", "--rm", f"x:1@sha256:{_DIGEST}"],
        ),
        _with(_DOCKER, args=["run", "-i", f"x:1@sha256:{_DIGEST}"]),
        _with(_HTTP, url="http://example.com/mcp"),
        _with(_HTTP, url=_USERINFO_URL),
        _with(_HTTP, url="https://example.com/mcp?token=1"),
        _with(_HTTP, url="https://example.com/mcp#frag"),
        _with(_HTTP, url=7),
        _with(_HTTP, url="https://"),
        _with(_HTTP, url="https://example .com/mcp"),
        _with(_HTTP, url="https://example.com:invalid/mcp"),
        _with(_HTTP, url="https://example.com:0/mcp"),
        _with(_HTTP, name=[]),
        _with(_BUNX, command=[]),
        _with(_HTTP, headers={"Authorization": "Bearer token"}),
        _with(_HTTP, headers={"X-MCP-Readonly": "a b"}),
        _with(_HTTP, headers=["X-MCP-Readonly"]),
        _with(_HTTP, command="bunx"),
        _with(_HTTP, registry=True),
        _with(_HTTP, name="unreviewed"),
        _with(_HTTP, transport="sse"),
        {**_HTTP, "env": {"TOKEN": "x"}},
    ],
)
def test_unsafe_declarations_are_rejected(entry: Mapping[str, object]) -> None:
    assert mcp_issues([entry], allowed=_ALLOWED)


def test_issues_never_echo_declared_values() -> None:
    leaked_url = f"{_USERINFO_URL}?token=fixture"
    issues = mcp_issues([_with(_HTTP, url=leaked_url)], allowed=_ALLOWED)

    assert issues
    assert all("fixture" not in issue for issue in issues)


@pytest.mark.parametrize("entries", [None, [], {}, "docs", [None], [[]]])
def test_malformed_lists_are_rejected(entries: object) -> None:
    assert mcp_issues(entries, allowed=_ALLOWED)


def test_duplicate_names_are_rejected() -> None:
    assert mcp_issues([_HTTP, _HTTP], allowed=_ALLOWED)


def test_valid_hook_has_no_issues() -> None:
    assert hook_issues(_hook_text(), ["guard.py"]) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"bash": "python3 ./scripts/other.py"},
        {"bash": "python3 ./scripts/guard.py; id"},
        {"bash": "bash -c 'id'"},
        {"powershell": "pwsh -c id"},
        {"timeoutSec": 0},
        {"timeoutSec": 31},
        {"timeoutSec": "10"},
        {"timeoutSec": True},
        {"cwd": "/"},
        {"type": "http"},
    ],
)
def test_unsafe_hook_entries_are_rejected(changes: Mapping[str, object]) -> None:
    assert hook_issues(_hook_text(changes), ["guard.py"])


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        json.dumps({"version": 2, "hooks": {}}),
        json.dumps({"version": True, "hooks": {"preToolUse": [_HOOK_ENTRY]}}),
        json.dumps({"version": 1, "hooks": {}}),
        json.dumps({"version": 1}),
        json.dumps({"version": 1, "hooks": {"preToolUse": [_HOOK_ENTRY]}, "extra": 1}),
        json.dumps({"version": 1, "hooks": {"postToolUse": []}}),
        json.dumps({"version": 1, "hooks": {"preToolUse": []}}),
        json.dumps({"version": 1, "hooks": {"preToolUse": ["x"]}}),
    ],
)
def test_malformed_hook_files_are_rejected(text: str) -> None:
    assert hook_issues(text, ["guard.py"])


def test_hook_script_must_ship_in_the_bundle() -> None:
    assert hook_issues(_hook_text(), [])


@pytest.mark.parametrize("name", ["guard.py", "rules.policy"])
def test_script_names_allow_python_and_policy(name: str) -> None:
    assert script_issue(name) is None


@pytest.mark.parametrize(
    "name", ["rules.json", "run.sh", "nested/guard.py", "../guard.py", ".py", ""]
)
def test_script_names_reject_other_files(name: str) -> None:
    assert script_issue(name) is not None


def _shipped_mcp() -> list[tuple[str, dict[str, object]]]:
    found: list[tuple[str, dict[str, object]]] = []
    for manifest in sorted((_ROOT / "packages").glob("*/apm.yml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        found.extend(
            (manifest.parent.name, entry)
            for entry in data.get("dependencies", {}).get("mcp", [])
        )
    return found


def test_shipped_servers_satisfy_the_policy_allow_list() -> None:
    policy = yaml.safe_load((_ROOT / "apm-policy.yml").read_text(encoding="utf-8"))
    allowed = policy["mcp"]["allow"]
    shipped = _shipped_mcp()

    assert shipped
    for package in {name for name, _ in shipped}:
        entries = [entry for name, entry in shipped if name == package]
        assert mcp_issues(entries, allowed=allowed) == [], package
    assert {entry["name"] for _, entry in shipped} <= set(allowed)


def test_consumer_template_mirrors_the_repository_policy() -> None:
    template = _ROOT / ".apm/skills/kit-apm-adopt/assets/apm-policy.yml.template"
    consumer = yaml.safe_load(template.read_text(encoding="utf-8"))
    repository = yaml.safe_load((_ROOT / "apm-policy.yml").read_text("utf-8"))

    assert consumer["mcp"] == repository["mcp"]
    assert "executables" not in consumer
    assert "executables" not in repository


def test_shipped_hook_registration_is_valid() -> None:
    hooks = _ROOT / "packages/shared/.apm/hooks"
    scripts = [item.name for item in (hooks / "scripts").iterdir()]

    for registration in hooks.glob("*.json"):
        text = registration.read_text(encoding="utf-8")
        assert hook_issues(text, scripts) == [], registration.name
    assert (hooks / "git-guard.json").is_file()
