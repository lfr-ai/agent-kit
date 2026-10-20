"""Contracts for the repository-owned native adapters outside APM ownership."""

import json
from pathlib import Path

import pytest
import yaml
from scripts.check_native import check

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
