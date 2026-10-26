"""Containment, collision, and no-replace guarantees of composed output writes."""

from pathlib import Path
import string
import sys

import pytest

from agent_kit.core.models import CompositionPlan, PlannedFile
import agent_kit.infrastructure.output_adapter as output_module
from agent_kit.infrastructure.output_adapter import (
    OutputAdapter,
    OutputPathError,
    OutputPathIssue,
)


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


@pytest.mark.parametrize(
    "relative",
    [
        "docs/report.",
        "docs/report ",
        "docs./report.md",
        "docs /report.md",
        "docs/report:metadata",
        "docs:metadata/report.md",
        "docs/CON",
        "docs/con.txt",
        "docs/PRN.log",
        "docs/AUX",
        "docs/NUL.txt",
        "docs/COM1.md",
        "docs/LPT9.md",
        "docs/COM¹.md",
        "docs/LPT².md",
        "docs/CONIN$",
        "docs/CONOUT$",
        "NUL/report.md",
        *[f"docs/report{character}.md" for character in '<>"|?*'],
        *[f"docs/report{chr(code)}.md" for code in range(32)],
    ],
)
def test_nonportable_planned_paths_are_rejected_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    """Reject Windows normalization, devices, streams, and forbidden characters."""
    plan = _plan(
        tmp_path / "source",
        PlannedFile(content=b"valid", relative_path="docs/valid.md"),
        PlannedFile(content=b"unsafe", relative_path=relative),
    )

    def no_staging(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unsafe plans must fail before creating a staging directory")

    monkeypatch.setattr(output_module.tempfile, "TemporaryDirectory", no_staging)
    with pytest.raises(OutputPathError, match="unsafe path") as error:
        OutputAdapter().write(plan, tmp_path / "new-parent" / "out")

    assert error.value.issue is OutputPathIssue.UNSAFE_PLAN
    assert sorted(tmp_path.iterdir()) == []


@pytest.mark.parametrize("letter", list(string.ascii_letters))
def test_single_letter_alternate_stream_is_rejected_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, letter: str
) -> None:
    """A drive-like component cannot hide an alternate stream of a planned file."""
    plan = _plan(
        tmp_path / "source",
        PlannedFile(content=b"ordinary file", relative_path=f"docs/{letter}"),
        PlannedFile(
            content=b"alternate-stream bytes",
            relative_path=f"docs/{letter}:metadata",
        ),
    )

    def no_writes(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unsafe plans must fail before any filesystem writes")

    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "mkdir", no_writes)
        with pytest.raises(OutputPathError, match="unsafe path") as error:
            OutputAdapter().write(plan, tmp_path / "new-parent" / "out")

    assert error.value.issue is OutputPathIssue.UNSAFE_PLAN
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "relative",
    [
        "docs/a",
        "docs/Z",
        "docs/report.md",
        "docs/report metadata.md",
        "docs/report.v1.txt",
        ".apm/skills/report/assets/data.bin",
        "docs/COM10.md",
        "docs/LPT0.md",
        "docs/console.md",
        "docs/résumé.md",
    ],
)
def test_portable_planned_paths_preserve_their_names_and_bytes(
    tmp_path: Path, relative: str
) -> None:
    plan = _plan(
        tmp_path / "source",
        PlannedFile(content=b"exact bytes\n", relative_path=relative),
    )

    output = OutputAdapter().write(plan, tmp_path / "out")

    assert (output / relative).read_bytes() == b"exact bytes\n"
    assert [
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    ] == [relative]


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
