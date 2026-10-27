"""Contracts for the repository-owned native adapters outside APM ownership."""

import json
from pathlib import Path
import re

import pytest
from scripts.check_native import check
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_FILES = (
    ".github/agents/kit-reviewer.agent.md",
    ".claude/agents/kit-reviewer.md",
    ".github/hooks/session-context.json",
    ".claude/settings.json",
    ".vscode/settings.json",
)


@pytest.fixture
def native_root(tmp_path: Path) -> Path:
    """Copy only known repository-owned adapter inputs into a synthetic root."""
    for relative in _FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((_ROOT / relative).read_bytes())
    return tmp_path


def test_approved_native_contract_passes(native_root: Path) -> None:
    """Known reviewer, permission, and single-hook contracts pass."""
    assert check(native_root) == []


def test_reviewer_cannot_enable_nested_agents(native_root: Path) -> None:
    """Changing the explicit empty worker allowlist must fail the contract."""
    path = native_root / ".github/agents/kit-reviewer.agent.md"
    text = path.read_text()
    header, body = text.split("---", 2)[1:]
    metadata = yaml.safe_load(header)
    metadata["agents"] = ["*"]
    path.write_text(f"---\n{yaml.safe_dump(metadata)}---\n{body}", encoding="utf-8")

    assert any("reviewer" in finding for finding in check(native_root))


def test_writable_tools_are_rejected(native_root: Path) -> None:
    """The read-only reviewer cannot gain an edit tool."""
    path = native_root / ".claude/agents/kit-reviewer.md"
    path.write_text(
        path.read_text().replace("Read, Grep, Glob", "Read, Grep, Glob, Edit"),
        encoding="utf-8",
    )

    assert any("Claude reviewer" in finding for finding in check(native_root))


def test_unknown_native_reviewer_metadata_is_rejected(native_root: Path) -> None:
    """An unreviewed native metadata extension cannot silently change behavior."""
    path = native_root / ".claude/agents/kit-reviewer.md"
    text = path.read_text()
    header, body = text.split("---", 2)[1:]
    metadata = yaml.safe_load(header)
    metadata["mcpServers"] = ["unapproved-server"]
    path.write_text(f"---\n{yaml.safe_dump(metadata)}---\n{body}", encoding="utf-8")

    assert any("metadata" in finding for finding in check(native_root))


def test_mirrored_hook_double_execution_is_rejected(native_root: Path) -> None:
    """VS Code Local cannot enable the mirrored Claude hook source."""
    path = native_root / ".vscode/settings.json"
    settings = json.loads(path.read_text())
    settings["chat.useClaudeHooks"] = True
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("mirrored" in finding for finding in check(native_root))


def test_permission_widening_is_rejected(native_root: Path) -> None:
    """Native permission drift is not hidden by a passing APM audit."""
    path = native_root / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["permissions"]["allow"] = ["Bash(*)"]
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("permission" in finding for finding in check(native_root))


@pytest.mark.parametrize("rule", ["Bash(uv add *)", "Bash(npx *)", "Bash(uvx *)"])
def test_agent_package_install_denials_cannot_be_dropped(
    native_root: Path, rule: str
) -> None:
    """Agents cannot install unreviewed packages outside the audited lockfile."""
    path = native_root / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["permissions"]["deny"].remove(rule)
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("permission" in finding for finding in check(native_root))


def test_vscode_package_install_approval_cannot_be_relaxed(native_root: Path) -> None:
    """A workspace auto-approval cannot replace the required installer prompt."""
    path = native_root / ".vscode/settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    rules = settings["chat.tools.terminal.autoApprove"]
    rules[next(iter(rules))] = True
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("VS Code" in finding for finding in check(native_root))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("python.defaultInterpreterPath", "C:\\machine\\python.exe"),
        ("python.languageServer", "Pylance"),
        ("python.testing.unittestEnabled", True),
        ("python.testing.pytestEnabled", False),
        ("python.testing.pytestEnabled", 1),
        ("python.testing.unittestEnabled", 0),
        ("ty.diagnosticMode", "off"),
        ("ruff.importStrategy", "useBundled"),
        ("chat.useClaudeMdFile", True),
        ("chat.mcp.autostart", "newAndOutdated"),
    ],
)
def test_workspace_toolchain_and_discovery_drift_is_rejected(
    native_root: Path, key: str, value: object
) -> None:
    path = native_root / ".vscode/settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings[key] = value
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("VS Code" in finding for finding in check(native_root))


def test_python_formatter_drift_is_rejected(native_root: Path) -> None:
    path = native_root / ".vscode/settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings.setdefault("[python]", {})["editor.defaultFormatter"] = (
        "ms-python.black-formatter"
    )
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("VS Code" in finding for finding in check(native_root))


def _claude_rules() -> dict[str, list[str]]:
    permissions = json.loads((_ROOT / ".claude/settings.json").read_text("utf-8"))
    return permissions["permissions"]


def _matches(rule: str, command: str) -> bool:
    """Apply Claude Code's documented Bash wildcard semantics to one rule."""
    pattern = rule.removeprefix("Bash(").removesuffix(")")
    expression = ".*".join(re.escape(part) for part in pattern.split("*"))
    if pattern.endswith(" *"):
        expression = expression.removesuffix(r"\ .*") + r"(?:\ .*)?"
    return re.fullmatch(expression, command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push origin main --force-with-lease",
        "git push -f",
        "git -C . push --force",
        "git push origin --delete feature",
        "git push origin +main",
        "git push origin :feature",
        "git push --tags",
        "git tag v1.0.0",
        "git config --global user.name x",
        "gh release create v1.0.0",
        "gh repo edit --visibility private",
        "gh auth token",
        "gh pr merge 3 --squash --admin",
    ],
)
def test_irreversible_publication_is_refused(command: str) -> None:
    """Force, tags, releases, settings, credentials and admin merges are denied."""
    assert any(_matches(rule, command) for rule in _claude_rules()["deny"])


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin fix/kit-skill",
        "git -C ../agent-kit push origin fix/kit-skill",
        "gh pr create --fill",
        "gh pr merge 3 --auto --squash",
        "gh api repos/lfr-ai/agent-kit/pulls",
    ],
)
def test_pushes_and_pull_requests_require_approval_but_are_not_denied(
    command: str,
) -> None:
    """An approved branch push and pull request stay possible, never silent."""
    rules = _claude_rules()
    assert any(_matches(rule, command) for rule in rules["ask"])
    assert not any(_matches(rule, command) for rule in rules["deny"])


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git diff",
        "git log --oneline",
        "git switch -c fix/x",
        "git commit -m tag",
    ],
)
def test_local_git_work_is_never_blocked_or_prompted(command: str) -> None:
    """Branching and committing on request must stay frictionless."""
    rules = _claude_rules()
    assert not any(_matches(rule, command) for rule in (*rules["ask"], *rules["deny"]))


@pytest.mark.parametrize(
    "rule", ["Bash(git push *)", "Bash(gh pr create *)", "Bash(gh pr merge *)"]
)
def test_publication_approval_rules_cannot_be_dropped(
    native_root: Path, rule: str
) -> None:
    """Pushing and opening a pull request cannot silently stop asking."""
    path = native_root / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["permissions"]["ask"].remove(rule)
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("permission" in finding for finding in check(native_root))


@pytest.mark.parametrize(
    "rule", ["Bash(git tag *)", "Bash(*git*push*--force*)", "Bash(gh release *)"]
)
def test_publication_denials_cannot_be_dropped(native_root: Path, rule: str) -> None:
    """Tags, force pushes and releases cannot be re-enabled by editing settings."""
    path = native_root / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["permissions"]["deny"].remove(rule)
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("permission" in finding for finding in check(native_root))


def test_vscode_push_approval_cannot_be_relaxed(native_root: Path) -> None:
    """A workspace auto-approval cannot cover git push or pull-request creation."""
    path = native_root / ".vscode/settings.json"
    settings = json.loads(path.read_text(encoding="utf-8"))
    rules = settings["chat.tools.terminal.autoApprove"]
    rules["/^git\\b.*\\bpush\\b/"] = True
    path.write_text(json.dumps(settings), encoding="utf-8")

    assert any("VS Code" in finding for finding in check(native_root))
