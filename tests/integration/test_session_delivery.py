"""End-to-end session delivery through the CLI, composition root, and real catalog."""

import json
from pathlib import Path

import pytest

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.composition.root import build_actions
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.presentation.cli import main


def test_cli_session_delivery_has_verifiable_integrity(
    source_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "session"

    result = main(
        build_actions(),
        [
            "compose",
            "backend",
            "--root",
            str(source_root),
            "--output",
            str(output),
            "--skill",
            "kit-backend",
            "--runtime",
            "copilot",
        ],
    )
    captured = capsys.readouterr()

    assert result == 0, captured.err
    assert "native roles omitted" in captured.out
    assert "not billed tokens" in captured.out
    assert not (output / ".claude").exists()
    report = ProvenanceService().verify(FileCatalogAdapter().load_composed(output))
    assert report.valid


def test_hexagonal_architecture_skill_session_keeps_instructions_and_resources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The renamed shared capability keeps the established session delivery contract."""
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "hexagonal-session"
    skill_id = "kit-hexagonal-architecture"

    result = main(
        build_actions(),
        [
            "compose",
            "shared",
            "--root",
            str(root),
            "--output",
            str(output),
            "--skill",
            skill_id,
            "--runtime",
            "copilot",
        ],
    )
    captured = capsys.readouterr()

    assert result == 0, captured.err
    assert "native roles omitted" in captured.out
    files = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    source_skill = (
        root / "packages/shared/.apm/skills/kit-hexagonal-architecture/SKILL.md"
    )
    skill_path = ".apm/skills/kit-hexagonal-architecture/SKILL.md"
    assert files[skill_path] == source_skill.read_bytes()
    assert ".apm/skills/kit-clean-architecture/SKILL.md" not in files
    instructions = {
        f".apm/instructions/{path.name}"
        for path in (root / "packages/shared/.apm/instructions").glob(
            "*.instructions.md"
        )
    }
    assert instructions <= files.keys()
    selection = json.loads(files[".apm/selection.json"])
    assert selection["mode"] == "session"
    assert selection["skills"] == [skill_id]
    assert selection["instructions"] == sorted(
        path.removeprefix(".apm/instructions/").removesuffix(".instructions.md")
        for path in instructions
    )
    assert selection["native_role_files"] == 0


def test_clean_architecture_alias_is_not_selectable_for_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The renamed capability has no legacy runtime alias or shim."""
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "legacy-session"

    result = main(
        build_actions(),
        [
            "compose",
            "shared",
            "--root",
            str(root),
            "--output",
            str(output),
            "--skill",
            "kit-clean-architecture",
        ],
    )
    captured = capsys.readouterr()

    assert result == 1
    assert "kit-clean-architecture" in captured.err
    assert not output.exists()


def test_session_omits_native_roles_even_if_their_skill_is_selected() -> None:
    root = Path(__file__).parents[2]
    snapshot = FileCatalogAdapter().load(root)

    session = CatalogService().compose(
        snapshot, "shared", (), ("copilot",), skills=("kit-agent-runtime",)
    )
    project = CatalogService().compose(snapshot, "shared", (), ("copilot",))
    session_paths = {item.relative_path for item in session.files}

    assert ".apm/skills/kit-agent-runtime/assets/agents.json" in session_paths
    assert not any(
        name.startswith((".github/agents/", ".claude/agents/"))
        for name in session_paths
    )
    assert any(
        item.relative_path.startswith(".github/agents/") for item in project.files
    )
