"""End-to-end session delivery through the CLI, composition root, and real catalog."""

import json
from pathlib import Path

import pytest

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.composition.root import build_actions
import agent_kit.infrastructure.catalog_adapter as catalog_module
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


@pytest.mark.parametrize(
    "generated",
    ["__pycache__/helper.cpython-313.pyc", "helper.pyc", "helper.pyo"],
)
def test_delivery_omits_source_bytecode_but_rejects_injected_output(
    source_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    generated: str,
) -> None:
    assets = source_root / "packages/shared/.apm/skills/kit-shared/assets"
    assets.mkdir()
    cache = assets / generated
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"interpreter-specific cache")
    (assets / "helper.py").write_text("value = 1\n", encoding="utf-8")
    (assets / "image.bin").write_bytes(b"\xff\x00")
    output = tmp_path / "session"

    result = main(
        build_actions(),
        ["compose", "shared", "--root", str(source_root), "--output", str(output)],
    )
    assert result == 0, capsys.readouterr().err
    delivered = output / ".apm/skills/kit-shared/assets"
    assert not (delivered / generated).exists()
    assert (delivered / "helper.py").read_text(encoding="utf-8") == "value = 1\n"
    assert (delivered / "image.bin").read_bytes() == b"\xff\x00"
    adapter = FileCatalogAdapter()
    assert ProvenanceService().verify(adapter.load_composed(output)).valid

    injected = delivered / generated
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_bytes(b"unattested output")
    assert not ProvenanceService().verify(adapter.load_composed(output)).valid


@pytest.mark.parametrize("relative", ["__pycache__", "helper.pyc", "helper.pyo"])
def test_bytecode_exclusion_does_not_hide_linked_paths(
    source_root: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    cache = source_root / "packages/shared/.apm/skills/kit-shared" / relative
    if relative == "__pycache__":
        cache.mkdir()
    else:
        cache.write_bytes(b"linked bytecode")
    original = catalog_module._is_link

    def linked(path: Path) -> bool:
        return path == cache or original(path)

    monkeypatch.setattr(catalog_module, "_is_link", linked)
    snapshot = FileCatalogAdapter().load(source_root)
    bundle = next(bundle for bundle in snapshot.bundles if bundle.name == "shared")
    assert any(
        item.is_symlink and item.relative_path.endswith(f"/{relative}")
        for item in bundle.files
    )
    assert not CatalogService().validate(snapshot).valid


@pytest.mark.parametrize("generated", [".git", "node_modules", ".hypothesis", ".ty"])
def test_source_inventory_does_not_descend_into_generated_directories(
    source_root: Path, generated: str
) -> None:
    cache = source_root / generated / "nested"
    cache.mkdir(parents=True)
    (cache / "generated.txt").write_text("not source", encoding="utf-8")
    documentation = source_root / "docs"
    documentation.mkdir()
    (documentation / "guide.md").write_text("# Authored guide\n", encoding="utf-8")

    snapshot = FileCatalogAdapter().load(source_root)
    assert not any(path.startswith(f"{generated}/") for path in snapshot.root_paths)
    assert "docs/guide.md" in snapshot.root_paths


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
