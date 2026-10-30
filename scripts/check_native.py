"""Validate this repository's explicit native adapter contract."""

import json
from pathlib import Path
import sys

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_COMMAND = "uv run --locked --no-sync agent-kit context"
_SESSION_ENTRYPOINTS = (".venv/Scripts/agent-kit.exe", ".venv/bin/agent-kit")
_HOOK_TIMEOUT_SECONDS = 10
_FRONTMATTER_FENCES = 2  # split into empty prefix, metadata, and body
# Dependencies change through a reviewed, audited lock; agents never install ad hoc.
_PACKAGE_INSTALL_DENY = [
    "Bash(pip install *)",
    "Bash(pip3 install *)",
    "Bash(python -m pip install *)",
    "Bash(python3 -m pip install *)",
    "Bash(pipx *)",
    "Bash(uv add *)",
    "Bash(uv pip install *)",
    "Bash(uv tool install *)",
    "Bash(uv tool run *)",
    "Bash(uvx *)",
    "Bash(npm install *)",
    "Bash(npm i *)",
    "Bash(npm exec *)",
    "Bash(npx *)",
    "Bash(pnpm add *)",
    "Bash(pnpm dlx *)",
    "Bash(yarn add *)",
    "Bash(yarn dlx *)",
    "Bash(bun add *)",
    "Bash(bunx *)",
]
# Publishing is human-approved. Pushes and pull requests prompt; force, tags, releases,
# repository settings and credentials are refused. Rules match the usual command
# spelling only: the ruleset and repository-scoped token are the real boundary.
_VERSION_CONTROL_ASK = [
    "Bash(git push *)",
    "Bash(git * push *)",
    "Bash(git reset --hard *)",
    "Bash(git clean *)",
    "Bash(git rebase *)",
    "Bash(git branch -D *)",
    "Bash(gh pr create *)",
    "Bash(gh pr merge *)",
    "Bash(gh pr close *)",
    "Bash(gh pr edit *)",
    "Bash(gh issue create *)",
    "Bash(gh api *)",
]
_VERSION_CONTROL_DENY = [
    "Bash(*git*push*--force*)",
    "Bash(*git*push* -f*)",
    "Bash(*git*push*--delete*)",
    "Bash(*git*push*--mirror*)",
    "Bash(*git*push*--tags*)",
    "Bash(*git*push* +*)",
    "Bash(*git*push* :*)",
    "Bash(*gh*pr merge*--admin*)",
    "Bash(git tag *)",
    "Bash(git config --global *)",
    "Bash(git config --system *)",
    "Bash(gh release *)",
    "Bash(gh repo edit *)",
    "Bash(gh repo delete *)",
    "Bash(gh repo rename *)",
    "Bash(gh secret *)",
    "Bash(gh variable *)",
    "Bash(gh auth *)",
]
# VS Code false rules always require approval; they are not a sandbox.
_PACKAGE_INSTALL_APPROVAL = {
    "/^(pip|pip3|pipx|uvx|npx|bunx)(\\s|$)/": False,
    "/^python[0-9.]*(\\.exe)?\\s+-m\\s+pip\\s+install\\b/": False,
    "/^uv\\s+(add|pip\\s+install|tool\\s+(install|run))\\b/": False,
    "/^(npm|pnpm|yarn|bun)\\s+(add|i|install|exec|dlx|x)\\b/": False,
}
_VERSION_CONTROL_APPROVAL = {
    "/^git\\b.*\\bpush\\b/": False,
    "/^git\\s+(tag|rebase|clean|reset\\s+--hard|branch\\s+-D|config\\s+--(global|system))\\b/": False,
    "/^gh\\s+(pr\\s+(create|merge|close|edit|ready)|issue\\s+(create|edit|close)|release|repo|api|auth|secret|variable)\\b/": False,
}
_TERMINAL_APPROVAL = {**_PACKAGE_INSTALL_APPROVAL, **_VERSION_CONTROL_APPROVAL}
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
    "chat.tools.terminal.autoApprove": _TERMINAL_APPROVAL,
}


def _reviewer(path: Path) -> tuple[object, str]:
    """Read metadata and body without importing provider code."""
    header, body = path.read_text(encoding="utf-8").split("---", _FRONTMATTER_FENCES)[
        1:
    ]
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


def _reviewer_failures(root: Path) -> list[str]:
    """Require matching, least-privilege native reviewer definitions."""
    failures: list[str] = []
    copilot, copilot_body = _reviewer(root / ".github/agents/kit-reviewer.agent.md")
    claude, claude_body = _reviewer(root / ".claude/agents/kit-reviewer.md")
    failures.extend(
        "Native reviewer metadata requires explicit review."
        for metadata, fields in ((copilot, _COPILOT_FIELDS), (claude, _CLAUDE_FIELDS))
        if not isinstance(metadata, dict) or set(metadata) != fields
    )
    if not isinstance(copilot, dict) or copilot.get("tools") != ["read", "search"]:
        failures.append("Copilot reviewer must use the approved read/search tools.")
    if isinstance(copilot, dict) and copilot.get("agents") != []:
        failures.append("Copilot reviewer cannot enable nested workers.")
    if not isinstance(copilot, dict) or (
        copilot.get("user-invocable") is not True
        or copilot.get("disable-model-invocation") is not False
    ):
        failures.append(
            "Copilot reviewer invocation flags must be true/false booleans."
        )
    if not isinstance(claude, dict) or claude.get("tools") != "Read, Grep, Glob":
        failures.append("Claude reviewer must use the approved Read/Grep/Glob tools.")
    if copilot_body != claude_body:
        failures.append("Native reviewer procedure bodies diverged.")
    return failures


def _copilot_hook_failures(root: Path) -> list[str]:
    """Require the reviewed Copilot session hook."""
    copilot_hook = json.loads((root / ".github/hooks/session-context.json").read_text())
    expected_copilot = {
        "version": 1,
        "hooks": {
            "sessionStart": [
                {
                    "type": "command",
                    "command": _COMMAND,
                    "timeoutSec": _HOOK_TIMEOUT_SECONDS,
                }
            ]
        },
    }
    if copilot_hook != expected_copilot:
        return ["Copilot hook contract changed without a contract review."]
    return []


def _claude_settings_failures(root: Path) -> list[str]:
    """Require the reviewed Claude session hook and permission defaults."""
    failures: list[str] = []
    settings = json.loads((root / ".claude/settings.json").read_text())
    expected_hooks = {
        "SessionStart": [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [
                    {
                        "type": "command",
                        "command": _COMMAND,
                        "timeout": _HOOK_TIMEOUT_SECONDS,
                    }
                ],
            }
        ]
    }
    if settings.get("hooks") != expected_hooks:
        failures.append("Claude hook contract changed without a contract review.")
    if settings.get("disableAllHooks", False) is not False:
        failures.append("Claude session hooks must not be disabled (disableAllHooks).")
    if settings.get("permissions") != {
        "defaultMode": "default",
        "ask": _VERSION_CONTROL_ASK,
        "deny": [
            "Read(.env)",
            "Read(.env.*)",
            *_PACKAGE_INSTALL_DENY,
            *_VERSION_CONTROL_DENY,
        ],
    }:
        failures.append("Claude native permission defaults changed.")
    return failures


def check(root: Path) -> list[str]:
    """Find changed reviewer tools, policy scope, or hook execution ownership."""
    failures = _reviewer_failures(root)
    failures.extend(_copilot_hook_failures(root))
    failures.extend(_claude_settings_failures(root))
    vscode = json.loads((root / ".vscode/settings.json").read_text())
    failures.extend(_vscode_contract(vscode))
    return failures


def main() -> int:
    """Print native contract failures without changing configuration."""
    try:
        failures = check(_ROOT)
        if not any((_ROOT / name).is_file() for name in _SESSION_ENTRYPOINTS):
            failures.append(
                "Local session context entrypoint is missing. Run task bootstrap to "
                "audit and provision the locked environment; --no-sync hooks never "
                "install dependencies."
            )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        sys.stderr.write(f"Native contract cannot be parsed: {exc}\n")
        return 1
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return 1
    sys.stdout.write("Repository native adapter contracts passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
