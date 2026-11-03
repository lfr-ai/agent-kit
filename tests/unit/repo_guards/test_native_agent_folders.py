"""Native agent folders stay flat because runtimes do not discover subfolders."""

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_FOLDERS = (".github/agents", ".claude/agents")


@pytest.mark.parametrize("folder", _FOLDERS)
def test_no_agent_file_exists_in_a_subdirectory(folder: str) -> None:
    """VS Code scans direct children only; nested files would be invisible."""
    root = _ROOT / folder
    nested = [
        path.relative_to(_ROOT).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.parent != root
    ]
    assert nested == []
    assert not any(path.is_dir() for path in root.iterdir())


def _frontmatter(path: Path) -> dict[str, object]:
    _, header, _ = path.read_text(encoding="utf-8").split("---\n", 2)
    metadata = yaml.safe_load(header)
    assert isinstance(metadata, dict)
    return metadata


def test_repository_copilot_agents_resolve_and_hide_workers() -> None:
    """Every ``agents:`` entry names an existing agent; workers are picker-hidden."""
    metadata = {
        path.name: _frontmatter(path)
        for path in sorted((_ROOT / ".github/agents").glob("*.agent.md"))
    }
    names = {str(item["name"]) for item in metadata.values()}
    assert {path.removesuffix(".agent.md") for path in metadata} == names
    for filename, item in metadata.items():
        allowed = item.get("agents", [])
        assert isinstance(allowed, list), filename
        tools = item["tools"]
        assert isinstance(tools, list), filename
        assert set(allowed) <= names, filename
        if item["user-invocable"] is False:
            assert item["disable-model-invocation"] is False, filename
            assert "agents" not in item, filename
            assert "agent" not in tools, filename
        if allowed:
            assert "agent" in tools, filename
