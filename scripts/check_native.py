"""Validate this repository's explicit native adapter contract."""

import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_COMMAND = "uv run --locked agent-kit context"
_COPILOT_FIELDS = {
    "name",
    "description",
    "tools",
    "agents",
    "user-invocable",
    "disable-model-invocation",
}
_CLAUDE_FIELDS = {"name", "description", "tools"}
_VSCODE_TOOLCHAIN = {
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv",
    "python.languageServer": "None",
    "python.testing.cwd": "${workspaceFolder}",
    "python.testing.pytestEnabled": True,
    "python.testing.unittestEnabled": False,
    "python.testing.pytestArgs": ["tests"],
    "ruff.nativeServer": "on",
    "ruff.importStrategy": "fromEnvironment",
    "ruff.configurationPreference": "filesystemFirst",
    "ty.importStrategy": "fromEnvironment",
    "ty.diagnosticMode": "workspace",
    "chat.useAgentSkills": True,
    "chat.useAgentsMdFile": True,
    "chat.useClaudeMdFile": False,
    "chat.mcp.autostart": "never",
}


def _reviewer(path: Path) -> tuple[object, str]:
    """Read metadata and body without importing provider code."""
    header, body = path.read_text(encoding="utf-8").split("---", 2)[1:]
    return yaml.safe_load(header), body.strip()


def _vscode_contract(settings: object) -> list[str]:
    """Keep workspace tool ownership and native discovery explicit."""
    if not isinstance(settings, dict):
        return ["VS Code settings must be a JSON object."]
    failures = [
        f"VS Code setting '{name}' differs from the project toolchain/discovery contract."
        for name, expected in _VSCODE_TOOLCHAIN.items()
        if settings.get(name) != expected
        or type(settings.get(name)) is not type(expected)
    ]
    python = settings.get("[python]")
    if not isinstance(python, dict) or python.get("editor.defaultFormatter") != (
        "charliermarsh.ruff"
    ):
        failures.append("VS Code Python formatting must be owned by Ruff.")
    if settings.get("chat.useClaudeHooks") is not False:
        failures.append("VS Code Local must not execute mirrored Claude hooks.")
    return failures


def check(root: Path) -> list[str]:
    """Find changed reviewer tools, policy scope, or hook execution ownership."""
    failures: list[str] = []
    copilot, copilot_body = _reviewer(root / ".github/agents/kit-reviewer.agent.md")
    claude, claude_body = _reviewer(root / ".claude/agents/kit-reviewer.md")
    for metadata, fields in (
        (copilot, _COPILOT_FIELDS),
        (claude, _CLAUDE_FIELDS),
    ):
        if not isinstance(metadata, dict) or set(metadata) != fields:
            failures.append("Native reviewer metadata requires explicit review.")
    if not isinstance(copilot, dict) or copilot.get("tools") != ["read", "search"]:
        failures.append("Copilot reviewer must use the approved read/search tools.")
    if isinstance(copilot, dict) and copilot.get("agents") != []:
        failures.append("Copilot reviewer cannot enable nested workers.")
    if not isinstance(claude, dict) or claude.get("tools") != "Read, Grep, Glob":
        failures.append("Claude reviewer must use the approved Read/Grep/Glob tools.")
    if copilot_body != claude_body:
        failures.append("Native reviewer procedure bodies diverged.")
    copilot_hook = json.loads((root / ".github/hooks/session-context.json").read_text())
    expected_copilot = {
        "version": 1,
        "hooks": {
            "sessionStart": [{"type": "command", "command": _COMMAND, "timeoutSec": 10}]
        },
    }
    if copilot_hook != expected_copilot:
        failures.append("Copilot hook contract changed without a contract review.")
    settings = json.loads((root / ".claude/settings.json").read_text())
    expected_hooks = {
        "SessionStart": [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [{"type": "command", "command": _COMMAND, "timeout": 10}],
            }
        ]
    }
    if settings.get("hooks") != expected_hooks:
        failures.append("Claude hook contract changed without a contract review.")
    if settings.get("permissions") != {
        "defaultMode": "default",
        "deny": ["Read(.env)", "Read(.env.*)"],
    }:
        failures.append("Claude native permission defaults changed.")
    vscode = json.loads((root / ".vscode/settings.json").read_text())
    failures.extend(_vscode_contract(vscode))
    return failures


def main() -> int:
    """Print native contract failures without changing configuration."""
    try:
        failures = check(_ROOT)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Native contract cannot be parsed: {exc}", file=sys.stderr)
        return 1
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print("Repository native adapter contracts passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
