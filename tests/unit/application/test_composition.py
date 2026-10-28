"""Profile composition and atomic output contracts."""

from __future__ import annotations

from dataclasses import replace
import json
from typing import TYPE_CHECKING

import pytest

from agent_kit.application.services.catalog_service import (
    CatalogService,
    CompositionCollisionError,
)
from agent_kit.core.models import CompositionPlan, PlannedFile
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter
import agent_kit.infrastructure.output_adapter as output_module
from agent_kit.infrastructure.output_adapter import OutputAdapter

if TYPE_CHECKING:
    from pathlib import Path


def _plan(
    root: Path,
    profile: str = "backend",
    features: tuple[str, ...] = (),
    runtimes: tuple[str, ...] = (),
) -> CompositionPlan:
    snapshot = FileCatalogAdapter().load(root)
    return CatalogService().compose(snapshot, profile, features, runtimes)


def _materialize(root: Path, output: Path, profile: str = "backend") -> Path:
    return OutputAdapter().write(_plan(root, profile), output)


def test_backend_composition_flattens_only_selected_bundles(
    source_root: Path, tmp_path: Path
) -> None:
    output = _materialize(source_root, tmp_path / "backend")

    assert (output / ".apm/skills/kit-shared/SKILL.md").is_file()
    assert (output / ".apm/skills/kit-backend/SKILL.md").is_file()
    assert not (output / ".apm/skills/kit-frontend/SKILL.md").exists()
    manifest = json.loads((output / "apm.yml").read_text(encoding="utf-8"))
    assert manifest["name"] == "agent-kit-backend"
    assert manifest["targets"] == ["copilot", "claude"]
    assert manifest["dependencies"] == {}
    assert manifest["executables"] == {}
    assert manifest["includes"] == [".apm/instructions/", ".apm/skills/"]


def test_composed_package_carries_its_license(
    source_root: Path, tmp_path: Path
) -> None:
    """Redistributable APM packages include SPDX metadata and the license text."""
    (source_root / "LICENSE").write_text(
        "MIT License\nFixture content\n", encoding="utf-8"
    )
    output = _materialize(source_root, tmp_path / "licensed")

    manifest = json.loads((output / "apm.yml").read_text())
    assert manifest["license"] == "MIT"
    assert (output / "LICENSE").read_text() == "MIT License\nFixture content\n"


def test_feature_selection_forms_transitive_ordered_union(
    source_root: Path,
) -> None:
    plan = _plan(source_root, "shared", ("iac",))

    assert plan.bundles == ("shared", "iac")


def test_compose_outputs_are_byte_deterministic(
    source_root: Path, tmp_path: Path
) -> None:
    first = _materialize(source_root, tmp_path / "first")
    second = _materialize(source_root, tmp_path / "second")
    first_files = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }

    assert first_files == second_files


def test_existing_output_is_never_modified(source_root: Path, tmp_path: Path) -> None:
    output = tmp_path / "already-there"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("operator-owned", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        _materialize(source_root, output)

    assert marker.read_text(encoding="utf-8") == "operator-owned"


@pytest.mark.parametrize(
    "relative_output",
    [
        ".",
        "..",
        "packages",
        "packages/backend/.apm/skills/new-output",
    ],
)
def test_output_root_ancestor_and_source_overlap_are_rejected(
    source_root: Path, relative_output: str
) -> None:
    plan = _plan(source_root)
    output = source_root / relative_output

    with pytest.raises(ValueError, match=r"output|source"):
        OutputAdapter().write(plan, output)


def test_root_build_output_is_allowed(source_root: Path) -> None:
    output = source_root / "build/backend"

    result = _materialize(source_root, output)

    assert result == output.resolve()
    assert (output / "provenance.json").is_file()


def test_build_symlink_cannot_redirect_output(
    source_root: Path, tmp_path: Path
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    build = source_root / "build"
    try:
        build.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    with pytest.raises(ValueError, match="source validation failed"):
        _materialize(source_root, build / "backend")

    assert list(external.iterdir()) == []


def test_flatten_collision_fails_instead_of_overwriting(
    source_root: Path, tmp_path: Path
) -> None:
    duplicate = (
        source_root / "packages/backend/.apm/instructions/kit-shared.instructions.md"
    )
    duplicate.write_text(
        "---\ndescription: Duplicate instruction.\napplyTo: '**/*.py'\n"
        "---\n\nCollision.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="collision"):
        _plan(source_root)

    assert not (tmp_path / "unused").exists()


def test_casefold_destination_collision_is_rejected(source_root: Path) -> None:
    duplicate = (
        source_root / "packages/backend/.apm/instructions/KIT-SHARED.instructions.md"
    )
    duplicate.write_text(
        "---\ndescription: Case-variant instruction.\napplyTo: '**/*.py'\n"
        "---\n\nCollision.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case-insensitive composition collision"):
        _plan(source_root)


@pytest.mark.parametrize("name", ["selection.json", "Selection.JSON"])
def test_authored_selection_collision_is_rejected_before_publication(
    source_root: Path, tmp_path: Path, name: str
) -> None:
    bundle = source_root / "packages/backend"
    authored = bundle / ".apm" / name
    authored.write_bytes(b'{"authored": true}')
    manifest_path = bundle / "apm.yml"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["includes"].append(f".apm/{name}")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert CatalogService().validate(FileCatalogAdapter().load(source_root)).valid
    output = tmp_path / "collision"

    with pytest.raises(CompositionCollisionError, match="composition collision"):
        _materialize(source_root, output)

    assert authored.read_bytes() == b'{"authored": true}'
    assert not output.exists()
    assert list(tmp_path.iterdir()) == [source_root]


def test_failed_atomic_rename_cleans_staging_output(
    source_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "failed-output"
    plan = _plan(source_root)
    failure = OSError("controlled rename failure")

    def fail_rename(_path: Path, _target: Path) -> None:
        raise failure

    monkeypatch.setattr(output_module, "_publish_directory", fail_rename)
    with pytest.raises(OSError, match="controlled rename failure") as raised:
        OutputAdapter().write(plan, output)

    assert raised.value is failure
    assert not output.exists()
    assert list(tmp_path.iterdir()) == [source_root]


def test_runtime_targets_are_explicitly_validated(source_root: Path) -> None:
    with pytest.raises(ValueError, match="not supported"):
        _plan(source_root, runtimes=("other",))


def test_planned_backslash_traversal_is_rejected(
    source_root: Path, tmp_path: Path
) -> None:
    """A Windows separator cannot turn a single POSIX component into traversal."""
    plan = replace(
        _plan(source_root),
        files=(PlannedFile(relative_path=r"..\escaped.txt", content=b"bad"),),
    )

    with pytest.raises(ValueError, match="unsafe path"):
        OutputAdapter().write(plan, tmp_path / "new-output")

    assert not (tmp_path / "escaped.txt").exists()


def test_build_allowance_does_not_allow_overlap_with_a_source_bundle(
    source_root: Path,
) -> None:
    """The build exception applies to the toolkit root, not nested source bundles."""
    plan = replace(_plan(source_root), source_paths=(("owned", "build/source"),))

    with pytest.raises(ValueError, match="overlaps"):
        OutputAdapter().write(plan, source_root / "build/source/new-output")


def test_concurrent_empty_destination_is_never_replaced(
    source_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A competing empty directory created during staging remains untouched."""
    output = tmp_path / "competing"
    publish = output_module._publish_directory

    def race(stage: Path, target: Path) -> None:
        target.mkdir()
        publish(stage, target)

    monkeypatch.setattr(output_module, "_publish_directory", race)

    with pytest.raises(FileExistsError, match=r"(?i)exists"):
        OutputAdapter().write(_plan(source_root), output)

    assert output.is_dir()
    assert list(output.iterdir()) == []
    assert not list(tmp_path.glob(".competing.agent-kit-*"))
