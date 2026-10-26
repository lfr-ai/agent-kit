"""Explicit session selection preserves policy without exposing the whole library."""

import json
from pathlib import Path

import pytest

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
from agent_kit.infrastructure.output_adapter import OutputAdapter


def _materialize_session(root: Path, output: Path, skills: tuple[str, ...]) -> Path:
    snapshot = FileCatalogAdapter().load(root)
    plan = CatalogService().compose(snapshot, "backend", (), (), skills=skills)
    return OutputAdapter().write(plan, output)


def test_session_delivers_only_named_skills_and_their_resources(
    source_root: Path,
) -> None:
    asset = source_root / "packages/backend/.apm/skills/kit-backend/assets/example.txt"
    asset.parent.mkdir()
    asset.write_text("Selected resource.\n", encoding="utf-8")
    snapshot = FileCatalogAdapter().load(source_root)

    plan = CatalogService().compose(
        snapshot, "backend", (), (), skills=("kit-backend",)
    )
    files = {item.relative_path: item.content for item in plan.files}

    assert ".apm/skills/kit-backend/SKILL.md" in files
    assert ".apm/skills/kit-backend/assets/example.txt" in files
    assert ".apm/skills/kit-shared/SKILL.md" not in files
    assert ".apm/instructions/kit-shared.instructions.md" not in files
    assert ".apm/instructions/kit-backend.instructions.md" in files
    assert "apm-policy.yml" in files
    assert "LICENSE" in files
    report = json.loads(files[".apm/selection.json"])
    assert report["mode"] == "session"
    assert report["skills"] == ["kit-backend"]
    assert report["instructions"] == ["kit-backend"]
    assert report["native_role_files"] == 0
    assert report["description_chars"] == len("Review backend changes carefully.")
    assert report["instruction_chars"] > 0


@pytest.mark.parametrize(
    "skills",
    [("kit-frontend",), ("unknown",), ("kit-backend", "kit-backend"), ("",)],
)
def test_session_rejects_unavailable_or_duplicate_skill_ids(
    source_root: Path, tmp_path: Path, skills: tuple[str, ...]
) -> None:
    destination = tmp_path / "not-created"

    with pytest.raises(ValueError, match="skill"):
        _materialize_session(source_root, destination, skills)

    assert not destination.exists()


def test_session_fails_if_a_selected_resource_links_to_an_omitted_skill(
    source_root: Path,
) -> None:
    owner = source_root / "packages/shared/.apm/skills/kit-shared"
    sibling = owner.parent / "kit-reference"
    sibling.mkdir()
    (sibling / "SKILL.md").write_text(
        "---\nname: kit-reference\ndescription: Read reference material.\n"
        "---\n\n# Reference\n",
        encoding="utf-8",
    )
    skill = owner / "SKILL.md"
    skill.write_text(
        skill.read_text() + "\n[Related](../kit-reference/SKILL.md)\n",
        encoding="utf-8",
    )
    snapshot = FileCatalogAdapter().load(source_root)

    with pytest.raises(ValueError, match="omitted resource"):
        CatalogService().compose(snapshot, "shared", (), (), skills=("kit-shared",))

    plan = CatalogService().compose(
        snapshot, "shared", (), (), skills=("kit-shared", "kit-reference")
    )
    assert sum(item.relative_path.endswith("/SKILL.md") for item in plan.files) == 2


def test_session_order_does_not_change_authored_output(source_root: Path) -> None:
    service = CatalogService()
    snapshot = FileCatalogAdapter().load(source_root)

    first = service.compose(
        snapshot, "backend", (), (), skills=("kit-shared", "kit-backend")
    )
    second = service.compose(
        snapshot, "backend", (), (), skills=("kit-backend", "kit-shared")
    )

    assert first.files == second.files


@pytest.mark.parametrize("skills", [(), ("kit-backend",), ("kit-shared",)])
def test_manifest_includes_preserve_file_and_directory_semantics(
    source_root: Path, skills: tuple[str, ...]
) -> None:
    bundle = source_root / "packages/backend"
    path = bundle / "apm.yml"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["includes"] = [
        ".apm/instructions/kit-backend.instructions.md",
        ".apm/skills/",
    ]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    plan = CatalogService().compose(
        FileCatalogAdapter().load(source_root),
        "backend",
        (),
        (),
        skills=skills,
    )
    files = {item.relative_path: item.content for item in plan.files}
    includes = json.loads(files["apm.yml"])["includes"]

    assert (".apm/instructions/kit-backend.instructions.md" in includes) is (
        skills != ("kit-shared",)
    )
    assert ".apm/instructions/kit-backend.instructions.md/" not in includes
    assert ".apm/skills/" in includes
    for include in includes:
        if include.endswith("/"):
            assert any(path.startswith(include) for path in files)
        else:
            assert include in files


def test_session_does_not_parse_python_subscript_calls_as_markdown_links(
    source_root: Path,
) -> None:
    asset = (
        source_root
        / "packages/backend/.apm/skills/kit-backend/assets/logging.py.template"
    )
    asset.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "from contextvars import ContextVar\n"
        '_ID = ContextVar[str | None]("correlation_id", default=None)\n'
    )
    asset.write_bytes(content.encode("utf-8"))
    plan = CatalogService().compose(
        FileCatalogAdapter().load(source_root),
        "backend",
        (),
        (),
        skills=("kit-backend",),
    )
    files = {item.relative_path: item.content for item in plan.files}
    assert (
        files[".apm/skills/kit-backend/assets/logging.py.template"] == content.encode()
    )
