"""Catalog-generated APM profile manifest and ownership contracts."""

import json
from pathlib import Path
import sys

import pytest
from scripts.build_profiles import ProfileBuildError, check, main, write


def test_profiles_are_compact_meta_packages_for_the_catalog_closure(
    source_root: Path,
) -> None:
    for bundle, name, url in (
        ("shared", "context7", "https://mcp.context7.com/mcp/oauth"),
        ("backend", "postman", "https://mcp.postman.com/minimal"),
    ):
        package_manifest = source_root / f"packages/{bundle}/apm.yml"
        manifest_data = json.loads(package_manifest.read_text(encoding="utf-8"))
        manifest_data["dependencies"]["mcp"] = [
            {
                "name": name,
                "registry": False,
                "transport": "http",
                "url": url,
            }
        ]
        package_manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

    write(source_root)

    assert check(source_root) == []
    assert not (source_root / "profiles/toolkit").exists()
    manifest_path = source_root / "profiles/backend/apm.yml"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "agent-kit-profile-backend"
    assert manifest["version"] == "0.1.0"
    assert manifest["targets"] == ["copilot", "claude"]
    assert manifest["includes"] == []
    assert manifest["dependencies"]["apm"] == [
        "lfr-ai/agent-kit/packages/shared#v0.1.0",
        "lfr-ai/agent-kit/packages/backend#v0.1.0",
    ]
    assert {server["name"] for server in manifest["dependencies"]["mcp"]} == {
        "context7",
        "postman",
    }
    assert not (source_root / "profiles/backend/.apm").exists()
    assert (source_root / ".agents/agentic-setup/profile-lock.json").is_file()


def test_profile_generation_refuses_unowned_files(source_root: Path) -> None:
    owned = source_root / "profiles/backend"
    owned.mkdir(parents=True)
    marker = owned / "operator-owned.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ProfileBuildError, match="unowned files"):
        write(source_root)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_profile_generation_refuses_independent_edits(source_root: Path) -> None:
    write(source_root)
    generated = source_root / "profiles/backend/apm.yml"
    generated.write_text("independent edit", encoding="utf-8")

    with pytest.raises(ProfileBuildError, match="edited independently"):
        write(source_root)

    assert generated.read_text(encoding="utf-8") == "independent edit"


def test_profile_cli_rejects_linked_root_before_resolving(
    source_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linked_root = tmp_path / "linked-root"
    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def is_symlink(path: Path) -> bool:
        return path == linked_root or original_is_symlink(path)

    def resolve(path: Path, *, strict: bool = False) -> Path:
        if path == linked_root:
            return source_root
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_profiles.py", "--root", str(linked_root), "--write"],
    )

    assert main() == 1
    assert not (source_root / "profiles").exists()
    assert not (source_root / ".agents/agentic-setup/profile-lock.json").exists()


def test_profile_generation_tracks_catalog_selection_changes(source_root: Path) -> None:
    write(source_root)
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["profiles"]["backend"]["extends"] = []
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    write(source_root)

    generated = json.loads(
        (source_root / "profiles/backend/apm.yml").read_text(encoding="utf-8")
    )
    assert generated["dependencies"]["apm"] == [
        "lfr-ai/agent-kit/packages/backend#v0.1.0"
    ]
    assert check(source_root) == []
