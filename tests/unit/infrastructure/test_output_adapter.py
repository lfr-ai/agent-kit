"""Containment, collision, and no-replace guarantees of composed output writes."""

from pathlib import Path
import sys

import pytest

from agent_kit.core.models import CompositionPlan, PlannedFile
import agent_kit.infrastructure.output_adapter as output_module
from agent_kit.infrastructure.output_adapter import OutputAdapter


def _plan(
    root: Path,
    *files: PlannedFile,
    source_paths: tuple[tuple[str, str], ...] = (("toolkit", "."),),
) -> CompositionPlan:
    return CompositionPlan(
        bundles=("toolkit",),
        files=files or (PlannedFile(content=b"x\n", relative_path="apm.yml"),),
        profile="toolkit",
        root=root,
        runtimes=(),
        source_paths=source_paths,
        version="0.1.0",
    )


def test_writes_every_planned_byte_beneath_a_new_directory(tmp_path: Path) -> None:
    """A fresh destination receives exactly the planned files."""
    plan = _plan(
        tmp_path / "source",
        PlannedFile(content=b"manifest\n", relative_path="apm.yml"),
        PlannedFile(content=b"\x00binary", relative_path=".apm/skills/a/data.bin"),
    )

    output = OutputAdapter().write(plan, tmp_path / "out")

    assert (output / "apm.yml").read_bytes() == b"manifest\n"
    assert (output / ".apm/skills/a/data.bin").read_bytes() == b"\x00binary"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out"]


def test_existing_output_is_never_replaced(tmp_path: Path) -> None:
    """The adapter refuses to overwrite any existing destination."""
    existing = tmp_path / "out"
    existing.mkdir()
    (existing / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        OutputAdapter().write(_plan(tmp_path / "source"), existing)

    assert (existing / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "relative",
    ["../escape", "/absolute", "C:/drive", "C:relative", "a\\b", "a//b", ""],
)
def test_unsafe_planned_paths_are_rejected_before_writing(
    tmp_path: Path, relative: str
) -> None:
    """No planned path may leave the destination or use host-specific syntax."""
    plan = _plan(tmp_path / "source", PlannedFile(content=b"x", relative_path=relative))

    with pytest.raises(ValueError, match="unsafe path"):
        OutputAdapter().write(plan, tmp_path / "out")

    assert not (tmp_path / "out").exists()


def test_case_insensitive_collisions_are_rejected(tmp_path: Path) -> None:
    """Paths that collide on case-insensitive filesystems are refused everywhere."""
    plan = _plan(
        tmp_path / "source",
        PlannedFile(content=b"a", relative_path="Skill.md"),
        PlannedFile(content=b"b", relative_path="skill.MD"),
    )

    with pytest.raises(ValueError, match="case-insensitive"):
        OutputAdapter().write(plan, tmp_path / "out")


def test_output_cannot_be_the_source_root_or_its_ancestor(tmp_path: Path) -> None:
    """Writing over the source tree or a parent of it is refused."""
    root = tmp_path / "source"
    root.mkdir()

    for output in (root, tmp_path):
        with pytest.raises(ValueError, match="source root"):
            OutputAdapter().write(_plan(root), output)


def test_output_inside_source_must_be_beneath_build(tmp_path: Path) -> None:
    """Only ROOT/build is an acceptable in-tree destination."""
    root = tmp_path / "source"
    root.mkdir()

    with pytest.raises(ValueError, match="beneath ROOT/build"):
        OutputAdapter().write(_plan(root), root / "docs" / "out")

    assert OutputAdapter().write(_plan(root), root / "build" / "out").is_dir()


def test_output_may_not_overlap_a_non_root_bundle(tmp_path: Path) -> None:
    """A destination inside a selected bundle path is refused."""
    root = tmp_path / "source"
    bundle = tmp_path / "bundle"
    plan = _plan(root, source_paths=(("external", "../bundle"),))

    with pytest.raises(ValueError, match="overlaps a source bundle"):
        OutputAdapter().write(plan, bundle / "out")


def test_unsupported_platform_fails_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Platforms without an atomic no-replace rename are refused explicitly."""
    monkeypatch.setattr(output_module.sys, "platform", "darwin")

    with pytest.raises(NotImplementedError, match="Windows and Linux"):
        OutputAdapter().write(_plan(tmp_path / "source"), tmp_path / "out")

    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_symlinked_output_parent_is_rejected(tmp_path: Path) -> None:
    """A link in the destination path cannot redirect the write."""
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "link").symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        OutputAdapter().write(_plan(tmp_path / "source"), tmp_path / "link" / "out")
